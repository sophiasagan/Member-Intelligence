from datetime import date, datetime, timezone
from decimal import Decimal

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.models.loan import Loan
from app.models.member import Member
from app.schemas.insights import MemberInsightResponse
from app.services.ai_service import generate_member_insight

router = APIRouter(prefix="/members", tags=["insights"])


@router.post("/{member_id}/analyze", response_model=MemberInsightResponse)
def analyze_member(member_id: int, db: Session = Depends(get_db)) -> MemberInsightResponse:
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    accounts = db.execute(
        select(Account).where(Account.member_id == member_id)
    ).scalars().all()

    loans = db.execute(
        select(Loan).where(Loan.member_id == member_id)
    ).scalars().all()

    total_deposits = sum((a.balance for a in accounts), Decimal("0"))
    total_loan_balance = sum((lo.current_balance for lo in loans), Decimal("0"))
    loan_to_deposit_ratio = (
        (total_loan_balance / total_deposits).quantize(Decimal("0.0001"))
        if total_deposits > 0
        else None
    )

    tenure_years = round((date.today() - member.member_since).days / 365.25, 2)

    member_data = {
        # identity
        "member_id": member.id,
        "member_number": member.member_number,
        "first_name": member.first_name,
        "last_name": member.last_name,
        "member_since": member.member_since.isoformat(),
        "tenure_years": tenure_years,
        "segment": member.segment,
        "zip_code": member.zip_code,
        # portfolio totals
        "total_deposits": str(total_deposits),
        "total_loan_balance": str(total_loan_balance),
        "net_worth": str(total_deposits - total_loan_balance),
        "loan_to_deposit_ratio": str(loan_to_deposit_ratio) if loan_to_deposit_ratio is not None else None,
        # line items
        "accounts": [
            {
                "account_type": a.account_type,
                "balance": str(a.balance),
                "status": a.status,
                "opened_date": a.opened_date.isoformat(),
            }
            for a in accounts
        ],
        "loans": [
            {
                "loan_type": lo.loan_type,
                "current_balance": str(lo.current_balance),
                "interest_rate": str(lo.interest_rate),
                "status": lo.status,
                "origination_date": lo.origination_date.isoformat(),
                "maturity_date": lo.maturity_date.isoformat(),
            }
            for lo in loans
        ],
    }

    try:
        insight = generate_member_insight(member_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI service returned an unparseable response: {exc}",
        ) from exc
    except anthropic.APIStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Anthropic API error {exc.status_code}: {exc.message}",
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not reach Anthropic API: {exc}",
        ) from exc

    return MemberInsightResponse(
        member_id=member.id,
        member_name=f"{member.first_name} {member.last_name}",
        generated_at=datetime.now(timezone.utc),
        narrative=insight.narrative,
        risk_flags=insight.risk_flags,
        cross_sell_opportunities=insight.cross_sell_opportunities,
    )
