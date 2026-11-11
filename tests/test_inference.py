import concurrent.futures
import threading
import time

import pytest
from fastapi.testclient import TestClient

from reglens import inference
from reglens.index import embed as models
from reglens.inference_client import endpoint


def test_service_serializes_work_validates_identity_and_bounds(monkeypatch):
    monkeypatch.setenv("REGLENS_INFERENCE_GUARD_PORT", "0")
    monkeypatch.setattr(inference, "warmup", lambda: None)
    active = 0
    maximum = 0
    lock = threading.Lock()

    def compute(texts, **kwargs):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return [[0.0] * 1024 for _ in texts]

    monkeypatch.setattr(models, "local_embed", compute)
    with TestClient(inference.app) as client:
        assert client.get("/ready").json()["identity"] == models.model_identity()
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            responses = list(
                pool.map(lambda _: client.post("/embed", json={"texts": ["rule"]}), range(3))
            )
        assert all(r.status_code == 200 for r in responses) and maximum == 1
        assert client.post("/embed", json={"texts": ["rule"], "identity": {}}).status_code == 409
        assert client.post("/embed", json={"texts": ["x" * 200001]}).status_code == 422
        assert client.post("/rerank", json={"texts": ["rule"]}).status_code == 422
        # Queue exhaustion returns promptly, without entering model work.
        for _ in range(4):
            inference._admission.acquire()
        try:
            assert client.post("/embed", json={"texts": ["rule"]}).status_code == 429
        finally:
            for _ in range(4):
                inference._admission.release()


def test_endpoint_cannot_silently_use_remote_or_fallback(monkeypatch):
    monkeypatch.setenv("REGLENS_INFERENCE_URL", "https://example.com")
    with pytest.raises(ValueError):
        endpoint()
    monkeypatch.setenv("REGLENS_INFERENCE_URL", "http://127.0.0.1:8001")
    monkeypatch.setattr(
        "reglens.inference_client.request",
        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("offline")),
    )
    with pytest.raises(ConnectionError):
        models.embed(["rule"])
