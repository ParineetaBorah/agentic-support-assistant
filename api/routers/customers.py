"""Customer endpoints."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from auth.keycloak import CurrentUser
from auth.rbac import require_sales_or_above
from db.customers import get_customer, list_customers
from db.issues import list_open_issues_for_customer
from db.pool import get_db
from models.customer import CustomerDetail, CustomerIssueSummary, CustomerOut

router = APIRouter()


@router.get("", response_model=list[CustomerOut])
async def get_customers(
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_sales_or_above),
) -> list[CustomerOut]:
    """List all customers."""
    rows = await list_customers(conn)
    return [
        CustomerOut(
            id=str(row["id"]),
            name=row["name"],
            tier=row["tier"],
            industry=row["industry"],
            account_manager=str(row["account_manager"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.get("/{customer_id}", response_model=CustomerDetail)
async def get_customer_detail(
    customer_id: str,
    conn: asyncpg.Connection = Depends(get_db),
    current_user: CurrentUser = Depends(require_sales_or_above),
) -> CustomerDetail:
    """Return a single customer plus their open issues."""
    customer_row = await get_customer(conn, customer_id)
    if customer_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    issue_rows = await list_open_issues_for_customer(conn, customer_id)
    return CustomerDetail(
        id=str(customer_row["id"]),
        name=customer_row["name"],
        tier=customer_row["tier"],
        industry=customer_row["industry"],
        account_manager=str(customer_row["account_manager"]),
        created_at=customer_row["created_at"],
        open_issues=[
            CustomerIssueSummary(
                id=str(row["id"]),
                title=row["title"],
                severity=row["severity"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in issue_rows
        ],
    )
