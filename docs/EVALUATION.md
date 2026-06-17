# Evaluation Results

## Setup

The eval harness runs 12 test cases covering the full agent surface: customer lookups, issue queries, escalation summaries, next-action creation, RBAC enforcement, out-of-scope questions, not-found handling, and multi-turn conversations.

Each case is scored on up to three dimensions:

- **Trajectory** — expected tools must appear in the right order (ordered subsequence; extra/interleaved calls allowed). RBAC enforcement (`guardrail_blocked`) and propose-then-confirm cases have dedicated gating on top.
- **Faithfulness** (RAGAS) — is the answer supported by the agent's tool outputs? Applied only to read queries; skipped for RBAC-blocked cases, no-tool cases, and write confirmations.
- **Reasonableness** — LLM-judge rubric (1–5) on the agent's recommended next action vs. the issue facts it retrieved. Applied to Q5 and Q9 only.

## Results (12/12 passing)

Run: `docker compose run --rm -e RAGAS_ENABLED=true eval`  
Judge model: `gpt-4o`

| Q#  | User  | Question (summary)                                    | Status | Trajectory | Faithful | Reasonable | Cost      |
|-----|-------|-------------------------------------------------------|--------|------------|----------|------------|-----------|
| Q1  | alice | Tell me about Globex                                  | PASS   | PASS       | 1.00     | —          | $0.000766 |
| Q2  | alice | What are Globex's open issues?                        | PASS   | PASS       | 1.00     | —          | $0.000740 |
| Q3  | bob   | Full details of Globex's critical issue               | PASS   | PASS       | 1.00     | —          | $0.001607 |
| Q4  | bob   | Summarise escalation risk for Globex                  | PASS   | PASS       | 1.00     | —          | $0.000717 |
| Q5  | carol | Create next action for Globex's critical issue        | PASS   | PASS       | —        | 5/5        | $0.001225 |
| Q6  | alice | Create next action (RBAC block — sales_user)          | PASS   | PASS       | —        | —          | $0.000694 |
| Q7  | carol | What is the weather in London? (out of scope)         | PASS   | PASS       | —        | —          | $0.000211 |
| Q8  | alice | Tell me about FooBar Inc (not found)                  | PASS   | PASS       | —        | —          | $0.000408 |
| Q9  | carol | Recommend next action for Globex's DB issue           | PASS   | PASS       | 0.81     | 5/5        | $0.001027 |
| Q10 | bob   | Log issue update for Globex's critical issue          | PASS   | PASS       | —        | —          | $0.001135 |
| Q11 | alice | What customers do we have? (no-tool case)             | PASS   | PASS       | —        | —          | $0.000208 |
| Q12 | carol | Multi-turn: switch to Wonka Industries' open issues   | PASS   | PASS       | 0.90     | —          | $0.000875 |

Total agent cost across the suite: **$0.009613** (judge/RAGAS calls excluded).

## Commentary

**Trajectory (12/12):** The agent called the right tools in the right order on every case, including the RBAC guardrail (Q6), the propose-then-confirm flow (Q9), and the multi-turn context switch (Q12).

**Faithfulness (0.81–1.00):** All grounded cases passed the 0.7 threshold. Q1–Q4 scored a perfect 1.00. Q9 (0.81) and Q12 (0.90) sit lower — both add some synthesis on top of the retrieved facts. Scores shift run-to-run since the judge is an LLM, so treat them as above threshold, not exact.

**Reasonableness:** Both Q5 and Q9 scored 5/5 — the next-action recommendations (e.g. escalate to CTO within 1 hour) matched issue severity well, with specific timelines and owners.

**Known limitation:** RAGAS faithfulness can be unreliable on negation/absence (e.g. a correct "no such customer" answer) and occasionally returns `NaN` on a judge sub-call error; both are treated as *not scored* rather than a grounding fail.

## What this eval does not cover

This is a focused suite, not exhaustive coverage. Known gaps:

- **Scale and concurrency** — all cases run sequentially. Behaviour under concurrent load is untested.
- **Adversarial inputs** — no prompt-injection or jailbreak attempts against the RBAC layer.
- **Faithfulness on absence** — RAGAS is unreliable when the correct answer is a negation ("no such customer"), so not-found cases rely on trajectory, not faithfulness.
- **Judge reliability** — the reasonableness judge is a single LLM call, not validated against human labels. For anything I'd stake a decision on, I'd calibrate it against a handful of human-scored examples first.
- **Determinism** — RAGAS and the judge are LLM-based, so scores vary slightly between runs. Thresholds, not exact values, are what's checked.
