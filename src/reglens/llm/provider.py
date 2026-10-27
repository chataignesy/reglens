"""Thin LLM provider layer. Every call is logged to the usage ledger.

- `ClaudeCLIProvider` (billing: subscription): runs `claude -p` with no tools, so calls use the
  local Claude Code login. For the user's own development only.
- An Anthropic API provider (billing: api) follows with the bring-your-own-key demo.
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


def get_provider(config: Config, ledger: Ledger | None = None) -> LLMProvider:
    if config.billing == "subscription":
        return ClaudeCLIProvider(config, ledger)
    raise NotImplementedError("API provider (billing: api) arrives with the BYOK demo, Phase 2.")
