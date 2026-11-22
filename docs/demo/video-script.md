# RegLens — demo video script (≈ 3 minutes)

For a screen recording of the local Next.js web UI, posted natively on LinkedIn. Answers are
generated live, so the wording will differ from run to run; the facts should not.

**Type every question on camera.** None of the demo questions is among the clickable examples on
the Ask page (`src/reglens/ui/content.py`), so the demo does not look staged; keep it that way.

**Why these questions (picked 15 Nov 2026).** Each scored *fully correct* (2/2) in all three saved
runs on the frozen 118-question set (Claude 13 Nov full run and rerun, Codex 14 Nov):

| Scene | Question ID | Evidence |
|---|---|---|
| 2 | `lgd-001` | 2/2 in all 3 runs and in all 3 smoke-30 gradings; always routed to *Quick* |
| 3 | `mh-002` | 2/2 in all 3 runs, always routed to the agent; correct in the 15 Nov dry run |
| 4 | `oos-007` | declined in all 3 runs and in the 15 Nov dry run |

The previous scene-2 question (*PD input floors for retail*, `pd-002`) scored only *partial* in two
of the three runs, which matches the awkward extra paragraph seen in the dry run. Backups with the
same record: `pd-001` (*What is the PD input floor for IRB corporate exposures under CRR3?*) for
scene 2, `oos-009` (*When should a loan move to stage 2 under IFRS 9?*) for scene 4.

## Before recording

1. Start four processes, each in its own terminal from the repository root (details in the
   README, *Start the web UI*):
   - database: `docker compose up -d`
   - shared inference (embedding model + reranker, one GPU owner; needed so research-agent
     subprocesses do not each load the models):
     `uv run uvicorn reglens.inference:app --host 127.0.0.1 --port 8001 --workers 1`
   - API, with `$env:REGLENS_INFERENCE_URL='http://127.0.0.1:8001'` set in that terminal:
     `uv run uvicorn reglens.api.app:app --port 8000`
   - web UI, in `web/`: `npm run dev` and open http://localhost:3000. If Windows has reserved
     port 3000 (`netsh int ipv4 show excludedportrange protocol=tcp`), use
     `npm run dev -- -p 3200` and open http://localhost:3200.
2. **Warm up:** wait until http://localhost:8000/api/ready reports `"ready": true`, then ask one
   throwaway question (the first answer takes noticeably longer).
3. **Model access:** use "Local subscription", so no API key appears on screen. If you
   use your own key instead, enter it before you start recording. Leave *Legal application
   date* empty and institution type on *Any*: the current corpus has no verified date or SI/LSI
   metadata until it is re-indexed, so setting them shows "not verified" notes.
4. **Window:** browser at 1920×1080, zoom 110–125 % so text is readable on a phone; close other
   tabs; hide bookmarks and notifications (Windows: Focus assist on).
5. **Dry run** each question once; if an answer comes out weaker than usual, simply ask it again.
6. **Recorder:** Windows Game Bar (`Win + Alt + R`) or OBS Studio; record at 1080p, 30 fps.
   Record each scene separately and cut them together; keep the voice-over close to the lines
   below.

## Scenes

### 1. Opening (≈ 10 s)
**Show:** the RegLens start page with the disclaimer visible.
**Say:** "This is RegLens, a personal open-source assistant for EU credit risk regulation:
the CRR including CRR3, the RTS, EBA guidelines and Q&A, and the ECB guide to internal models.
Every answer has to show where it comes from."

### 2. A quick factual question (≈ 30 s)
**Answering:** Quick. **Ask:** *What LGD input floors apply to retail exposures under CRR3?*
**Show:** the live steps (searched the corpus, drafting) → the answer (unsecured: QRRE 50 %, other
retail 30 %; secured by residential property 5 %; other retail secured by financial collateral
0 %, receivables 10 %, immovable property 10 %, other physical collateral 15 %) → click a
citation badge to open its source (CRR Art. 164(4), Table 1, labelled *law*)
→ the "Answered … from" line (source versions) → "Mechanical citation checks: all claims passed" (say what it does not check).
**Say:** "Each claim cites the exact article, is labelled law, supervisory expectation or
interpretation, and the as-of line says which consolidated version the answer is based on.
Before I see the answer, code checks that every claim cites a passage it was given and that
its numbers are actually in that passage."

### 3. A real-world scenario (≈ 60 s)
**Answering:** Auto. **Ask:** *In a jurisdiction where the competent authority set the retail
materiality threshold at EUR 100 and 1%, a retail obligor owes EUR 120 past due, which is 3% of
its exposure, for 95 days, then pays it off. Is it in default, and when can it return to
non-default?*
**Show:** the live timeline: "Needs several provisions: research agent", then each tool call as
it happens (in the dry run: two searches, for the materiality threshold and for the probation
period; the steps vary between runs). The agent takes 30 s to 2 min; cut the wait in editing. Then the answer: in default,
both components exceeded and more than 90 days; return to non-default only after at least
three months' probation → the assumption it flags as *interpretation*.
**Say:** "Questions like this need several provisions. A small model routes it to an agent that
reads the article, follows the references and searches the EBA guidelines, with a hard limit on
its steps. Note that it states its own assumptions as interpretation, not as law."

