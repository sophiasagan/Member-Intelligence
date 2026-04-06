from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class MemberBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_number: str
    first_name: str
    last_name: str
    email: str
    date_of_birth: date
    member_since: date
    segment: str | None
    zip_code: str | None
    created_at: datetime


class MemberListItem(MemberBase):
    """Single entry in the paginated list response."""
    pass


class PaginatedMembers(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    results: list[MemberListItem]


class MemberSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_deposits: Decimal
    total_loan_balance: Decimal
    account_count: int
    loan_count: int
    tenure_years: float


class MemberDetail(MemberBase):
    """Member record with computed financial summary."""
    summary: MemberSummary


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------
class AccountItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_type: str
    balance: Decimal
    opened_date: date
    status: str


class LoanItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    loan_type: str
    current_balance: Decimal
    interest_rate: Decimal
    origination_date: date
    maturity_date: date
    status: str


class MemberPortfolio(BaseModel):
    member_id: int
    accounts: list[AccountItem]
    loans: list[LoanItem]
    total_deposits: Decimal
    total_loan_balance: Decimal
    loan_to_deposit_ratio: Decimal | None  # None when deposits == 0
    net_worth: Decimal


# ---------------------------------------------------------------------------
# Segment summary
# ---------------------------------------------------------------------------
class SegmentStats(BaseModel):
    segment: str
    member_count: int
    avg_deposits: Decimal
    avg_loan_balance: Decimal
    avg_loan_to_deposit_ratio: Decimal | None  # None when avg_deposits == 0
    top_loan_type: str | None  # None when segment has no loans


class SegmentSummaryResponse(BaseModel):
    segments: list[SegmentStats]
