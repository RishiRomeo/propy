"""
api.py

FastAPI wrapper around the deed validation pipeline.
Exposes a single POST endpoint that accepts raw OCR text
and returns the validated deed JSON.
"""

import warnings

from fastapi import FastAPI
from pydantic import BaseModel, Field

from helpers.llm_helpers import (
    extract_deed_data,
    load_counties,
    match_county,
    validate_amounts,
    validate_dates,
)

app = FastAPI(
    title="Propy Deed Validator",
    description="Validates OCR-scanned deeds using LLM extraction and deterministic guardrails.",
    version="0.1.0",
)

COUNTIES = load_counties("counties.json")

RAW_OCR_DEFAULT = """*** RECORDING REQ ***
Doc: DEED-TRUST-0042
County: S. Clara  |  State: CA
Date Signed: 2024-01-15
Date Recorded: 2024-01-10
Grantor:  T.E.S.L.A. Holdings LLC
Grantee:  John  &  Sarah  Connor
Amount: $1,250,000.00 (One Million Two Hundred Thousand Dollars)
APN: 992-001-XA
Status: PRELIMINARY
*** END ***"""


class DeedRequest(BaseModel):
    ocr_text: str = Field(
        default=RAW_OCR_DEFAULT,
        description="Raw OCR-scanned deed text to validate.",
    )


class DeedResponse(BaseModel):
    deed: dict
    estimated_annual_tax: float | None
    validation_flags: list[str]
    flag_count: int


@app.post("/validate-deed", response_model=DeedResponse)
def validate_deed(request: DeedRequest) -> DeedResponse:
    deed = extract_deed_data(request.ocr_text)

    matched_county = match_county(deed.get("county", ""), COUNTIES)

    if matched_county:
        deed["county_resolved"] = matched_county["name"]
        deed["tax_rate"] = matched_county["tax_rate"]
    else:
        deed["county_resolved"] = None
        deed["tax_rate"] = None

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        validate_dates(deed.get("date_signed", ""), deed.get("date_recorded", ""))
        validate_amounts(deed.get("amount_numeric", 0), deed.get("amount_written", ""))

    flags = [str(w.message) for w in caught_warnings]

    amount = deed.get("amount_numeric", 0)
    tax_rate = deed.get("tax_rate")
    estimated_tax = amount * tax_rate if tax_rate and amount else None

    return DeedResponse(
        deed=deed,
        estimated_annual_tax=estimated_tax,
        validation_flags=flags,
        flag_count=len(flags),
    )