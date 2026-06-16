# Agentic Support Assistant

A role-aware enterprise support agent built with LangGraph, FastAPI, and MCP. Agents look up customers and issues, draft escalation summaries, and record next actions — all scoped to the caller's Keycloak role.

## Deliverables

| | |
|---|---|
| **Eval results** | [docs/EVALUATION.md](docs/EVALUATION.md) |
| **AI usage notes** | [docs/AI_USAGE.md](docs/AI_USAGE.md) |

## Architecture

![Architecture diagram](docs/architecture.png)

**Folder structure**

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

Visit `http://localhost:3000` and log in with one of the test users below.

## Try it

**Test users**

| Username | Password    | Role           | Can do                                      |
|----------|-------------|----------------|---------------------------------------------|
| alice    | password123 | `sales_user`   | Read customers and issues                   |
| bob      | password123 | `support_user` | Read + write escalation summaries & updates |
| carol    | password123 | `admin`        | All of the above + create next actions      |

![UI screenshot](docs/screenshot.png)

**Sample queries to try**

- `What are Globex's open issues?`
- `Give me the full details of Globex's critical issue`
- `Summarise the escalation risk for Globex`
- `Create a next action for Globex's critical issue: escalate to CTO within 1 hour` _(log in as carol)_

## Agent and tools

The agent is implemented with LangGraph. On each turn it receives the user's message, inspects its available tools, and decides which to call — there is no hard-coded routing. Tools are selected dynamically based on the query.

**Available tools (all served by the MCP server)**

| Tool | Description | Roles |
|------|-------------|-------|
| `get_customer_profile` | Look up a customer by name (exact then prefix match) | all |
| `get_open_issues` | Retrieve all open issues for a customer | all |
| `get_issue_detail` | Full issue detail including update history | all |
| `create_escalation_summary` | LLM-generated risk summary and escalation assessment (Skill) | support, admin |
| `add_issue_update` | Log a progress note on an issue | support, admin |
| `record_recommendation` | Record the outcome of a proposed next action | support, admin |
| `create_next_action` | Persist a recommended next action for an issue | admin only |

The agent follows a propose-then-confirm pattern for write operations: it surfaces a recommendation and waits for explicit user confirmation before calling any write tool.

### Streaming (`POST /chat/stream`)

The API streams the agent's response as Server-Sent Events. Three event types are emitted:

| Event | Payload | When |
|-------|---------|------|
| `status` | `{ "status": "..." }` | Each tool call in progress (e.g. "Pulling up issue details...") |
| `token` | `{ "content": "..." }` | Each LLM output token as it arrives |
| `error` | `{ "message": "..." }` | In-band error if the agent fails mid-stream (HTTP status stays 200) |

The UI subscribes to this stream and renders tool activity and the answer incrementally.

## MCP (Model Context Protocol)

All tools are served by a dedicated MCP server (`mcp_server/`, port 8001) over HTTP using the streamable-HTTP transport. The FastAPI agent connects to it at startup and discovers tools dynamically — the agent code has no knowledge of what tools exist or how they work.

**Why MCP here:**
- **Separation of concerns** — tool definitions, SQL queries, and business logic live in `mcp_server/`, not in the agent. The agent is a pure orchestrator.
- **Independent deployability** — the MCP server can be updated, scaled, or replaced without touching the agent.
- **RBAC at the tool boundary** — every tool call carries the caller's role. Permission checks happen inside the MCP server, making it impossible for the agent to bypass them regardless of what the LLM decides to do.

## Skills

The **Customer Escalation Summary** is implemented as a reusable skill in `mcp_server/server.py` (`create_escalation_summary`). It is not a single prompt call — it is a structured workflow:

1. Fetches all open issues for the customer from Postgres, including their full update history
2. Renders a structured prompt from the retrieved data
3. Calls the LLM to produce a validated JSON response
4. Validates the output against a Pydantic schema (`EscalationSummary`)
5. Returns four structured fields: `summary`, `risk_level`, `recommendation`, `missing_info`

