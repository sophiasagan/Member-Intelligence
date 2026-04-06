from datetime import datetime

from pydantic import BaseModel


class MemberInsight(BaseModel):
    """Internal type returned by ai_service — the raw Claude output."""
    narrative: str
    risk_flags: list[str]
    cross_sell_opportunities: list[str]


class MemberInsightResponse(BaseModel):
    """API response for POST /members/{id}/analyze."""
    member_id: int
    member_name: str
    generated_at: datetime
    narrative: str
    risk_flags: list[str]
    cross_sell_opportunities: list[str]
