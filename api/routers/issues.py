"""Issue endpoints."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth.keycloak import CurrentUser
from auth.rbac import require_sales_or_above, require_support_or_above
from db.issues import (
    get_issue,
    insert_issue_update,
    list_issue_updates,
    list_issues,
)
from db.pool import get_db
from models.issue import IssueDetail, IssueOut, IssueUpdateCreate, IssueUpdateOut

router = APIRouter()


@router.get("", response_model=list[IssueOut])
async def get_issues(
    customer_id: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    severity: str | None = None,
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_sales_or_above),
) -> list[IssueOut]:
    """List issues, optionally filtered by customer_id, status, and/or severity."""
    rows = await list_issues(conn, customer_id=customer_id, status=status_, severity=severity)
    return [
        IssueOut(
            id=str(row["id"]),
            customer_id=str(row["customer_id"]),
            title=row["title"],
            description=row["description"],
            severity=row["severity"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


@router.get("/{issue_id}", response_model=IssueDetail)
async def get_issue_detail(
    issue_id: str,
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_sales_or_above),
) -> IssueDetail:
    """Return a single issue plus all of its updates, oldest first."""
    issue_row = await get_issue(conn, issue_id)
    if issue_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    update_rows = await list_issue_updates(conn, issue_id)
    return IssueDetail(
        id=str(issue_row["id"]),
        customer_id=str(issue_row["customer_id"]),
        title=issue_row["title"],
        description=issue_row["description"],
        severity=issue_row["severity"],
        status=issue_row["status"],
        created_at=issue_row["created_at"],
        updated_at=issue_row["updated_at"],
        updates=[
            IssueUpdateOut(
                id=str(row["id"]),
                update_text=row["update_text"],
                updated_by=str(row["updated_by"]),
                created_at=row["created_at"],
            )
            for row in update_rows
        ],
    )


@router.post("/{issue_id}/updates", response_model=IssueUpdateOut)
async def create_issue_update(
    issue_id: str,
    body: IssueUpdateCreate,
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_support_or_above),
) -> IssueUpdateOut:
    """Add an update to an issue."""
    issue_row = await get_issue(conn, issue_id)
    if issue_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    row = await insert_issue_update(conn, issue_id, body.update_text, current_user.user_id)
    return IssueUpdateOut(
        id=str(row["id"]),
        update_text=row["update_text"],
        updated_by=str(row["updated_by"]),
        created_at=row["created_at"],
    )
