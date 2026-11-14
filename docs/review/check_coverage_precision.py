"""Replay the eight fresh single drafts through the tightened guard, without model calls."""

import json
from copy import deepcopy
from pathlib import Path

from reglens.answer.research import guard
from reglens.answer.schema import parse_reply
from reglens.eval.fingerprint import SINGLE_FILES, code_hash
from reglens.index.db import connect
from reglens.retrieve.search import Hit


def main():
    baseline = json.loads(Path("docs/results/codex-completeness8-2026-11-14.json").read_text())
    run = json.loads(Path(baseline["result_path"]).read_text())
    drafts = []
    for call in run["calls"]:
        if call["purpose"] == "answer":
            artifact = json.loads(Path(call["artifact"]).read_text())
            data, problems = parse_reply(artifact["response"]["text"])
            assert not problems
            drafts.append(data)
    rows = []
    with connect() as conn:
        for item in baseline["items"]:
            path = next(a["artifact"] for a in item["entry"]["attempt_artifacts"]
                        if a["mode"] == "single")
            stored = json.loads(Path(path).read_text())
            text = {e["id"]: e["text"] for e in stored["evidence"]}
            hits = [Hit(**h, text=text[h["id"]]) for h in stored["context"]]
            raw = next(d for d in drafts if d["answer"] == stored["answer"])
            data = deepcopy(raw)
            gaps = guard(item["question"], data, hits, conn=conn)
            rows.append({"id": item["id"], "old_missing_info": stored["missing_info"],
                         "new_missing_info": data.get("missing_info", False), "gaps": gaps})
    by_id = {r["id"]: r for r in rows}
    assert by_id["dod-005"]["gaps"] and by_id["dod-005"]["new_missing_info"]
    assert not by_id["mh-012"]["gaps"] and not by_id["mh-012"]["new_missing_info"]
    for cid in ["app-001", "lgd-007", "val-001", "app-004"]:
        assert not by_id[cid]["gaps"]
    assert by_id["lom-001"]["gaps"] and by_id["irb-007"]["gaps"]
    output = {"basis": "raw provider drafts before the old guard mutated gap flags; no model calls",
              "answer_code_hash": code_hash(SINGLE_FILES), "items": rows}
    path = Path("docs/review/coverage-precision-local-2026-11-14.json")
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({r["id"]: {"old": r["old_missing_info"], "new": r["new_missing_info"]}
                      for r in rows}))


if __name__ == "__main__":
    main()
