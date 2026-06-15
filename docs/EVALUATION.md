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

| Q#  | User  | Question (summary)                                    | Status | Trajectory | Faithful | Reasonable |
|-----|-------|-------------------------------------------------------|--------|------------|----------|------------|
| Q1  | alice | Tell me about Globex                                  | PASS   | PASS       | —        | —          |
| Q2  | alice | What are Globex's open issues?                        | PASS   | PASS       | —        | —          |
| Q3  | bob   | Full details of Globex's critical issue               | PASS   | PASS       | 0.92     | —          |
| Q4  | bob   | Summarise escalation risk for Globex                  | PASS   | PASS       | 0.79     | —          |
| Q5  | carol | Create next action for Globex's critical issue        | PASS   | PASS       | —        | 5/5        |
| Q6  | alice | Create next action (RBAC block — sales_user)          | PASS   | PASS       | —        | —          |
| Q7  | carol | What is the weather in London? (out of scope)         | PASS   | PASS       | —        | —          |
| Q8  | alice | Tell me about FooBar Inc (not found)                  | PASS   | PASS       | —        | —          |
| Q9  | carol | Recommend next action for Globex's DB issue           | PASS   | PASS       | 0.79     | 3/5        |
| Q10 | bob   | Log issue update for Globex's critical issue          | PASS   | PASS       | —        | —          |
| Q11 | alice | What customers do we have? (no-tool case)             | PASS   | PASS       | —        | —          |
| Q12 | carol | Multi-turn: switch to Wonka Industries' open issues   | PASS   | PASS       | 0.82     | —          |

## Commentary

**Trajectory (12/12):** The agent called the right tools in the right order on every case, including the RBAC guardrail (Q6), the propose-then-confirm flow (Q9), and the multi-turn context switch (Q12).

**Faithfulness (0.79–0.92):** All grounded cases scored above the 0.7 threshold. Q3 scored highest (0.92) — a detailed issue lookup with a direct, fact-dense answer. Q4 and Q9 scored 0.79 — the escalation summary involves some LLM synthesis on top of retrieved facts, which RAGAS penalises slightly even when the synthesis is accurate.

**Reasonableness:** Q5 scored 5/5 — the agent's next-action recommendation (escalate to CTO within 1 hour) matched the issue severity well. Q9 scored 3/5 — the escalation proposal was reasonable but lacked specificity about timeline and owner, which the judge penalised.

**Known limitation:** RAGAS faithfulness can be unreliable on negation/absence (e.g. a correct "no such customer" answer) and occasionally returns `NaN` on a judge sub-call error; both are treated as *not scored* rather than a grounding fail.

## What this eval does not cover

This is a focused suite, not exhaustive coverage. Known gaps:

- **Scale and concurrency** — all cases run sequentially. Behaviour under concurrent load is untested.
- **Adversarial inputs** — no prompt-injection or jailbreak attempts against the RBAC layer.
- **Faithfulness on absence** — RAGAS is unreliable when the correct answer is a negation ("no such customer"), so not-found cases rely on trajectory, not faithfulness.
- **Judge reliability** — the reasonableness judge is a single LLM call, not validated against human labels. For anything I'd stake a decision on, I'd calibrate it against a handful of human-scored examples first.
- **Determinism** — RAGAS and the judge are LLM-based, so scores vary slightly between runs. Thresholds, not exact values, are what's checked.
