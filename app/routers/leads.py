"""
Authenticated dashboard API for lead management.
All endpoints are scoped to the current user's organization.
"""
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, select

from app.dependencies import CurrentUserDep, DatabaseDep
from app.models.lead import Lead, LeadStatus
from app.schemas.lead import LeadUpdate

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])

_VALID_STATUSES = {s.value for s in LeadStatus}


def _serialize_lead(lead: Lead) -> dict:
    return {
        "id": str(lead.id),
        "organization_id": str(lead.organization_id),
        "agent_id": str(lead.agent_id) if lead.agent_id else None,
        "conversation_id": str(lead.conversation_id) if lead.conversation_id else None,
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "company": lead.company,
        "location": lead.location,
        "interest": lead.interest,
        "intent_summary": lead.intent_summary,
        "lead_score": lead.lead_score,
        "status": lead.status,
        "source_url": lead.source_url,
        "metadata_json": lead.metadata_json,
        "captured_at": lead.captured_at.isoformat() if lead.captured_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
    }


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_lead_stats(user: CurrentUserDep, db: DatabaseDep):
    """Dashboard summary cards: counts by status + avg score + this-week count."""
    org_id = user.organization_id
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    base = select(Lead).where(Lead.organization_id == org_id)

    total_q = select(func.count(Lead.id)).where(Lead.organization_id == org_id)

    def _count_status(status: str):
        return select(func.count(Lead.id)).where(
            and_(Lead.organization_id == org_id, Lead.status == status)
        )

    avg_score_q = select(func.avg(Lead.lead_score)).where(
        Lead.organization_id == org_id
    )
    this_week_q = select(func.count(Lead.id)).where(
        and_(Lead.organization_id == org_id, Lead.captured_at >= week_ago)
    )

    total = (await db.execute(total_q)).scalar() or 0
    new = (await db.execute(_count_status("new"))).scalar() or 0
    contacted = (await db.execute(_count_status("contacted"))).scalar() or 0
    qualified = (await db.execute(_count_status("qualified"))).scalar() or 0
    converted = (await db.execute(_count_status("converted"))).scalar() or 0
    avg_score_raw = (await db.execute(avg_score_q)).scalar()
    avg_score = round(float(avg_score_raw), 1) if avg_score_raw is not None else None
    leads_this_week = (await db.execute(this_week_q)).scalar() or 0

    return {
        "success": True,
        "data": {
            "total": total,
            "new": new,
            "contacted": contacted,
            "qualified": qualified,
            "converted": converted,
            "avg_score": avg_score,
            "leads_this_week": leads_this_week,
        },
    }


# ── Export CSV (before detail so /export isn't caught as /{id}) ───────────────

@router.get("/export")
async def export_leads_csv(
    user: CurrentUserDep,
    db: DatabaseDep,
    status: str | None = Query(default=None),
    min_score: int | None = Query(default=None, ge=0, le=100),
    interest: str | None = Query(default=None),
):
    """Download all filtered leads as a UTF-8 CSV file."""
    org_id = user.organization_id
    q = select(Lead).where(Lead.organization_id == org_id)

    if status and status in _VALID_STATUSES:
        q = q.where(Lead.status == status)
    if min_score is not None:
        q = q.where(Lead.lead_score >= min_score)
    if interest:
        q = q.where(Lead.interest == interest)

    q = q.order_by(Lead.captured_at.desc())
    result = await db.execute(q)
    leads = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "name", "email", "phone", "interest",
        "lead_score", "status", "source_url", "captured_at",
    ])
    for lead in leads:
        writer.writerow([
            str(lead.id),
            lead.name or "",
            lead.email or "",
            lead.phone or "",
            lead.interest or "",
            lead.lead_score,
            lead.status,
            lead.source_url or "",
            lead.captured_at.isoformat() if lead.captured_at else "",
        ])

    output.seek(0)
    filename = f"leads_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("")
async def list_leads(
    user: CurrentUserDep,
    db: DatabaseDep,
    status: str | None = Query(default=None),
    min_score: int | None = Query(default=None, ge=0, le=100),
    interest: str | None = Query(default=None),
    date_from: str | None = Query(default=None),   # ISO date string
    date_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    """List leads with filters and pagination."""
    org_id = user.organization_id
    q = select(Lead).where(Lead.organization_id == org_id)

    if status and status in _VALID_STATUSES:
        q = q.where(Lead.status == status)
    if min_score is not None:
        q = q.where(Lead.lead_score >= min_score)
    if interest:
        q = q.where(Lead.interest == interest)
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
            q = q.where(Lead.captured_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
            q = q.where(Lead.captured_at <= dt_to)
        except ValueError:
            pass

    # Total count for pagination
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(Lead.captured_at.desc())
    q = q.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(q)
    leads = result.scalars().all()

    return {
        "success": True,
        "data": {
            "leads": [_serialize_lead(l) for l in leads],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        },
    }


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{lead_id}")
async def get_lead(lead_id: uuid.UUID, user: CurrentUserDep, db: DatabaseDep):
    """Get a single lead by ID."""
    result = await db.execute(
        select(Lead).where(
            Lead.id == lead_id, Lead.organization_id == user.organization_id
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"success": True, "data": _serialize_lead(lead)}


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{lead_id}")
async def update_lead(
    lead_id: uuid.UUID,
    body: LeadUpdate,
    user: CurrentUserDep,
    db: DatabaseDep,
):
    """Update lead status or add notes."""
    result = await db.execute(
        select(Lead).where(
            Lead.id == lead_id, Lead.organization_id == user.organization_id
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if body.status is not None:
        if body.status not in _VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status '{body.status}'")
        lead.status = body.status
    if body.name is not None:
        lead.name = body.name
    if body.email is not None:
        lead.email = body.email.lower()
    if body.phone is not None:
        lead.phone = body.phone
    if body.company is not None:
        lead.company = body.company
    if body.interest is not None:
        lead.interest = body.interest
    if body.notes is not None:
        meta = lead.metadata_json or {}
        meta["notes"] = body.notes
        lead.metadata_json = meta

    lead.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(lead)
    return {"success": True, "data": _serialize_lead(lead)}


# ── Delete / Archive ──────────────────────────────────────────────────────────

@router.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: uuid.UUID, user: CurrentUserDep, db: DatabaseDep):
    """Hard-delete lead."""
    result = await db.execute(
        select(Lead).where(
            Lead.id == lead_id, Lead.organization_id == user.organization_id
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    await db.delete(lead)
    await db.commit()
    return None
