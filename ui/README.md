# Acme Agent UI

Minimal React + TypeScript + Vite frontend for the Acme Agent demo: a login
page and a chat interface for talking to the support agent.

## Setup

```bash
npm install
npm run dev
```

The dev server runs on http://localhost:5173 and proxies `/api/*` requests
to the backend at `http://localhost:8000` (see `vite.config.ts`).

## Requirements

- Backend API running on port 8000: `cd ../api && uvicorn main:app --reload`
- Keycloak running on port 8080 with the `acme` realm imported
- Postgres, Redis, and LiteLLM running (see the root `docker-compose.yml`)

## Login

Sign in with one of the seeded Keycloak users (password `password123`):

| Username | Role          |
| -------- | ------------- |
| alice    | sales_user    |
| bob      | support_user  |
| carol    | admin         |

## Configuration

The UI never talks to Keycloak directly — `POST /api/auth/login` on the
backend handles the Keycloak token exchange. To point at a different
Keycloak instance, realm, or client, configure the backend's `Settings`
(see `api/core/config.py`), not this app.

## Scope

This is a minimal demo build: only login and chat are implemented. The
dashboard, customers list, and issue detail pages are not yet built.
