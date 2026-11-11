from reglens.answer.research import completion_note, report


def test_checklist_distinguishes_unread_partial_and_delivered():
    data = {
        "research_checks": [
            {"aspect": "rule", "status": "evidence_found", "reason": "Read", "citations": ["C1"]},
            {
                "aspect": "exceptions",
                "status": "evidence_found",
                "reason": "Read",
                "citations": ["C2"],
            },
            {
                "aspect": "temporal",
                "status": "unresolved",
                "reason": "Missing interval",
                "citations": [],
            },
        ]
    }
    result = report(data, {"C1", "C2"}, {"C2"})
    assert result["checks"]["rule"]["status"] == "evidence_found"
    assert set(result["unresolved"]) == {"definitions", "exceptions", "applicability", "temporal"}
    assert "temporal: Missing interval" in completion_note(data)
    assert report({}, set())["unresolved"]
    assert completion_note({}) is None