The recommendation field is stripped from the response for non-admin callers at the MCP layer — the agent never sees it and cannot surface it.

## Authentication (Keycloak)

Keycloak runs in Docker Compose (port 8080). The login flow:

1. The UI posts credentials to `POST /auth/login` on the FastAPI backend
2. FastAPI exchanges them with Keycloak using the Resource Owner Password flow
3. Keycloak returns a signed JWT; FastAPI forwards it to the UI
4. All subsequent API calls carry the JWT as a Bearer token
5. FastAPI validates the JWT signature against Keycloak's JWKS endpoint and extracts the role claim
6. The role is passed to every MCP tool call — RBAC is enforced at the tool level, not just the API gateway

**Roles**

| Role           | Capabilities                                                   |
|----------------|----------------------------------------------------------------|
| `sales_user`   | Read-only access to customer and issue data                    |
| `support_user` | Read and write access for issues and escalations               |
| `admin`        | Full access, including creating and updating next actions       |

## Database (PostgreSQL)

Schema managed by Alembic. Tables:

| Table | Purpose |
|-------|---------|
| `users` | User accounts with role assignments |
| `customers` | Customer profiles (name, tier, industry, account manager) |
| `issues` | Open issues per customer (title, description, severity, status) |
| `issue_updates` | Append-only log of progress notes on issues |
| `next_actions` | Recommended next actions recorded by the agent (admin only) |
| `conversations` | One row per chat session |
| `conversation_turns` | Message history per conversation |
| `agent_actions` | Audit log of every tool call and its output |
| `agent_recommendations` | Outcome tracking for proposed next actions (accepted/edited/dismissed) |

Seeded with representative customers, issues, and update history via `api/db/seed.py`, run automatically on `docker compose up`.

## Memory (Redis)

Redis stores **conversation history only** — all message turns per `conv:{conversation_id}` key, with a 1-hour TTL. On each request the agent reads the full turn history from Redis to populate its LangGraph message state, then appends the new turns back.

**Redis vs PostgreSQL trade-off:** Conversation turns are also written to `conversation_turns` in Postgres for durability and audit. Redis is the fast read path — the agent always reads from Redis during an active session, never from Postgres. If Redis loses a key (TTL expiry or restart), the conversation context is lost for that session, but the durable record in Postgres remains. This is an intentional trade-off: Redis is optimised for the hot path; Postgres is the source of truth.

## Trade-offs

| Decision | Choice | Reason |
|----------|--------|--------|
| LLM model | `gpt-4o-mini` via LiteLLM proxy | Cost-efficient for a tool-calling agent; the proxy means switching models requires one config change |
| MCP transport | Streamable HTTP (not stdio) | stdio works for a single process; HTTP is required for Docker Compose where the agent and MCP server are separate containers |
| Customer name lookup | Exact match then prefix | Realistic user input rarely matches stored names exactly; prefix fallback handles "Globex" → "Globex Corp" without fuzzy matching complexity |
| RBAC enforcement | At the MCP tool boundary | Enforcing at the API gateway alone would not protect against a compromised or misbehaving agent; tool-level enforcement is the last line of defence |
| Duplicate write prevention | `parallel_tool_calls=False` + DB idempotency constraint | LLMs can emit duplicate tool calls in a single turn; disabling parallel calls prevents this at the LLM layer, and the DB constraint is the safety net |
| Conversation memory | Redis (active session) + Postgres (durable) | Redis gives sub-millisecond reads for the hot path; Postgres ensures history survives restarts and is available for audit |
| Redis memory cap | None set (dev only) | No memory limit or eviction policy — production would need both |
| Streaming | SSE-formatted over `POST` | The native browser `EventSource` API only supports `GET`, so the UI uses `fetch` + `ReadableStream` instead. This means no automatic reconnection if the stream drops |

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
