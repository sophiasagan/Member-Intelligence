from datetime import date
from decimal import Decimal
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, over, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.models.loan import Loan
from app.models.member import Member
from app.schemas.member import (
    AccountItem,
    LoanItem,
    MemberDetail,
    MemberListItem,
    MemberPortfolio,
    MemberSummary,
    PaginatedMembers,
    SegmentStats,
    SegmentSummaryResponse,
)

router = APIRouter(prefix="/members", tags=["members"])
segments_router = APIRouter(prefix="/segments", tags=["segments"])


@router.get("", response_model=PaginatedMembers)
def list_members(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    segment: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PaginatedMembers:
    stmt = select(Member)

    if segment is not None:
        stmt = stmt.where(Member.segment == segment.lower())

    total: int = db.scalar(select(func.count()).select_from(stmt.subquery()))

    rows = (
        db.execute(
            stmt.order_by(Member.member_since.desc(), Member.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    return PaginatedMembers(
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
        results=[MemberListItem.model_validate(m) for m in rows],
    )


@router.get("/{member_id}", response_model=MemberDetail)
def get_member(member_id: int, db: Session = Depends(get_db)) -> MemberDetail:
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    # Aggregate deposits (all accounts) in one query
    deposit_row = db.execute(
        select(
            func.coalesce(func.sum(Account.balance), 0).label("total_deposits"),
            func.count(Account.id).label("account_count"),
        ).where(Account.member_id == member_id)
    ).one()

    # Aggregate active loan balances in one query
    loan_row = db.execute(
        select(
            func.coalesce(func.sum(Loan.current_balance), 0).label("total_loan_balance"),
            func.count(Loan.id).label("loan_count"),
        ).where(Loan.member_id == member_id)
    ).one()

    today = date.today()
    tenure_years = round(
        (today - member.member_since).days / 365.25, 2
    )

    summary = MemberSummary(
        total_deposits=Decimal(str(deposit_row.total_deposits)),
        total_loan_balance=Decimal(str(loan_row.total_loan_balance)),
        account_count=deposit_row.account_count,
        loan_count=loan_row.loan_count,
        tenure_years=tenure_years,
    )

    return MemberDetail(
        **MemberListItem.model_validate(member).model_dump(),
        summary=summary,
    )


@router.get("/{member_id}/portfolio", response_model=MemberPortfolio)
def get_member_portfolio(member_id: int, db: Session = Depends(get_db)) -> MemberPortfolio:
    if db.get(Member, member_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    accounts = (
        db.execute(select(Account).where(Account.member_id == member_id))
        .scalars()
        .all()
    )
    loans = (
        db.execute(select(Loan).where(Loan.member_id == member_id))
        .scalars()
        .all()
    )

    total_deposits = sum((a.balance for a in accounts), Decimal("0"))
    total_loan_balance = sum((lo.current_balance for lo in loans), Decimal("0"))
    loan_to_deposit_ratio = (
        (total_loan_balance / total_deposits).quantize(Decimal("0.0001"))
        if total_deposits > 0
        else None
    )

    return MemberPortfolio(
        member_id=member_id,
        accounts=[AccountItem.model_validate(a) for a in accounts],
        loans=[LoanItem.model_validate(lo) for lo in loans],
        total_deposits=total_deposits,
        total_loan_balance=total_loan_balance,
        loan_to_deposit_ratio=loan_to_deposit_ratio,
        net_worth=total_deposits - total_loan_balance,
    )


# ---------------------------------------------------------------------------
# Segments summary  (registered under /segments router)
# ---------------------------------------------------------------------------

@segments_router.get("/summary", response_model=SegmentSummaryResponse)
def get_segment_summary(db: Session = Depends(get_db)) -> SegmentSummaryResponse:
    # -- per-member deposit totals -----------------------------------------
    member_deposits = (
        select(
            Account.member_id,
            func.coalesce(func.sum(Account.balance), 0).label("total_deposits"),
        )
        .group_by(Account.member_id)
        .subquery()
    )

    # -- per-member loan totals --------------------------------------------
    member_loans = (
        select(
            Loan.member_id,
            func.coalesce(func.sum(Loan.current_balance), 0).label("total_loan_balance"),
        )
        .group_by(Loan.member_id)
        .subquery()
    )

    # -- segment-level aggregates ------------------------------------------
    # avg LTD computed per-member first, then averaged, so members with no
    # deposits contribute 0 rather than skewing a simple SUM/SUM ratio.
    ltd_per_member = case(
        (member_deposits.c.total_deposits > 0,
         member_loans.c.total_loan_balance / member_deposits.c.total_deposits),
        else_=0,
    )

    segment_agg = (
        db.execute(
            select(
                Member.segment,
                func.count(Member.id).label("member_count"),
                func.avg(
                    func.coalesce(member_deposits.c.total_deposits, 0)
                ).label("avg_deposits"),
                func.avg(
                    func.coalesce(member_loans.c.total_loan_balance, 0)
                ).label("avg_loan_balance"),
                func.avg(ltd_per_member).label("avg_ltd_ratio"),
            )
            .outerjoin(member_deposits, Member.id == member_deposits.c.member_id)
            .outerjoin(member_loans, Member.id == member_loans.c.member_id)
            .group_by(Member.segment)
            .order_by(Member.segment)
        )
        .mappings()
        .all()
    )

    # -- top loan type per segment (window fn approach) --------------------
    # Count (segment, loan_type) pairs, then rank within each segment.
    loan_type_counts = (
        select(
            Member.segment.label("segment"),
            Loan.loan_type.label("loan_type"),
            func.count(Loan.id).label("cnt"),
        )
        .join(Loan, Member.id == Loan.member_id)
        .group_by(Member.segment, Loan.loan_type)
        .subquery()
    )

    # SQLite supports ROW_NUMBER() since 3.25 (2018).
    ranked = (
        select(
            loan_type_counts.c.segment,
            loan_type_counts.c.loan_type,
            func.row_number()
            .over(
                partition_by=loan_type_counts.c.segment,
                order_by=loan_type_counts.c.cnt.desc(),
            )
            .label("rn"),
        ).subquery()
    )

    top_loan_types: dict[str, str] = {
        row.segment: row.loan_type
        for row in db.execute(
            select(ranked.c.segment, ranked.c.loan_type).where(ranked.c.rn == 1)
        ).all()
    }

    # -- assemble response -------------------------------------------------
    stats = []
    for row in segment_agg:
        seg = row["segment"] or "unknown"
        avg_dep = Decimal(str(row["avg_deposits"] or 0))
        avg_ltd = (
            Decimal(str(row["avg_ltd_ratio"])).quantize(Decimal("0.0001"))
            if avg_dep > 0
            else None
        )
        stats.append(
            SegmentStats(
                segment=seg,
                member_count=row["member_count"],
                avg_deposits=avg_dep.quantize(Decimal("0.01")),
                avg_loan_balance=Decimal(str(row["avg_loan_balance"] or 0)).quantize(Decimal("0.01")),
                avg_loan_to_deposit_ratio=avg_ltd,
                top_loan_type=top_loan_types.get(row["segment"]),
            )
        )

    return SegmentSummaryResponse(segments=stats)
