"""AI business assistant."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai import orchestrator, tools
from app.api.deps import RestaurantContext, require
from app.core.config import get_settings
from app.core.errors import RateLimited
from app.core.permissions import Permission
from app.core.rate_limit import ai_limiter
from app.db.session import get_db
from app.schemas.ai import AIStatus, AssistantReply, ChatRequest, Insights
from app.services.audit import record_audit
from app.services.dashboard import build_dashboard

router = APIRouter(prefix="/ai", tags=["ai"])
AI_REQUESTS_PER_WINDOW = 30
AI_WINDOW_SECONDS = 600


@router.get("/status", response_model=AIStatus)
def status(ctx: RestaurantContext = Depends(require(Permission.AI_USE))) -> AIStatus:
    settings = get_settings()
    configured = settings.llm_configured
    return AIStatus(
        llm_configured=configured,
        model=settings.openai_model if configured else None,
        available_tools=[t.name for t in tools.tools_for(ctx)],
        message=(
            "Connected to the configured OpenAI model."
            if configured
            else "No OPENAI_API_KEY is configured. The assistant answers common questions with SmartPOS's "
            "rule-based engine. Add OPENAI_API_KEY to the backend environment to enable natural-language "
            "answers."
        ),
    )


@router.post("/chat", response_model=AssistantReply)
def chat(
    data: ChatRequest, ctx: RestaurantContext = Depends(require(Permission.AI_USE)), db: Session = Depends(get_db)
) -> AssistantReply:
    allowed, retry_after = ai_limiter.hit(f"ai:{ctx.user_id}", AI_REQUESTS_PER_WINDOW, AI_WINDOW_SECONDS)
    if not allowed:
        raise RateLimited("Too many assistant requests. Please wait a moment.", details={"retry_after": retry_after})
    reply = orchestrator.answer(db, ctx, data.message, data.history)
    # The question text is not stored; only which tools were used.
    record_audit(
        db,
        action="ai.query",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        details={"mode": reply.mode, "tools": [t.name for t in reply.tools_used], "question_length": len(data.message)},
        ip_address=ctx.ip,
    )
    db.commit()
    return reply


@router.get("/insights", response_model=Insights, summary="Deterministic insights (no LLM required)")
def insights(
    ctx: RestaurantContext = Depends(require(Permission.ANALYTICS_READ)), db: Session = Depends(get_db)
) -> Insights:
    return Insights(insights=build_dashboard(db, ctx).insights)
