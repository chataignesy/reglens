"""Thin LLM provider layer. Every call is logged to the usage ledger.

- `ClaudeCLIProvider` (billing: subscription): runs `claude -p` with no tools, so calls use the
  local Claude Code login. For the user's own development only.
- `AnthropicAPIProvider` (billing: api): the official Anthropic SDK with a caller-supplied key,
  for the bring-your-own-key demo. The key is held by the client object only — never logged,
  stored or written to the ledger.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from reglens.cancel import Cancelled
from reglens.config import Config
from reglens.llm.ledger import Ledger, Usage

DEFAULT_SYSTEM = "You are a precise assistant for EU credit risk regulation."


class LLMError(RuntimeError):
    """A failed call. `tokens` is what the failed call reported spending (None: unknown)."""

    def __init__(
        self, message: str, *, tokens: int | None = None, usage_known: bool | None = None,
        retryable: bool | None = None,
    ):
        super().__init__(message)
        self.tokens = tokens
        self.usage_known = tokens is not None if usage_known is None else usage_known
        self.retryable = transient_error(message) if retryable is None else retryable


def transient_error(message: str) -> bool:
    """Conservative compatibility classification for older cached provider errors.

    Cost caps, schema failures and missing evidence are real attempts, not service outages.
    New API failures carry explicit classification rather than relying on this text.
    """
    import re

    return bool(re.search(
        r"timed?\s*out|timeout|rate.?limit|usage limit|session limit|"
        r"hit your limit|out of extra usage|overloaded|could not reach|"
        r"connection (?:error|reset)|returned non-JSON|API error \(5\d\d\)", message, re.I,
    ))


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    usage: Usage
    stop_reason: str | None = None
    usage_known: bool = True
    reported_cost_usd: float | None = None


class LLMProvider(Protocol):
    def complete(
        self,
        prompt: str,
        *,
        purpose: str,
        system: str | None = None,
        tier: str | None = None,
        effort: str | None = None,
    ) -> Completion: ...


def _usage_from_model_usage(raw: dict) -> Usage:
    """`modelUsage` entries in `claude -p` JSON use camelCase keys."""
    return Usage(
        input_tokens=int(raw.get("inputTokens") or 0),
        output_tokens=int(raw.get("outputTokens") or 0),
        cache_read_input_tokens=int(raw.get("cacheReadInputTokens") or 0),
        cache_creation_input_tokens=int(raw.get("cacheCreationInputTokens") or 0),
    )


def _all_usage(out: dict) -> Usage:
    """The top-level CLI usage can omit helpers; modelUsage is the authoritative breakdown."""
    parts = [_usage_from_model_usage(v) for v in (out.get("modelUsage") or {}).values()]
    if not parts:
        return Usage.from_response(out.get("usage") or {})
    return Usage(
        *(
            sum(getattr(p, key) for p in parts)
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
            )
        )
    )


class ClaudeCLIProvider:
    def __init__(
        self,
        config: Config,
        ledger: Ledger | None = None,
        *,
        executable: str = "claude",
        timeout_s: int = 600,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self.config = config
        self.ledger = ledger or Ledger(config)
        self.executable = executable
        self.timeout_s = timeout_s
        self.runner = runner
        self.cancel = None  # a reglens.cancel.CancelToken: checked before every call

    def with_cancel(self, token) -> ClaudeCLIProvider:
        """Same settings, but the subprocess is killed when `token` is cancelled."""
        from reglens.cancel import cancellable_runner

        clone = ClaudeCLIProvider(
            self.config,
            self.ledger,
            executable=self.executable,
            timeout_s=self.timeout_s,
            runner=cancellable_runner(token),
        )
        clone.cancel = token
        return clone

    def complete(
        self,
        prompt: str,
        *,
        purpose: str,
        system: str | None = None,
        tier: str | None = None,
        effort: str | None = None,
        extra_args: list[str] | None = None,
    ) -> Completion:
        """`extra_args` are appended to the `claude -p` command (e.g. --mcp-config)."""
        if self.cancel is not None:
            self.cancel.check()
        model = self.config.model(tier)
        # System prompt goes via a file to stay clear of Windows command-line length limits.
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
            f.write(system or DEFAULT_SYSTEM)
            system_file = f.name
        cmd = [
            self.executable,
            "-p",
            "--output-format",
            "json",
            "--model",
            model,
            "--system-prompt-file",
            system_file,
            "--tools",
            "",
            "--no-session-persistence",
            "--strict-mcp-config",
        ]
        if effort:
            cmd += ["--effort", effort]
        cmd += extra_args or []
        try:
            # Neutral cwd so no project CLAUDE.md is loaded into the call; prompt via stdin.
            proc = self.runner(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_s,
                cwd=tempfile.gettempdir(),
                # MCP tools must be loaded up front: with tool search on, the CLI defers them
                # behind ToolSearch, which `--tools ""` removes, so the agent sees no tools.
                env=os.environ | {"ENABLE_TOOL_SEARCH": "false"},
            )
        except Cancelled:
            # killed mid-call: it may have spent tokens, but reported none (unknown, not zero)
            self.ledger.record(
                model, Usage(0, 0), purpose=purpose, outcome="cancelled", usage_known=False
            )
            raise
        except subprocess.TimeoutExpired as e:
            self.ledger.record(
                model, Usage(0, 0), purpose=purpose, outcome="timeout", usage_known=False
            )
            raise LLMError(f"claude -p timed out after {self.timeout_s}s") from e
        finally:
            os.unlink(system_file)

        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            self.ledger.record(
                model, Usage(0, 0), purpose=purpose, outcome="no_result", usage_known=False
            )
            raise LLMError(
                f"claude -p returned non-JSON (exit {proc.returncode}): {proc.stderr[-500:]}"
            ) from e
        if out.get("is_error") or out.get("subtype") != "success":
            # a failed call (e.g. the --max-budget-usd cap) still spent tokens: log them
            outcome = str(out.get("subtype") or "error")
            if outcome == "success":  # CLI can report is_error=true with subtype=success
                outcome = "provider_error"
            tokens = self._log(out, model, purpose, outcome=outcome)
            raise LLMError(f"claude -p failed: {outcome}: {out.get('result')}", tokens=tokens)

        self._log(out, model, purpose)
        return Completion(
            text=out.get("result", ""),
            model=model,
            usage=_all_usage(out),
            stop_reason=out.get("stop_reason"),
            usage_known=bool(out.get("modelUsage") or out.get("usage")),
            reported_cost_usd=out.get("total_cost_usd"),
        )

    def _log(self, out: dict, model: str, purpose: str, *, outcome: str = "ok") -> int | None:
        """One ledger entry per model actually used (Claude Code may call helper models).
        Returns the tokens logged, or None when the reply carried no usage (unknown)."""
        model_usage = out.get("modelUsage") or {}
        if not model_usage:
            known = bool(out.get("usage"))
            usage = Usage.from_response(out.get("usage") or {})
            self.ledger.record(
                model,
                usage,
                purpose=purpose,
                reported_cost_usd=out.get("total_cost_usd"),
                outcome=outcome,
                usage_known=known,
            )
            return usage.total_tokens if known else None
        total = 0
        for name, raw in model_usage.items():
            usage = _usage_from_model_usage(raw)
            total += usage.total_tokens
            self.ledger.record(
                name,
                usage,
                purpose=purpose,
                reported_cost_usd=raw.get("costUSD"),
                outcome=outcome,
            )
        return total


FALLBACK_BETA = "server-side-fallback-2026-07-01"  # with fallbacks="default"


class AnthropicAPIProvider:
    """Messages API via the official SDK. Adaptive thinking is the model default (no `thinking`
    parameter); depth is set with `output_config.effort`. Server-side fallback ("default" form)
    re-runs a policy-declined request on a suitable model inside the same call."""

    def __init__(
        self,
        config: Config,
        api_key: str | None = None,
        ledger: Ledger | None = None,
        *,
        client=None,
        max_tokens: int = 16000,
        fallback: bool = True,
    ):
        self.config = config
        self.ledger = ledger or Ledger(config)
        self.max_tokens = max_tokens
        self.fallback = fallback
        if client is None:
            import anthropic

            # api_key=None lets the SDK resolve ANTHROPIC_API_KEY or an `ant auth login` profile
            client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.client = client
        self.cancel = None  # a reglens.cancel.CancelToken: no new request once it is set

    def with_cancel(self, token) -> AnthropicAPIProvider:
        self.cancel = token
        return self

    def complete(
        self,
        prompt: str,
        *,
        purpose: str,
        system: str | None = None,
        tier: str | None = None,
        effort: str | None = None,
    ) -> Completion:
        response, usage, served = self.create(
            [{"role": "user", "content": prompt}],
            purpose=purpose,
            system=system,
            tier=tier,
            effort=effort,
        )
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        return Completion(text=text, model=served, usage=usage, stop_reason=response.stop_reason)

    def create(
        self,
        messages: list[dict],
        *,
        purpose: str,
        system: str | None = None,
        tier: str | None = None,
        effort: str | None = None,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
    ) -> tuple:
        """One Messages API call (any number of turns, optional tools), logged to the ledger.
        `tool_choice={"type": "none"}` keeps the tools defined but forbids calling them (a
        final turn). Returns (response, Usage, served model). Raises LLMError on API errors
        and refusals."""
        import anthropic

        if self.cancel is not None:
            self.cancel.check()
        model = self.config.model(tier)
        kwargs: dict = {
            "model": model,
            "max_tokens": self.max_tokens,
            # cache the static prefix: tools + system prompt (shorter prefixes silently don't cache)
            "system": [
                {
                    "type": "text",
                    "text": system or DEFAULT_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        if effort:
            kwargs["output_config"] = {"effort": effort}
        try:
            if self.fallback:
                response = self.client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks="default", **kwargs
                )
            else:
                response = self.client.messages.create(**kwargs)
        except anthropic.APIError as e:
            self.ledger.record(
                model, Usage(0, 0), purpose=purpose, outcome=type(e).__name__, usage_known=False
            )
            if isinstance(e, anthropic.AuthenticationError):
                message = "Anthropic API rejected the API key."
            elif isinstance(e, anthropic.PermissionDeniedError):
                message = "The API key has no access to this model."
            elif isinstance(e, anthropic.RateLimitError):
                message = "Rate limited by the Anthropic API; try again shortly."
            elif isinstance(e, anthropic.BadRequestError):
                message = f"Request rejected: {e.message}"
            elif isinstance(e, anthropic.APIStatusError):
                message = f"Anthropic API error ({e.status_code})."
            else:
                message = "Could not reach the Anthropic API."
            retryable = isinstance(e, (
                anthropic.RateLimitError, anthropic.APIConnectionError,
                anthropic.AuthenticationError, anthropic.PermissionDeniedError,
            )) or (
                isinstance(e, anthropic.APIStatusError) and e.status_code >= 500
            )
            raise LLMError(message, retryable=retryable) from e

        usage = Usage.from_response(response.usage)
        served = getattr(response, "model", model) or model
        logged = served if served in self.config.prices else model
        self.ledger.record(logged, usage, purpose=purpose)
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise LLMError(
                f"The model declined the request (category: {category}).", tokens=usage.total_tokens
            )
        return response, usage, served


def get_provider(
    config: Config, ledger: Ledger | None = None, *, api_key: str | None = None
) -> LLMProvider:
    if config.billing == "subscription":
        return ClaudeCLIProvider(config, ledger)
    return AnthropicAPIProvider(config, api_key, ledger)
