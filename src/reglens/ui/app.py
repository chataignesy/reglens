"""RegLens Streamlit UI v0.  Run: uv run streamlit run src/reglens/ui/app.py

Two ways to call the model:
- Your Anthropic API key (bring-your-own-key, for the public demo). The key lives only in this
  browser session's state, is passed to the Anthropic SDK client, and is never logged or stored.
- Local Claude subscription (`claude -p`), shown only when `billing: subscription` is configured.
"""

from __future__ import annotations

from dataclasses import replace

import streamlit as st

from reglens.answer.pipeline import LEVEL_LABEL, answer_question
from reglens.answer.verify import check_answer
from reglens.config import load_config
from reglens.llm.provider import AnthropicAPIProvider, ClaudeCLIProvider, LLMError
from reglens.retrieve.search import Filters

DISCLAIMER = (
    "Personal open-source project — not affiliated with any employer, supervisor or regulator. "
    "Not legal or regulatory advice; always check the official texts."
)
EXAMPLES = [
    "What is the PD input floor for IRB corporate exposures under CRR3?",
    "How long is the probation period after distressed restructuring?",
    "Which discount rate should be used to calculate realised LGD?",
    "What output floor factor applies in 2026?",
    "Can a bank use own LGD estimates for a large corporate under A-IRB?",
]
DEPTHS = {"Auto": "auto", "Quick (single pass)": "single", "Deep (agent)": "agent"}


@st.cache_resource
def _conn():
    from reglens.index import db

    return db.connect()


@st.cache_resource
def _warm_models():
    """Load embedding and reranker models once per server process."""
    from reglens.index.embed import embedder, reranker

    embedder()
    reranker()
    return True


def _sidebar(cfg):
    st.sidebar.header("Model access")
    options = ["Your Anthropic API key"]
    if cfg.billing == "subscription":
        options.append("Local Claude subscription")
    mode = st.sidebar.radio("Call Claude with", options)
    key = None
    if mode == "Your Anthropic API key":
        key = st.sidebar.text_input(
            "Anthropic API key",
            type="password",
            help="Used only for this session's requests to the Anthropic API; never stored.",
        )
    st.sidebar.header("Answering")
    depth = st.sidebar.radio(
        "Mode",
        list(DEPTHS),
        help="Auto: a small model decides whether the question needs several provisions. "
        "Deep: the agent searches, follows cross-references and reads definitions (more tokens).",
    )
    st.sidebar.header("Filters")
    applies = st.sidebar.selectbox(
        "Institution type", ["any", "SI", "LSI"], help="Applied in quick mode."
    )
    st.sidebar.caption(f"Model: `{cfg.model((cfg.answer or {}).get('tier', 'dev'))}`")
    return mode, key, DEPTHS[depth], None if applies == "any" else applies


def _provider(cfg, mode, key):
    if mode == "Local Claude subscription":
        return ClaudeCLIProvider(cfg)
    if not key:
        return None
    return AnthropicAPIProvider(replace(cfg, billing="api"), api_key=key)


def _answer(depth, provider, cfg, question, applies):
    if depth == "agent":
        from reglens.agent.run import answer_agentic

        return answer_agentic(_conn(), provider, cfg, question)
    if depth == "auto":
        from reglens.answer.route import answer_routed

        return answer_routed(_conn(), provider, cfg, question)
    return answer_question(_conn(), provider, cfg, question, filters=Filters(applies_to=applies))


def _show(ans, check):
    if ans.abstained:
        st.warning(f"**Not answered from the RegLens corpus.** {ans.abstain_reason}")
    elif ans.errors:
        st.error("; ".join(ans.errors))
    else:
        st.markdown(ans.answer)
    st.caption(ans.as_of)

    cited = ans.cited_hits()
    if cited:
        st.subheader("Sources")
        for i, h in enumerate(ans.context, 1):
            if h in cited:
                source = h.text.split(" › ", 1)[0]
                level = LEVEL_LABEL.get(h.legal_level, h.legal_level)
                with st.expander(f"[C{i}] {source} {h.ref} — {level}"):
                    st.text(h.text)
    if ans.claims:
        ok, n = check["ok"], check["claims"]
        label = f"Citation check: {ok}/{n} claims supported"
        with st.expander(label, expanded=ok < n):
            for c in ans.claims:
                icon = "✅" if c.check == "ok" else "⚠️"
                st.markdown(f"{icon} *{c.kind}* — {c.text} `{', '.join(c.citations)}`"
                            + ("" if c.check == "ok" else f" — **{c.check}**"))
    steps = [t for t in ans.trace if t.get("tool") not in ("route", "answer")]
    if steps:
        with st.expander(f"Research steps: {len(steps)} tool calls"):
            for t in steps:
                args = ", ".join(repr(a) for a in t.get("args", []) if a not in (None, ""))
                st.markdown(f"`{t['tool']}({args})` → {len(t.get('keys', []))} passages")
    route = next((t for t in ans.trace if t.get("tool") == "route"), None)
    if ans.usage_tokens:
        mode = f" · routed to {route['route']}" if route else ""
        st.caption(f"{ans.model} · {ans.usage_tokens:,} tokens{mode}")


def _ask_tab(cfg, mode, key, depth, applies) -> None:
    example = st.selectbox("Examples", ["—"] + EXAMPLES)
    question = st.text_area(
        "Your question", value="" if example == "—" else example, height=90,
        placeholder="e.g. Which LGD input floors apply to retail exposures?",
    )
    if not st.button("Ask", type="primary", disabled=not question.strip()):
        return
    provider = _provider(cfg, mode, key)
    if provider is None:
        st.error("Enter your Anthropic API key in the sidebar, or use the local subscription.")
        return
    with st.spinner("Searching the corpus and drafting a cited answer…"):
        _warm_models()
        try:
            ans = _answer(depth, provider, cfg, question.strip(), applies)
        except LLMError as e:
            st.error(str(e))
            return
    _show(ans, check_answer(ans))


def main() -> None:
    st.set_page_config(page_title="RegLens", page_icon="⚖️", layout="wide")
    cfg = load_config()
    st.title("RegLens")
    st.caption(
        "Grounded answers on EU credit risk regulation — CRR3, RTS, EBA guidelines, ECB guide."
    )
    st.info(DISCLAIMER)

    mode, key, depth, applies = _sidebar(cfg)
    ask, gap = st.tabs(["Ask", "Policy gap analysis"])
    with ask:
        _ask_tab(cfg, mode, key, depth, applies)
    with gap:
        from reglens.ui.gap_view import gap_tab

        gap_tab()


if __name__ == "__main__" or st.runtime.exists():
    main()
