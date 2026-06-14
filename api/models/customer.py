"""Pydantic models for customer endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CustomerOut(BaseModel):
    """A customer record."""

    id: str
    name: str
    tier: str
    industry: str
    account_manager: str
    created_at: datetime


class CustomerIssueSummary(BaseModel):
    """Summary of one of a customer's open issues."""

    id: str
    title: str
    severity: str
    status: str
    created_at: datetime


class CustomerDetail(CustomerOut):
    """A customer record plus their open (non-closed) issues."""

    open_issues: list[CustomerIssueSummary]
