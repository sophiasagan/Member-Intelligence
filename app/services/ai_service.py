"""
AI service — wraps the Anthropic SDK to produce member insights.

Public API:
    from app.services.ai_service import generate_member_insight
    insight = generate_member_insight(member_data)
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal

import anthropic

from app.config import get_settings
from app.schemas.insights import MemberInsight

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """\
You are an expert credit union member advisor with deep knowledge of personal finance, \
lending, and deposit products. Your role is to review a member's financial profile and \
provide clear, actionable intelligence to credit union staff.

When analysing a member you must always return a single JSON object — no markdown fences, \
no prose outside the object — with exactly these three keys:

  "narrative"               – string: 2–3 paragraphs of plain-English summary covering the \
member's financial health, account activity, loan obligations, and tenure with the credit union. \
Write for a staff member who will use this during a member service call.

  "risk_flags"              – array of strings: each flag is a concise, specific concern \
(e.g. high loan-to-deposit ratio, delinquent loan status, single account dependency). \
Return an empty array if there are no material concerns.

  "cross_sell_opportunities" – array of strings: each item is a specific product or service \
the member does not currently hold that would genuinely benefit them given their profile \
(e.g. "Open a money-market account to earn higher yield on $42,000 idle checking balance", \
"Auto loan refinance — current rate 9.5% is above current market"). \
Return an empty array if no clear opportunities exist.

Be factual and grounded in the data provided. Do not invent figures. \
Do not use generic advice that would apply to any member.\
"""


def _format_member_context(data: dict) -> str:
    """Render member_data as a structured plain-text block for the user message."""

    def fmt_money(val) -> str:
        try:
            return f"${Decimal(str(val)):,.2f}"
        except Exception:
            return str(val)

    lines: list[str] = ["=== MEMBER PROFILE ==="]

    # Identity / tenure
    lines += [
        f"Name:          {data.get('first_name', '')} {data.get('last_name', '')}",
        f"Member number: {data.get('member_number', 'N/A')}",
        f"Member since:  {data.get('member_since', 'N/A')}",
        f"Tenure:        {data.get('tenure_years', 'N/A')} years",
        f"Segment:       {data.get('segment', 'N/A')}",
        f"ZIP code:      {data.get('zip_code', 'N/A')}",
    ]

    # Portfolio totals
    lines += [
        "",
        "=== PORTFOLIO TOTALS ===",
        f"Total deposits:       {fmt_money(data.get('total_deposits', 0))}",
        f"Total loan balance:   {fmt_money(data.get('total_loan_balance', 0))}",
        f"Net worth (deposits – loans): {fmt_money(data.get('net_worth', 0))}",
    ]

    ltd = data.get("loan_to_deposit_ratio")
    lines.append(
        f"Loan-to-deposit ratio: {float(ltd):.2%}" if ltd is not None else
        "Loan-to-deposit ratio: N/A (no deposits)"
    )

    # Accounts
    accounts: list[dict] = data.get("accounts", [])
    lines += ["", f"=== ACCOUNTS ({len(accounts)}) ==="]
    if accounts:
        for acct in accounts:
            lines.append(
                f"  • {acct.get('account_type', '?').upper():14s} "
                f"balance={fmt_money(acct.get('balance', 0))}  "
                f"status={acct.get('status', '?')}  "
                f"opened={acct.get('opened_date', '?')}"
            )
    else:
        lines.append("  (none)")

    # Loans
    loans: list[dict] = data.get("loans", [])
    lines += ["", f"=== LOANS ({len(loans)}) ==="]
    if loans:
        for loan in loans:
            rate = loan.get("interest_rate", 0)
            try:
                rate_str = f"{float(rate):.2%}"
            except Exception:
                rate_str = str(rate)
            lines.append(
                f"  • {loan.get('loan_type', '?').upper():10s} "
                f"current_balance={fmt_money(loan.get('current_balance', 0))}  "
                f"rate={rate_str}  "
                f"status={loan.get('status', '?')}  "
                f"matures={loan.get('maturity_date', '?')}"
            )
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def generate_member_insight(member_data: dict) -> MemberInsight:
    """
    Call Claude to generate a structured insight for a single member.

    Args:
        member_data: dict with member fields + portfolio totals + accounts/loans lists.
                     Typically built from MemberPortfolio + MemberDetail responses.

    Returns:
        MemberInsight with narrative, risk_flags, cross_sell_opportunities.

    Raises:
        ValueError: if the model returns malformed JSON.
        anthropic.APIError: propagated on API-level failures.
    """
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    user_message = (
        "Please analyse the following credit union member and return the JSON insight object.\n\n"
        + _format_member_context(member_data)
    )

    logger.debug("Sending member %s to %s", member_data.get("member_number"), _MODEL)

    message = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = message.content[0].text.strip()
    logger.debug("Raw model response: %s", raw[:200])

    # Slice from first { to last } — handles markdown fences or any leading/trailing prose
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        logger.error("Model returned non-JSON response: %r", raw)
        raise ValueError(f"Model returned non-JSON response: {raw[:200]!r}")
    json_str = raw[start:end]

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.error("Model returned unparseable JSON: %r", json_str)
        raise ValueError(f"Model returned non-JSON response: {exc}") from exc

    return MemberInsight(
        narrative=parsed.get("narrative", ""),
        risk_flags=parsed.get("risk_flags", []),
        cross_sell_opportunities=parsed.get("cross_sell_opportunities", []),
    )
