"""Bounded loopback-only client for the optional single-owner inference service."""

from __future__ import annotations

import json
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def endpoint() -> str | None:
    value = os.environ.get("REGLENS_INFERENCE_URL")
    if not value:
        return None
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("REGLENS_INFERENCE_URL must be a loopback HTTP origin")
    return value.rstrip("/")


def request(path: str, payload: dict | None = None, *, timeout: float = 90):
    base = endpoint()
    if not base:
        raise RuntimeError("No shared inference endpoint configured")
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        raw = response.read(8_000_001)
        if len(raw) > 8_000_000:
            raise ValueError("Inference response exceeds size limit")
        return json.loads(raw)


def ready() -> dict:
    return request("/ready", timeout=5)
