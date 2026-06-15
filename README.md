# Agentic Support Assistant

A role-aware enterprise support agent built with LangGraph, FastAPI, and MCP. Agents look up customers and issues, draft escalation summaries, and record next actions — all scoped to the caller's Keycloak role.

## Architecture

```
ui/          React + TypeScript frontend
api/         FastAPI backend — auth, routers, LangGraph agent, Alembic migrations
mcp_server/  MCP tool server — customer/issue queries and writes against Postgres
infra/       Docker configs for Keycloak, LiteLLM, and Postgres
```

**Services (Docker Compose)**

| Service      | Port | Purpose                                      |
|--------------|------|----------------------------------------------|
| `api`        | 8000 | FastAPI app + LangGraph agent                |
| `ui`         | 3000 | React frontend                               |
| `mcp_server` | 8001 | MCP tool server                              |
| `keycloak`   | 8080 | Auth & RBAC (`sales_user`, `support_user`, `admin`) |
| `litellm`    | 4000 | LLM proxy (OpenAI)                           |
| `postgres`   | 5432 | Primary database                             |
| `redis`      | 6379 | Conversation history cache                   |

## Quickstart

**1. Copy env and fill in your API keys**

```bash
cp .env.example .env
# Edit .env — add OPENAI_API_KEY
```

**2. Start all services**

```bash
docker compose up -d
```

This runs migrations and seeds dev data automatically via the `migrate` service.

**3. Open the UI**

Visit `http://localhost:3000`. Log in with a Keycloak user from `infra/keycloak/acme-realm.json`.

## Local development (without Docker)

Start dependencies first:

```bash
docker compose up -d postgres keycloak redis litellm mcp_server
```

Then run the API:

```bash
cd api
pip install -r requirements.txt
uvicorn main:app --reload
```

## Database migrations

```bash
cd api && alembic upgrade head   # apply migrations
cd api && python db/seed.py      # seed dev data
```

When running via Docker, always rebuild the migrate image after schema changes:

```bash
docker compose run --build --rm migrate
docker compose up -d --no-deps --force-recreate api mcp_server
```

## Agent roles

| Role           | Capabilities                                                   |
|----------------|----------------------------------------------------------------|
| `sales_user`   | Read customers and issues                                      |
| `support_user` | Read + create escalation summaries, add issue updates, record recommendations |
| `admin`        | All of the above + create next actions                         |

## Environment variables

See `.env.example` for all variables. Key ones:

| Variable              | Description                                      |
|-----------------------|--------------------------------------------------|
| `OPENAI_API_KEY`      | Required — used by LiteLLM proxy                |
| `LITELLM_MODEL`       | Model name passed to LiteLLM (default: `gpt-4o-mini`) |
| `LANGSMITH_API_KEY`   | Optional — enables LangSmith tracing             |
| `LANGSMITH_TRACING`   | Set to `true` to enable tracing                  |

## Tests

```bash
python tests/test_api.py
python tests/test_agent.py
python tests/test_auth.py
python tests/test_mcp.py
```

## Eval

Run it in Docker — **no host Python or venv needed** (just `docker compose up` first):

```bash
# fast: trajectory only (~1 min, no judge calls)
docker compose run --rm eval

# full: trajectory + grounding + reasonableness (judge-LLM calls, slower)
docker compose run --rm -e RAGAS_ENABLED=true eval
```

Results print as a `Q# | Status | Trajectory | Faithful | Reasonable | …` table and
are written to `eval/results.json` (with the judge's per-case rationale).

The harness scores each case on three dimensions:

- **Trajectory** — expected tools must appear in the right order (ordered
  subsequence; extra/interleaved calls allowed). RBAC enforcement
  (`guardrail_blocked`) and propose-then-confirm cases keep their dedicated
  gating on top.
- **Grounding** — RAGAS faithfulness: is the answer supported by the agent's
  tool outputs (read from `agent_actions`)? Applied only to **read** queries —
  skipped for RBAC-blocked cases, no-tool cases, and write confirmations (whose
  text echoes the user's request, not retrieved data).
- **Recommendation reasonableness** — a rubric LLM-judge (1–5) on the agent's
  recommended next action vs. the issue facts it retrieved. Applied to the
  recommendation cases (Q5's recorded action, Q9's escalation proposal). Not
  applied to issue-update logging (e.g. Q10), which is not a recommendation.

Both judge-based dimensions are **optional and off by default** (`RAGAS_ENABLED`,
so dev runs stay fast). The eval runs in its own container/venv so the judge
stack (ragas + langchain) never touches the app's langgraph stack.

Running it locally without Docker (for development) instead:

```bash
python -m venv eval/.venv && eval/.venv/bin/pip install -r eval/requirements.txt
RAGAS_ENABLED=true eval/.venv/bin/python eval/run_eval.py
```

**Judge model.** Faithfulness and reasonableness are scored by a judge model
(`EVAL_JUDGE_MODEL`) via LiteLLM. The default is **`gpt-4o`** — reproducible
with the required OpenAI key and the most reliable pairing with RAGAS. The judge
is a noisy estimator — validate against a few human labels before trusting it
for anything high-stakes.

**Known limitation.** RAGAS faithfulness can be unreliable on negation/absence
(e.g. a correct "no such customer" answer) and occasionally returns `NaN` on a
judge sub-call error; both are treated as *not scored* rather than a grounding
fail, and the case is flagged rather than special-cased.
