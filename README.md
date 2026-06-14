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
| `litellm`    | 4000 | LLM proxy (OpenAI / Anthropic)               |
| `postgres`   | 5432 | Primary database                             |
| `redis`      | 6379 | Conversation history cache                   |

## Quickstart

**1. Copy env and fill in your API keys**

```bash
cp .env.example .env
# Edit .env — add OPENAI_API_KEY (required) and optionally ANTHROPIC_API_KEY
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
| `ANTHROPIC_API_KEY`   | Optional — only needed if switching to Claude    |
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

```bash
python eval/run_eval.py
```
