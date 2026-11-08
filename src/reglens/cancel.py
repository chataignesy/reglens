"""Cooperative cancellation for one question (review 2026-11-08: F5).

The HTTP API creates a `CancelToken` per request and sets it when the browser disconnects
(Stop, closed tab). Work stops at the next check: before every model call (both providers
check `provider.cancel`), at every progress event between steps and tool calls, and a running
`claude -p` subprocess is killed at once. In-process retrieval (milliseconds) is not
interrupted; an Anthropic API request already in flight finishes, but no further one starts.
"""

from __future__ import annotations

import subprocess
import threading
import time


class Cancelled(Exception):
    """The question was cancelled (client disconnected); no result is produced."""


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise Cancelled()


def cancellable_runner(token: CancelToken, poll_s: float = 0.25):
    """A `subprocess.run` stand-in for ClaudeCLIProvider that kills the process on cancel."""

    def run(cmd, *, input=None, timeout=None, cwd=None, env=None, encoding="utf-8", **_kw):
        token.check()
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding=encoding,
            cwd=cwd,
            env=env,
        )
        result: dict = {}
        reader = threading.Thread(
            target=lambda: result.update(
                zip(("out", "err"), proc.communicate(input), strict=True)
            ),
            daemon=True,
        )
        reader.start()
        start = time.monotonic()
        while reader.is_alive():
            reader.join(poll_s)
            if token.cancelled:
                proc.kill()
                reader.join(5)
                raise Cancelled()
            if timeout and time.monotonic() - start > timeout:
                proc.kill()
                reader.join(5)
                raise subprocess.TimeoutExpired(cmd, timeout)
        return subprocess.CompletedProcess(cmd, proc.returncode, result.get("out", ""),
                                           result.get("err", ""))

    return run
