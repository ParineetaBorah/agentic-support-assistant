"""Pydantic models for next-action endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class NextActionOut(BaseModel):
    """A recommended next action on an issue."""

    id: str
    issue_id: str
    recommendation_text: str
    risk_level: str
    created_by: str
    status: str
    created_at: datetime


class NextActionStatusUpdate(BaseModel):
    """Request body for updating a next action's status."""

    status: Literal["completed"]
