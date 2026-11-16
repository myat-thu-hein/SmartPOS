"""AI assistant schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.analytics import Insight
from app.schemas.common import RequestModel


class ChatMessage(RequestModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(RequestModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


class ToolCallInfo(BaseModel):
    name: str
    arguments: dict[str, Any]


class AssistantReply(BaseModel):
    answer: str
    mode: Literal["llm", "offline"]
    model: str | None
    tools_used: list[ToolCallInfo]
    notice: str | None = None


class AIStatus(BaseModel):
    llm_configured: bool
    model: str | None
    available_tools: list[str]
    message: str


class Insights(BaseModel):
    insights: list[Insight]
    source: Literal["rules"] = "rules"
