"""Streamlit tab: coverage matrix of the synthetic Model Validation Policy against the
obligation register. Shows a precomputed run (`reglens gap`), so viewing costs no tokens."""

from __future__ import annotations

import io
import json
from pathlib import Path

import streamlit as st

from reglens.config import PROJECT_ROOT
from reglens.gap.evaluate import GAP_RESULTS
from reglens.gap.match import FINDINGS

DEMO_RESULT = PROJECT_ROOT / "docs" / "synthetic-policy" / "coverage-demo.json"
POLICY_URL = "docs/synthetic-policy/model-validation-policy.md"
COLUMNS = [
    "obligation_id", "status", "clauses", "rationale", "source", "obligation", "topic",
    "quote", "reviewer_status", "reviewer_comment",
]
LABELS = {
    "covered": "✅ covered", "partial": "🟡 partial", "missing": "🔴 missing",
    "contradicted": "⛔ contradicted", "not_applicable": "➖ not applicable",
    "other_document": "📄 other document", "unassessed": "❔ unassessed",
}


def _latest() -> Path | None:
    if DEMO_RESULT.exists():
        return DEMO_RESULT
    runs = sorted(GAP_RESULTS.glob("gap-*.json"))
    return runs[-1] if runs else None


def _xlsx(df) -> bytes | None:
    try:
        buf = io.BytesIO()
        df.to_excel(buf, index=False, sheet_name="Coverage matrix")
        return buf.getvalue()
    except ImportError:  # no Excel writer installed: CSV only
        return None


def gap_tab() -> None:
    import pandas as pd

    st.subheader("Policy gap analysis")
    st.caption(
        "A **synthetic** Model Validation Policy of the fictitious RegLens Demo Bank, checked "
        "against an obligation register extracted from the CRR, RTS, EBA guidelines and the ECB "
        "guide. Each verdict cites the policy clause and quotes it; quotes are verified in code."
    )
    path = _latest()
    if path is None:
        st.info("No gap analysis run yet. Run `reglens gap --yes` first.")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["rows"]
    df = pd.DataFrame(rows)
    df["clauses"] = df["clauses"].map(lambda c: ", ".join(c) if isinstance(c, list) else c)

    counts = df["status"].value_counts()
    cols = st.columns(6)
    for col, status in zip(cols, ["covered", "partial", "missing", "contradicted",
                                  "other_document", "not_applicable"], strict=True):
        col.metric(LABELS[status], int(counts.get(status, 0)))
    if data.get("recall") is not None:
        st.markdown(
            f"**Planted gaps found:** {data['recall']:.0%} of {data['gaps']} "
            f"(by type: {data['by_type']}); type accuracy {data['type_accuracy']:.0%}."
        )

    with st.expander("Planted gaps (answer key)"):
        for g in data.get("per_gap", []):
            mark = "✅" if g["found"] else "❌"
            st.markdown(f"{mark} **{g['id']}** ({g['type']}): `{g['statuses']}`")

    c1, c2, c3 = st.columns([2, 2, 3])
    statuses = c1.multiselect(
        "Status", list(LABELS), default=list(FINDINGS), format_func=LABELS.get
    )
    topics = c2.multiselect("Topic", sorted(df["topic"].unique()))
    text = c3.text_input("Search obligations", placeholder="e.g. probation, internal audit")
    view = df[df["status"].isin(statuses)]
    if topics:
        view = view[view["topic"].isin(topics)]
    if text:
        view = view[view["obligation"].str.contains(text, case=False, regex=False)]
    st.caption(f"{len(view)} of {len(df)} obligations")
    st.dataframe(
        view[COLUMNS].assign(status=view["status"].map(LABELS)),
        hide_index=True,
        use_container_width=True,
    )

    d1, d2 = st.columns(2)
    d1.download_button(
        "Download CSV", df[COLUMNS].to_csv(index=False).encode("utf-8-sig"),
        "coverage-matrix.csv", "text/csv",
    )
    if (xlsx := _xlsx(df[COLUMNS])) is not None:
        d2.download_button(
            "Download Excel (with reviewer columns)", xlsx, "coverage-matrix.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    st.caption(f"Policy text: `{POLICY_URL}` · results: `{path.name}`")
