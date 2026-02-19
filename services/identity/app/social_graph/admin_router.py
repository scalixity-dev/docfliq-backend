"""
Social graph domain — admin-facing routes.

Routes:
  GET   /api/v1/admin/social/reports                   List all reports (filterable by status)
  PATCH /api/v1/admin/social/reports/{report_id}/review  Handle a report (reviewed/actioned/dismissed)

Requires: ADMIN or SUPER_ADMIN role.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.database import get_db
from app.social_graph import controller as ctrl
from app.social_graph.constants import ReportStatus
from app.social_graph.schemas import (
    AdminReportItem,
    AdminReportListResponse,
    AdminReportReviewRequest,
)
from shared.models.user import CurrentUser

router = APIRouter(prefix="/admin/social", tags=["admin-social-graph"])


@router.get(
    "/reports",
    response_model=AdminReportListResponse,
    summary="[Admin] List user/content reports",
    description="Optionally filter by status. Results are ordered oldest-first (FIFO review queue).",
)
async def list_reports(
    status: ReportStatus | None = Query(None, description="Filter by report status"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminReportListResponse:
    return await ctrl.admin_list_reports(session, status_filter=status, page=page, size=size)


@router.patch(
    "/reports/{report_id}/review",
    response_model=AdminReportItem,
    summary="[Admin] Review a report",
    description=(
        "Set the report status to 'reviewed', 'actioned', or 'dismissed'. "
        "Optionally record the action taken."
    ),
)
async def review_report(
    report_id: uuid.UUID,
    body: AdminReportReviewRequest,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminReportItem:
    return await ctrl.admin_review_report(session, report_id, admin.id, body)
