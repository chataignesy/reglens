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

from reglens.config import Config
from reglens.llm.ledger import Ledger, Usage

DEFAULT_SYSTEM = "You are a precise assistant for EU credit risk regulation."


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    usage: Usage
    stop_reason: str | None = None


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

    def complete(
        self,
        prompt: str,
        *,
        purpose: str,
        system: str | None = None,
        tier: str | None = None,
        effort: str | None = None,
    ) -> Completion:
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
            )
        except subprocess.TimeoutExpired as e:
            raise LLMError(f"claude -p timed out after {self.timeout_s}s") from e
        finally:
            os.unlink(system_file)

        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise LLMError(
                f"claude -p returned non-JSON (exit {proc.returncode}): {proc.stderr[-500:]}"
            ) from e
        if out.get("is_error") or out.get("subtype") != "success":
            raise LLMError(f"claude -p failed: {out.get('subtype')}: {out.get('result')}")

        self._log(out, model, purpose)
        return Completion(
            text=out.get("result", ""),
            model=model,
            usage=Usage.from_response(out.get("usage") or {}),
            stop_reason=out.get("stop_reason"),
        )

    def _log(self, out: dict, model: str, purpose: str) -> None:
        # One ledger entry per model actually used (Claude Code may call helper models).
        model_usage = out.get("modelUsage") or {}
        if not model_usage:
            self.ledger.record(
                model,
                Usage.from_response(out.get("usage") or {}),
                purpose=purpose,
                reported_cost_usd=out.get("total_cost_usd"),
            )
            return
        for name, raw in model_usage.items():
            self.ledger.record(
                name,
                _usage_from_model_usage(raw),
                purpose=purpose,
                reported_cost_usd=raw.get("costUSD"),
            )


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

    def complete(
        self,
        prompt: str,
        *,
        purpose: str,
        system: str | None = None,
        tier: str | None = None,
        effort: str | None = None,
    ) -> Completion:
        import anthropic

        model = self.config.model(tier)
        kwargs: dict = {
            "model": model,
            "max_tokens": self.max_tokens,
            # cache the static system prompt (shorter prefixes silently don't cache)
            "system": [
                {
                    "type": "text",
                    "text": system or DEFAULT_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": prompt}],
        }
        if effort:
            kwargs["output_config"] = {"effort": effort}
        try:
            if self.fallback:
                response = self.client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks="default", **kwargs
                )
            else:
                response = self.client.messages.create(**kwargs)
        except anthropic.AuthenticationError as e:
            raise LLMError("Anthropic API rejected the API key.") from e
        except anthropic.PermissionDeniedError as e:
            raise LLMError("The API key has no access to this model.") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Rate limited by the Anthropic API; try again shortly.") from e
        except anthropic.BadRequestError as e:
            raise LLMError(f"Request rejected: {e.message}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Anthropic API error ({e.status_code}).") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Could not reach the Anthropic API.") from e

        usage = Usage.from_response(response.usage)
        served = getattr(response, "model", model) or model
        if served in self.config.prices:
            self.ledger.record(served, usage, purpose=purpose)
        else:
            self.ledger.record(model, usage, purpose=purpose)
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise LLMError(f"The model declined the request (category: {category}).")
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        return Completion(text=text, model=served, usage=usage, stop_reason=response.stop_reason)


def get_provider(
    config: Config, ledger: Ledger | None = None, *, api_key: str | None = None
) -> LLMProvider:
    if config.billing == "subscription":
        return ClaudeCLIProvider(config, ledger)
    return AnthropicAPIProvider(config, api_key, ledger)
