"""
ETL pipeline: read CSVs → clean → load into SQLite via SQLAlchemy.

Supports three file types keyed by filename stem:
  members, accounts, loans

Usage (programmatic):
    from app.services.etl import run_etl
    result = run_etl({"members": Path("data/raw/members.csv")})

Usage (CLI):
    python -m app.services.etl data/raw/members.csv data/raw/accounts.csv data/raw/loans.csv
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

import pandas as pd
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models import Account, Loan, Member

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class ETLResult:
    inserted: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Cleaning helpers
# ---------------------------------------------------------------------------
def _clean_members(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    errors: list[str] = []

    required = ["member_number", "first_name", "last_name", "email",
                 "date_of_birth", "member_since"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        errors.append(f"members CSV missing columns: {missing_cols}")
        return df, errors

    initial_len = len(df)

    # Drop rows missing required fields
    df = df.dropna(subset=required)
    dropped = initial_len - len(df)
    if dropped:
        logger.warning("members: dropped %d rows with null required fields", dropped)

    # Normalise strings
    df["member_number"] = df["member_number"].astype(str).str.strip().str.upper()
    df["email"] = df["email"].astype(str).str.strip().str.lower()
    df["first_name"] = df["first_name"].astype(str).str.strip().str.title()
    df["last_name"] = df["last_name"].astype(str).str.strip().str.title()

    # Validate member_number uniqueness
    dupes = df[df.duplicated("member_number", keep=False)]
    if not dupes.empty:
        dup_vals = dupes["member_number"].unique().tolist()
        errors.append(f"members: duplicate member_numbers found: {dup_vals[:10]}")
        df = df.drop_duplicates("member_number", keep="first")

    # Parse dates
    for col in ("date_of_birth", "member_since"):
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    bad_dates = df[df["date_of_birth"].isna() | df["member_since"].isna()]
    if not bad_dates.empty:
        logger.warning("members: dropping %d rows with unparseable dates", len(bad_dates))
        df = df.dropna(subset=["date_of_birth", "member_since"])

    # Optional fields — fill nulls with sensible defaults
    df["segment"] = df["segment"].fillna("standard").astype(str).str.strip().str.lower()
    df["zip_code"] = df["zip_code"].fillna("00000").astype(str).str.strip().str.zfill(5)

    return df, errors


def _clean_accounts(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    errors: list[str] = []

    required = ["member_number", "account_type", "balance", "opened_date", "status"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        errors.append(f"accounts CSV missing columns: {missing_cols}")
        return df, errors

    df = df.dropna(subset=required)

    df["member_number"] = df["member_number"].astype(str).str.strip().str.upper()
    df["account_type"] = df["account_type"].astype(str).str.strip().str.lower()
    df["status"] = df["status"].astype(str).str.strip().str.lower()

    valid_types = {"checking", "savings", "money_market", "cd"}
    invalid = df[~df["account_type"].isin(valid_types)]
    if not invalid.empty:
        errors.append(
            f"accounts: {len(invalid)} rows with unknown account_type: "
            f"{invalid['account_type'].unique().tolist()}"
        )
        df = df[df["account_type"].isin(valid_types)]

    df["balance"] = pd.to_numeric(df["balance"], errors="coerce").fillna(0.0).round(2)
    df["opened_date"] = pd.to_datetime(df["opened_date"], errors="coerce").dt.date
    df = df.dropna(subset=["opened_date"])

    return df, errors


def _clean_loans(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    errors: list[str] = []

    required = [
        "member_number", "loan_type", "original_balance", "current_balance",
        "interest_rate", "origination_date", "maturity_date", "status",
    ]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        errors.append(f"loans CSV missing columns: {missing_cols}")
        return df, errors

    df = df.dropna(subset=required)

    df["member_number"] = df["member_number"].astype(str).str.strip().str.upper()
    df["loan_type"] = df["loan_type"].astype(str).str.strip().str.lower()
    df["status"] = df["status"].astype(str).str.strip().str.lower()

    valid_types = {"auto", "mortgage", "personal", "heloc"}
    invalid = df[~df["loan_type"].isin(valid_types)]
    if not invalid.empty:
        errors.append(
            f"loans: {len(invalid)} rows with unknown loan_type: "
            f"{invalid['loan_type'].unique().tolist()}"
        )
        df = df[df["loan_type"].isin(valid_types)]

    for col in ("original_balance", "current_balance", "interest_rate"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["original_balance", "current_balance", "interest_rate"])
    df["original_balance"] = df["original_balance"].round(2)
    df["current_balance"] = df["current_balance"].round(2)
    df["interest_rate"] = df["interest_rate"].round(4)

    for col in ("origination_date", "maturity_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    df = df.dropna(subset=["origination_date", "maturity_date"])

    return df, errors


# ---------------------------------------------------------------------------
# DB loaders
# ---------------------------------------------------------------------------
def _load_members(df: pd.DataFrame, db: Session) -> tuple[int, int]:
    """Returns (inserted, skipped)."""
    existing = {m for (m,) in db.query(Member.member_number).all()}
    new_rows = df[~df["member_number"].isin(existing)]
    skipped = len(df) - len(new_rows)

    records = [
        Member(
            member_number=row.member_number,
            first_name=row.first_name,
            last_name=row.last_name,
            email=row.email,
            date_of_birth=row.date_of_birth,
            member_since=row.member_since,
            segment=row.segment,
            zip_code=row.zip_code,
        )
        for row in new_rows.itertuples(index=False)
    ]
    db.bulk_save_objects(records)
    db.flush()
    return len(records), skipped


def _load_accounts(df: pd.DataFrame, db: Session) -> tuple[int, int]:
    member_map: dict[str, int] = {
        mn: mid for mn, mid in db.query(Member.member_number, Member.id).all()
    }
    valid = df[df["member_number"].isin(member_map)]
    skipped = len(df) - len(valid)
    if skipped:
        logger.warning("accounts: skipped %d rows — member_number not found", skipped)

    records = [
        Account(
            member_id=member_map[row.member_number],
            account_type=row.account_type,
            balance=row.balance,
            opened_date=row.opened_date,
            status=row.status,
        )
        for row in valid.itertuples(index=False)
    ]
    db.bulk_save_objects(records)
    db.flush()
    return len(records), skipped


def _load_loans(df: pd.DataFrame, db: Session) -> tuple[int, int]:
    member_map: dict[str, int] = {
        mn: mid for mn, mid in db.query(Member.member_number, Member.id).all()
    }
    valid = df[df["member_number"].isin(member_map)]
    skipped = len(df) - len(valid)
    if skipped:
        logger.warning("loans: skipped %d rows — member_number not found", skipped)

    records = [
        Loan(
            member_id=member_map[row.member_number],
            loan_type=row.loan_type,
            original_balance=row.original_balance,
            current_balance=row.current_balance,
            interest_rate=row.interest_rate,
            origination_date=row.origination_date,
            maturity_date=row.maturity_date,
            status=row.status,
        )
        for row in valid.itertuples(index=False)
    ]
    db.bulk_save_objects(records)
    db.flush()
    return len(records), skipped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
FileInput = Union[Path, bytes, io.BytesIO]

PIPELINE: dict[str, tuple] = {
    "members":  (_clean_members,  _load_members),
    "accounts": (_clean_accounts, _load_accounts),
    "loans":    (_clean_loans,    _load_loans),
}


def _read_csv(source: FileInput) -> pd.DataFrame:
    if isinstance(source, Path):
        return pd.read_csv(source, dtype=str)
    if isinstance(source, bytes):
        return pd.read_csv(io.BytesIO(source), dtype=str)
    return pd.read_csv(source, dtype=str)


def run_etl(files: dict[str, FileInput]) -> ETLResult:
    """
    Process one or more CSV files.

    Args:
        files: mapping of table name → file path or raw bytes.
               Recognised keys: "members", "accounts", "loans".
               Process members before accounts/loans so FKs resolve.
    """
    result = ETLResult()

    # Enforce dependency order
    ordered_keys = [k for k in ("members", "accounts", "loans") if k in files]
    unknown = set(files) - set(PIPELINE)
    if unknown:
        result.errors.append(f"Unknown file keys (ignored): {sorted(unknown)}")

    db = SessionLocal()
    try:
        for key in ordered_keys:
            clean_fn, load_fn = PIPELINE[key]

            try:
                df = _read_csv(files[key])
            except Exception as exc:
                result.errors.append(f"{key}: failed to read CSV — {exc}")
                continue

            df, clean_errors = clean_fn(df)
            result.errors.extend(clean_errors)

            if df.empty:
                logger.warning("%s: no valid rows after cleaning", key)
                result.inserted[key] = 0
                result.skipped[key] = 0
                continue

            inserted, skipped = load_fn(df, db)
            result.inserted[key] = inserted
            result.skipped[key] = skipped
            logger.info("%s: inserted=%d skipped=%d", key, inserted, skipped)

        db.commit()
    except Exception as exc:
        db.rollback()
        result.errors.append(f"DB commit failed: {exc}")
        logger.exception("ETL pipeline rolled back")
    finally:
        db.close()

    return result


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python -m app.services.etl <file1.csv> [file2.csv ...]")
        sys.exit(1)

    file_map: dict[str, FileInput] = {}
    for arg in sys.argv[1:]:
        p = Path(arg)
        stem = p.stem.lower()
        if stem not in PIPELINE:
            print(f"Warning: unrecognised file '{p.name}' (expected members/accounts/loans), skipping")
            continue
        file_map[stem] = p

    outcome = run_etl(file_map)
    print("\nETL Result:")
    print(f"  Inserted: {outcome.inserted}")
    print(f"  Skipped:  {outcome.skipped}")
    if outcome.errors:
        print(f"  Errors:")
        for e in outcome.errors:
            print(f"    - {e}")
    else:
        print("  No errors.")