### 4. Knowing what it doesn't know (≈ 15 s)
**Ask:** *What is the minimum leverage ratio requirement for EU banks?*
**Show:** the "not answered from the RegLens corpus" message.
**Say:** "Leverage is outside the credit risk scope, so it declines, even though the article
that sets the leverage ratio happens to be in the corpus."

### 5. Policy gap analysis (≈ 40 s)
**Show:** the **Policy gap analysis** page with **"Committed demo run (synthetic policy)"** selected
in the run picker (by default the page opens the newest *local* run) → the verdict counts and
"planted gaps found 100 %"
→ click the *partial* and *missing* cards to hide them (only *contradicted* stays) and search
*previously defaulted* → click the row (OB-0218 in the demo run; the register now uses stable
content IDs and keeps OB-0218 as a legacy alias), from the EBA
guideline on return to non-default: the policy's §7.4 says one month, the guideline requires at
least three → the Excel download with reviewer columns. (Other good rows: search *internal
audit* for the three-year audit cycle vs annually, or *large corporates* for own LGD estimates.)
**Say:** "The second use case: a synthetic validation policy of a fictitious bank, checked
against 720 obligations extracted from the regulation. Every verdict quotes the policy clause it
relies on. Fifteen deficiencies were planted in this policy, and it finds all of them. The
output is a matrix for a reviewer to sign off, not a final judgement."

### 6. Close (≈ 15 s)
**Show:** the README results table on GitHub (or a title card).
**Say:** "On a reviewed set of 118 development questions, automated grading gives it 86 percent
on the 103 in scope, and it declines all 15 out-of-scope ones. It was built on a deliberately
small budget. It's open source, and the tools also run as an MCP server inside Claude. Not
legal advice: always check the official texts."
**On-screen caption (required with the number):** "Frozen 118-question development set,
14 Nov 2026 · answers by GPT-6.1 via the Codex CLI backend · automated LLM grading, not
independent review."

**Note on the headline result (decided 15 Nov 2026: use the Codex runs for now).** Source: the
full Codex run on the frozen 118-question set ([results](../results/codex-frozen118-2026-11-14.md)):
86.4% mean in-scope score, 76 full / 26 partial / 1 wrong, 15/15 out-of-scope refusals. It is
the broadest Codex measurement; the routing14 (92.3%) and smoke30 runs cover far fewer
questions. The video itself shows Claude answering, so the caption must name the benchmark
model; the run predates the completeness fixes, and the set has been used for development.
Replace with a Claude measurement on the current code once one exists.

## Optional scene: MCP in Claude Desktop (≈ 30 s)
Add the RegLens MCP server to Claude Desktop (`uv run python -m reglens.agent.mcp_server`) and
ask Claude a question that uses the `search` and `get_article` tools. Only include it if the
setup is already working; the main video stands without it.

## Dry run — 15 Nov 2026 (merged code, Claude subscription, web UI)

All four services as above; web UI on a non-3000 port. 57,260 tokens in total (ledger).

| Scene | Result | Time · tokens | Watch for |
|---|---|---|---|
| 2 Quick (old question, `pd-002`) | ✅ 0,05 % / 0,1 % QRRE revolvers; Art. 163(1) *law*; 4/4 checks passed | 18 s · 11k | Also added an Art. 159a guarantee exception with a hedging sentence; question since replaced by `lgd-001` |
| 2 Quick (`lgd-001`, re-run same day) | ✅ every Table 1 floor matches the reference; Art. 164(4), 164(4a), 161(6) *law*; 9/9 checks passed | ~20 s · 12k | Longer answer (application rules, Art. 159a guarantee carve-out, Art. 164(6)–(7) higher floors); all correct, so scroll slowly or zoom on the floor list in editing |
| 3 Auto | ✅ routed to agent; default yes (both components > threshold, 95 ≥ 90 days); return after ≥ 3 months, ECB reset; assumptions stated; 5/5 checks | 28 s · 29k | EBA GL para. 71(a)–(e) citations showed as raw `[…]` text, not badges; fixed afterwards (multi-digit bracket keys, `agent/run.py`), not yet re-run live |
| 4 Out of scope | ✅ declined; mentions Art. 92 also lists the leverage ratio | 16 s · ~17k | — |

The "Semantic evidence assessment" and "Research checks still unresolved" status lines that
appeared under each answer have since been removed from the web UI (15 Nov 2026).

## After recording

- Add captions (most LinkedIn viewers watch muted).
- Keep the disclaimer visible in scene 1 and in the post text.
- Link the GitHub repository in the post once it is public.
