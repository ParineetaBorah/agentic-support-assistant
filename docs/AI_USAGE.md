# AI Tool Usage Notes

A brief account of how AI tools were used during the development of this project.

## Tools used

- **Claude Code (CLI)** — primary implementation tool. Used to scaffold the project, write application code, generate migrations, and wire components together.
- **Claude (chat)** — architectural advisor. Used to reason through design decisions, evaluate trade-offs, and review Claude Code's output before accepting it.

## How the work was divided

### Delegated to AI (with review)
- Boilerplate and scaffolding: project structure, Dockerfiles, docker-compose.yml, requirements files.
- Database layer: Alembic migration files and the seed script, generated from a schema I specified.
- Repetitive, well-defined code: Pydantic models, FastAPI routers following an established pattern, the React UI components.
- Test scripts: standalone test harnesses for auth, MCP tools, and the agent.

### Decided by me, implemented with AI assistance
- **Architecture**: the four-layer separation, the choice to put RBAC enforcement at the tool level (not just the API gateway), and the decision to keep the MCP server as a separate HTTP service rather than bundling it.
- **Key design trade-offs**: Docker Postgres over Supabase, pip over Poetry, what to keep in redis memory layer over PostGres, using LiteLLM.
- **The system prompt**: I wrote the tool catalogue, workflow chain, intent detection, and propose-then-confirm rules myself, then used AI feedback to tighten them.
- **Resilience and observability strategy**: which patterns to apply (idempotent writes, timeouts, retries) and which to defer (circuit breakers, fallback strategy) and why.

### Reviewed line-by-line, never blindly accepted
- All authentication and authorization code: JWT validation, RBAC role checks. Security-critical, so I read and understood every line.
- The duplicate-write fix: I reviewed why `parallel_tool_calls=False` and the database idempotency constraint were both needed, and how they interact.
- Any code touching the database write path.

## Notable AI-caught issues

Several real bugs were surfaced during AI-assisted development that I then reviewed and fixed:

- The MCP stdio-vs-HTTP transport mismatch that broke tool calling across Docker containers.
- The duplicate-write bug, caught by the eval harness, which led to the `parallel_tool_calls` and idempotency fixes.
- The fuzzy customer-name matching gap on realistic phrasing like "Globex" instead of "Globex Corp".
- The known identifier reuse gap. The agent kept re-fetching the same customer and issue IDs it had already looked up, or guessing them. I fixed it by pulling the resolved UUIDs from the `agent_actions` log into a KNOWN IDENTIFIERS prompt block, scoped to the most recent customer, so it can act directly instead of resolving everything again.

## What I would not delegate to AI on a real engagement

- Final review of security-critical code (auth, RBAC, secrets handling).
- Architectural decisions and trade-offs.
- Anything that writes data or has side effects, without understanding exactly what it does.
- Validating that eval results actually reflect agent quality, rather than trusting a green test run.

## Reflection

AI tools took a lot of the mechanical work off my plate, things like scaffolding, migrations, and boilerplate routers. That freed up time for the parts that actually needed judgment: the architecture, the system prompt, eval design, and security review.
