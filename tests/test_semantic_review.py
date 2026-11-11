import json
from types import SimpleNamespace

import pytest

from reglens.answer.pipeline import Answer, Claim
from reglens.answer.review import review
from reglens.eval.artifacts import adjudicate, store


def test_semantic_contradiction_is_not_mechanical_success():
    ans = Answer("Q", False, "", "Rule [C1]", [Claim("Rule", ["C1"], "law")], [], "")
    data = {
        "claims": [{"index": 1, "status": "contradicted", "reason": "Exception omitted"}],
        "prose_alignment": "mismatch",
        "issues": ["Prose expands the claim"],
    }

    class Provider:
        def complete(self, *args, **kwargs):
            assert kwargs["purpose"] == "semantic_review"
            return SimpleNamespace(
                text=json.dumps(data), model="fake", usage=SimpleNamespace(total_tokens=12)
            )

    assert review(ans, Provider())["claims"][0]["status"] == "contradicted"
    assert ans.usage_tokens == 12
    data["claims"] = []
    assert review(ans, Provider())["status"] == "invalid"


def test_adjudication_binds_original_and_requires_reason(tmp_path):
    artifact = store(tmp_path, {"answer": "original"})
    before = artifact.read_bytes()
    path = adjudicate(
        artifact,
        reviewer="Reviewer",
        decision="rejected",
        reason="Wrong scope",
        directory=tmp_path / "reviews",
    )
    assert json.loads(path.read_text())["artifact_sha256"]
    assert artifact.read_bytes() == before
    with pytest.raises(ValueError):
        adjudicate(artifact, reviewer="", decision="accepted", reason="ok")
