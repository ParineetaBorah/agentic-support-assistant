"""Insert fixed seed data for local development.

Run from the api/ directory:
    python db/seed.py

Every insert uses ON CONFLICT DO NOTHING, so this script is safe to run
multiple times against the same database.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from psycopg2.extensions import connection as PGConnection

from core.config import settings

USERS = [
    ("b1000000-0000-0000-0000-000000000001", "alice", "alice@acme.com", "sales_user"),
    ("b1000000-0000-0000-0000-000000000002", "bob", "bob@acme.com", "support_user"),
    ("b1000000-0000-0000-0000-000000000003", "carol", "carol@acme.com", "admin"),
]

CUSTOMERS = [
    ("a1000000-0000-0000-0000-000000000001", "Globex Corp", "enterprise", "Manufacturing", "b1000000-0000-0000-0000-000000000003"),
    ("a1000000-0000-0000-0000-000000000002", "Initech", "smb", "Technology", "b1000000-0000-0000-0000-000000000002"),
    ("a1000000-0000-0000-0000-000000000003", "Umbrella Ltd", "startup", "Biotech", "b1000000-0000-0000-0000-000000000001"),
]

ISSUES = [
    (
        "c1000000-0000-0000-0000-000000000001",
        "a1000000-0000-0000-0000-000000000001",
        "Production database unresponsive",
        "The production PostgreSQL instance is not responding to client connections.",
        "critical",
        "open",
    ),
    (
        "c1000000-0000-0000-0000-000000000002",
        "a1000000-0000-0000-0000-000000000001",
        "API gateway timeouts on checkout",
        "Checkout requests routed through the API gateway are timing out under load.",
        "high",
        "open",
    ),
    (
        "c1000000-0000-0000-0000-000000000003",
        "a1000000-0000-0000-0000-000000000001",
        "ETL pipeline failure",
        "The nightly ETL pipeline is failing during the transform step.",
        "high",
        "in_progress",
    ),
    (
        "c1000000-0000-0000-0000-000000000004",
        "a1000000-0000-0000-0000-000000000002",
        "SSO login intermittent failures",
        "Some users are redirected back to the login page after completing SSO authentication.",
        "medium",
        "open",
    ),
]

ISSUE_UPDATES = [
    (
        "d1000000-0000-0000-0000-000000000001",
        "c1000000-0000-0000-0000-000000000001",
        "Confirmed the primary Postgres instance is rejecting new connections; the connection pool appears exhausted.",
        "b1000000-0000-0000-0000-000000000002",
        "2026-06-12 09:15:00+00",
    ),
    (
        "d1000000-0000-0000-0000-000000000002",
        "c1000000-0000-0000-0000-000000000001",
        "Failover to the standby did not restore service; investigating disk I/O saturation on the primary.",
        "b1000000-0000-0000-0000-000000000002",
        "2026-06-12 11:40:00+00",
    ),
    (
        "d1000000-0000-0000-0000-000000000003",
        "c1000000-0000-0000-0000-000000000002",
        "Reproduced the timeouts under load at roughly 200 concurrent checkout requests.",
        "b1000000-0000-0000-0000-000000000002",
        "2026-06-11 14:05:00+00",
    ),
    (
        "d1000000-0000-0000-0000-000000000004",
        "c1000000-0000-0000-0000-000000000002",
        "Escalated to the platform team; awaiting a capacity increase on the gateway tier.",
        "b1000000-0000-0000-0000-000000000003",
        "2026-06-13 16:20:00+00",
    ),
    (
        "d1000000-0000-0000-0000-000000000005",
        "c1000000-0000-0000-0000-000000000003",
        "Nightly ETL fails at the transform step with a schema mismatch on the orders table.",
        "b1000000-0000-0000-0000-000000000002",
        "2026-06-10 08:00:00+00",
    ),
    (
        "d1000000-0000-0000-0000-000000000006",
        "c1000000-0000-0000-0000-000000000003",
        "Applied a temporary column mapping; monitoring tonight's pipeline run.",
        "b1000000-0000-0000-0000-000000000002",
        "2026-06-13 18:30:00+00",
    ),
    (
        "d1000000-0000-0000-0000-000000000007",
        "c1000000-0000-0000-0000-000000000004",
        "About 1 in 10 SSO logins loop back to the login page; suspect clock skew on the identity provider.",
        "b1000000-0000-0000-0000-000000000002",
        "2026-06-13 10:10:00+00",
    ),
]


def seed(conn: PGConnection) -> None:
    """Insert all seed rows into conn, skipping any that already exist."""
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO users (id, username, email, role)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            USERS,
        )
        cur.executemany(
            """
            INSERT INTO customers (id, name, tier, industry, account_manager)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            CUSTOMERS,
        )
        cur.executemany(
            """
            INSERT INTO issues (id, customer_id, title, description, severity, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            ISSUES,
        )
        cur.executemany(
            """
            INSERT INTO issue_updates (id, issue_id, update_text, updated_by, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            ISSUE_UPDATES,
        )
    conn.commit()


def main() -> None:
    """Connect to the configured database and insert seed data."""
    conn = psycopg2.connect(settings.postgres_url)
    try:
        seed(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
