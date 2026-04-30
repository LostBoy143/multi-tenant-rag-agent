"""
Lead extraction service.

Philosophy (per spec §2–3):
- ZERO extra LLM calls for v1.
- Email / phone come from regex over USER messages only (anti-hallucination §3.1).
- The model may emit a <lead>...</lead> JSON block; we accept structured
  name/company from it only when those values are plausible. We NEVER
  accept a model-fabricated email that doesn't appear in the user text.
- Score is heuristic: points for contact completeness + intent keyword hits.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead, LeadStatus

logger = logging.getLogger(__name__)

# ── Regex patterns ────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE
)

_PHONE_RE = re.compile(
    r"(?:\+?[\d][\d\s\-().]{7,}\d)",
    re.IGNORECASE,
)

# High-intent keywords (§3.2)
_HIGH_INTENT_KEYWORDS = {
    "pricing", "price", "cost", "costs", "demo", "trial", "enterprise",
    "quote", "buy", "plan", "plans", "integrate", "integration", "api",
    "contact", "book", "booking", "schedule", "purchase", "upgrade", "subscription",
    "paid", "payment", "onboard", "onboarding", "crm", "custom",
    "discount", "shipping", "delivery", "order", "return", "stock", "availability", "checkout"
}

# ── Lead XML block parser ─────────────────────────────────────────────────────

_LEAD_BLOCK_RE = re.compile(r"<lead>(.*?)</lead>", re.DOTALL | re.IGNORECASE)


def strip_lead_block(text: str) -> tuple[str, dict | None]:
    """
    Remove <lead>…</lead> from assistant text.
    Returns (clean_text, parsed_dict_or_None).
    """
    match = _LEAD_BLOCK_RE.search(text)
    if not match:
        return text, None

    raw_json = match.group(1).strip()
    clean_text = _LEAD_BLOCK_RE.sub("", text).strip()

    try:
        data = json.loads(raw_json)
        if not isinstance(data, dict):
            return clean_text, None
        return clean_text, data
    except (json.JSONDecodeError, ValueError):
        logger.debug("Lead block JSON parse failed: %s", raw_json[:200])
        return clean_text, None


# ── Field extractors ─────────────────────────────────────────────────────────

def _extract_email_from_text(text: str) -> str | None:
    matches = _EMAIL_RE.findall(text)
    return matches[-1].lower() if matches else None


def _extract_phone_from_text(text: str) -> str | None:
    matches = _PHONE_RE.findall(text)
    if not matches:
        return None
    # Use the most recent phone number provided in case of corrections
    raw = matches[-1].strip()
    # Must have at least 7 digits
    digits = re.sub(r"\D", "", raw)
    return raw if len(digits) >= 7 else None


def _compute_interest(user_messages: list[str]) -> str | None:
    """Return first matching high-intent category label, or None."""
    combined = " ".join(user_messages).lower()
    hits = [kw for kw in _HIGH_INTENT_KEYWORDS if kw in combined]
    if not hits:
        return None
    # Map keyword to human-readable label
    label_map = {
        "pricing": "Pricing", "price": "Pricing", "cost": "Pricing", "costs": "Pricing",
        "demo": "Demo", "trial": "Trial",
        "enterprise": "Enterprise", "quote": "Quote",
        "buy": "Purchase", "purchase": "Purchase",
        "plan": "Plans", "plans": "Plans",
        "integrate": "Integration", "integration": "Integration", "api": "API",
        "book": "Schedule", "booking": "Schedule", "schedule": "Schedule",
        "contact": "Contact", "onboard": "Onboarding", "onboarding": "Onboarding",
        "crm": "CRM Integration", "custom": "Custom",
        "discount": "Discounts", "shipping": "Shipping", "delivery": "Shipping",
        "order": "Orders", "return": "Returns", "checkout": "Checkout",
        "stock": "Availability", "availability": "Availability",
    }
    return label_map.get(hits[0], hits[0].title())


def _compute_score(
    email: str | None,
    phone: str | None,
    name: str | None,
    company: str | None,
    interest: str | None,
    user_message_count: int,
) -> int:
    """
    Heuristic 0-100 lead score (§3.2).
    Contact fields: email=30, phone=20, name=15, company=10.
    Intent + depth: interest=10, message count bonus up to 15.
    """
    score = 0
    if email:
        score += 30
    if phone:
        score += 20
    if name:
        score += 15
    if company:
        score += 10
    if interest:
        score += 10
    # Depth bonus: 1pt per message, max 15
    score += min(user_message_count, 15)
    return min(score, 100)


# ── Main upsert entry point ───────────────────────────────────────────────────

async def process_lead_from_message(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_text: str,           # the latest user message
    assistant_raw: str,       # raw assistant response (before stripping)
    all_user_texts: list[str],# all user messages in conversation so far
    source_url: str | None = None,
    visitor_id: str | None = None,
) -> None:
    """
    Extract a lead from the current exchange and upsert into the leads table.
    Called AFTER the assistant response is generated.
    No additional LLM calls are made.
    """
    try:
        # 1. Parse model <lead> block (if any)
        _, model_lead = strip_lead_block(assistant_raw)

        # 2. Extract email/phone from USER text only (anti-hallucination)
        combined_user = " ".join(all_user_texts)
        email = _extract_email_from_text(combined_user)
        phone = _extract_phone_from_text(combined_user)

        # 3. Accept name/company/interest from model block only when plausible (§3.1)
        name: str | None = None
        company: str | None = None
        model_interest: str | None = None
        if model_lead:
            raw_name = model_lead.get("name") or None
            raw_company = model_lead.get("company") or None
            raw_email = model_lead.get("email") or None
            raw_phone = model_lead.get("phone") or None
            raw_interest = model_lead.get("interest") or None

            # Interest: accept if non-empty string ≤ 30 chars
            if raw_interest and isinstance(raw_interest, str) and len(raw_interest) <= 30:
                clean_interest = raw_interest.strip().title()
                if clean_interest and clean_interest not in ["...", "Null", "None", "Unknown"]:
                    model_interest = clean_interest

            # Name: accept if non-empty string, ≤ 80 chars, no numbers
            if raw_name and isinstance(raw_name, str) and len(raw_name) <= 80 and not re.search(r"\d", raw_name):
                clean_name = raw_name.strip()
                if clean_name and clean_name not in ["...", "null", "None", "John Doe", "Jane Doe"]:
                    name = clean_name

            # Company: accept if non-empty string ≤ 100 chars
            if raw_company and isinstance(raw_company, str) and len(raw_company) <= 100:
                clean_company = raw_company.strip()
                if clean_company and clean_company not in ["...", "null", "None", "Acme Corp"]:
                    company = clean_company

            # Email from model: only if it actually appears in user text
            if raw_email and isinstance(raw_email, str):
                if raw_email.lower() in combined_user.lower():
                    email = email or raw_email.lower()

            # Phone from model: only if digits appear in user text
            if raw_phone and isinstance(raw_phone, str):
                digits = re.sub(r"\D", "", raw_phone)
                if digits and digits in re.sub(r"\D", "", combined_user):
                    phone = phone or raw_phone

        # 4. Compute interest label (LLM sentiment analysis first, fallback to regex keywords)
        interest = model_interest or _compute_interest(all_user_texts)

        # 5. Score
        score = _compute_score(
            email=email,
            phone=phone,
            name=name,
            company=company,
            interest=interest,
            user_message_count=len(all_user_texts),
        )

        # 6. Gate: only upsert if we have email OR phone OR (score >= 40 with name)
        if not email and not phone and not (score >= 40 and name):
            return

        # 7. Upsert lead row (one per conversation, enrich on subsequent messages)
        existing_result = await db.execute(
            select(Lead).where(Lead.conversation_id == conversation_id)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # Enrich: update with fresh data when provided (allows user corrections).
            # We overwrite existing values if the user supplies a new one in this exchange,
            # but never replace a known value with None/empty.
            if email:
                existing.email = email
            if phone:
                existing.phone = phone
            if name:
                existing.name = name
            if company:
                existing.company = company
            if interest:
                existing.interest = interest
            if source_url and not existing.source_url:
                existing.source_url = source_url
            # Always update score (may improve as more info revealed)
            existing.lead_score = _compute_score(
                email=existing.email,
                phone=existing.phone,
                name=existing.name,
                company=existing.company,
                interest=existing.interest,
                user_message_count=len(all_user_texts),
            )
            existing.updated_at = datetime.now(timezone.utc)
        else:
            lead = Lead(
                organization_id=organization_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                email=email,
                phone=phone,
                name=name,
                company=company,
                interest=interest,
                lead_score=score,
                source_url=source_url,
                visitor_id=visitor_id,
                status=LeadStatus.NEW,
                captured_at=datetime.now(timezone.utc),
            )
            db.add(lead)

        await db.commit()
        logger.info(
            "Lead upserted.",
            extra={
                "organization_id": str(organization_id),
                "conversation_id": str(conversation_id),
                "score": score,
                "has_email": bool(email),
                "has_phone": bool(phone),
            },
        )
    except Exception:
        logger.exception(
            "Lead extraction failed silently.",
            extra={"conversation_id": str(conversation_id)},
        )
        # Never crash the chat response due to lead capture failure
