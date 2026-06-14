"""Pydantic models for issue endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IssueOut(BaseModel):
    """An issue record."""

    id: str
    customer_id: str
    title: str
    description: str
    severity: str
    status: str
    created_at: datetime
    updated_at: datetime


class IssueUpdateOut(BaseModel):
    """A single update on an issue."""

    id: str
    update_text: str
    updated_by: str
    created_at: datetime


class IssueDetail(IssueOut):
    """An issue record plus its update history, oldest first."""

    updates: list[IssueUpdateOut]


class IssueUpdateCreate(BaseModel):
    """Request body for adding an update to an issue."""

    update_text: str
