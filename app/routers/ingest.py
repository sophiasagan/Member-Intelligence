"""
POST /ingest — accept one or more CSV file uploads and run the ETL pipeline.

Accepts multipart/form-data with fields: members, accounts, loans
(any combination; at least one required).

Example curl:
    curl -X POST http://localhost:8000/ingest \
      -F "members=@data/raw/members.csv" \
      -F "accounts=@data/raw/accounts.csv" \
      -F "loans=@data/raw/loans.csv"
"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.services.etl import run_etl

router = APIRouter(prefix="/ingest", tags=["ingest"])

_VALID_KEYS = {"members", "accounts", "loans"}


@router.post("", status_code=status.HTTP_200_OK)
async def ingest_csvs(
    members: UploadFile | None = File(default=None),
    accounts: UploadFile | None = File(default=None),
    loans: UploadFile | None = File(default=None),
) -> dict:
    """
    Upload CSV files to ingest into the database.

    - At least one of `members`, `accounts`, or `loans` must be provided.
    - Files must be CSV format.
    - `members` is processed before `accounts` and `loans` to satisfy FK constraints.
    """
    uploads: dict[str, UploadFile] = {
        k: v
        for k, v in {"members": members, "accounts": accounts, "loans": loans}.items()
        if v is not None
    }

    if not uploads:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one file (members, accounts, loans) must be provided.",
        )

    for key, upload in uploads.items():
        if upload.content_type not in ("text/csv", "application/csv", "application/octet-stream", "text/plain"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"'{key}' must be a CSV file (got {upload.content_type!r}).",
            )

    # Read all file bytes before passing to sync ETL
    file_bytes: dict[str, bytes] = {}
    for key, upload in uploads.items():
        try:
            file_bytes[key] = await upload.read()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to read file '{key}': {exc}",
            ) from exc

    result = run_etl(file_bytes)

    response: dict = {
        "inserted": result.inserted,
        "skipped": result.skipped,
    }

    if result.errors:
        # Non-fatal validation errors are returned as warnings; DB errors raise 500
        db_errors = [e for e in result.errors if e.startswith("DB commit")]
        validation_warnings = [e for e in result.errors if not e.startswith("DB commit")]

        if db_errors:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"message": "ETL pipeline failed during DB commit.", "errors": db_errors},
            )

        response["warnings"] = validation_warnings

    return response
