"""Pydantic models for MCP tool inputs and outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RiskLevel = Literal["low", "medium", "high", "critical"]
RecommendationOutcome = Literal["accepted", "edited", "dismissed"]


class GetCustomerProfileInput(BaseModel):
    """Input for get_customer_profile."""

    customer_name: str
    user_role: str


class CustomerProfile(BaseModel):
    """A customer's profile."""

    id: str
    name: str
    tier: str
    industry: str
    account_manager: str


class GetOpenIssuesInput(BaseModel):
    """Input for get_open_issues."""

    customer_id: str
    user_role: str


class OpenIssue(BaseModel):
    """Summary of an open issue."""

    id: str
    title: str
    severity: str
    status: str
    created_at: datetime


class OpenIssuesResult(BaseModel):
    """A customer's open issues, most severe first."""

    issues: list[OpenIssue]


class GetIssueDetailInput(BaseModel):
    """Input for get_issue_detail."""

    issue_id: str
    user_role: str


class IssueUpdate(BaseModel):
    """A single update on an issue."""

    id: str
    update_text: str
    updated_by: str
    created_at: datetime


class IssueDetail(BaseModel):
    """Full issue detail including its update history, oldest first."""

    id: str
    customer_id: str
    title: str
    description: str
    severity: str
    status: str
    created_at: datetime
    updated_at: datetime
    updates: list[IssueUpdate]


class CreateNextActionInput(BaseModel):
    """Input for create_next_action."""

    issue_id: str
    recommendation_text: str
    risk_level: RiskLevel
    user_id: str
    user_role: str
    conversation_id: str


class NextActionCreated(BaseModel):
    """Result of creating a next action."""

    id: str
    created_at: datetime


class AddIssueUpdateInput(BaseModel):
    """Input for add_issue_update."""

    issue_id: str
    update_text: str
    user_id: str
    user_role: str
    conversation_id: str


class IssueUpdateCreated(BaseModel):
    """Result of adding an issue update."""

    id: str
    created_at: datetime


class RecordRecommendationInput(BaseModel):
    """Input for record_recommendation."""

    issue_id: str
    recommended_text: str
    risk_level: RiskLevel
    outcome: RecommendationOutcome
    user_role: str
    conversation_id: str


class RecommendationRecorded(BaseModel):
    """Result of recording a recommendation outcome."""

    id: str
    outcome: str
    created_at: datetime


class CreateEscalationSummaryInput(BaseModel):
    """Input for create_escalation_summary."""

    customer_id: str
    user_role: str


class EscalationSummary(BaseModel):
    """Structured, LLM-generated escalation summary for a customer's open issues."""

    risk_level: RiskLevel
    summary: str
    recommendation: str
    missing_info: str


class ToolErrorPayload(BaseModel):
    """Structured error encoded as JSON in a tool's error text when isError=True."""

    error_type: Literal["permission_denied", "not_found", "validation_error", "internal_error"]
    detail: str
