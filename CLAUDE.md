# Development conventions for acme-agent

## Architecture
- Run the API from the `api/` directory: `uvicorn main:app --reload`
- Import paths are relative to `api/` (e.g. `from auth.keycloak import ...`)
- All new routers go in `api/routers/`, included in `main.py` with a prefix

## Pydantic & settings
- All env vars go through an `api/core/config.py` `Settings` singleton — never call `os.environ.get()` directly
- All Pydantic models (request/response schemas, JWT claims, internal data structures) live in `api/models/`, organized by domain (e.g. `api/models/auth.py`)
- All API request bodies must have a Pydantic input model
- All API responses must have a Pydantic response model (set via `response_model=`)
- All internal data structures (JWT claims, tool inputs/outputs) use Pydantic models

## Database
- PostgreSQL via `asyncpg`, with the connection pool initialised in `main.py`'s lifespan
- All queries live in `api/db/` — never inline SQL in routers or agent code
- UUID primary keys everywhere

## Database migrations
- Alembic owns the schema — never `ALTER` tables manually
- New tables/columns = new migration file in `api/alembic/versions/`
- Run migrations: `cd api && alembic upgrade head`
- Seed dev data: `cd api && python db/seed.py`
- `psycopg2-binary` for dev/Docker; swap to `psycopg2` (+ `libpq-dev`) in prod
- Docker build gotcha: `api`, `mcp_server`, and `migrate` each build their own
  image from their build context. After a code or migration change, rebuilding
  only `api`/`mcp_server` leaves `migrate`'s image stale, so `docker compose run
  migrate` silently no-ops against old code. Always run `docker compose run
  --build --rm migrate` (the `--build` forces migrate's image to rebuild) before
  recreating the app containers with `docker compose up -d --no-deps
  --force-recreate api mcp_server`.

## Redis
- All Redis access goes through a helper in `api/core/redis.py`
- Keys follow the pattern `conv:{conversation_id}` with a 1 hour TTL

## Error handling
- HTTP 401 for missing/invalid auth, 403 for insufficient role, 404 for not found
- Never let `KeyError` or `AttributeError` bubble up — catch at parse time via Pydantic

## Security
- Browser code never talks to Keycloak directly — all auth flows route through FastAPI (`POST /auth/login`)
- The Keycloak client secret only ever exists in `api/` environment variables and config files (`api/core/config.py`), never in UI code

## Dependencies
- pip + `requirements.txt` — no Poetry
- New packages are added to `api/requirements.txt` immediately

## Testing
- Test scripts go in `tests/`
- Each component gets a standalone test script runnable without the full stack
