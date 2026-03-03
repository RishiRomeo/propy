"""
main.py

Propy "Bad Deed" Validator
--------------------------
Orchestrates the full pipeline:
  1. Feed raw OCR text to Claude for structured extraction.
  2. Fuzzy-match the county name against counties.json for tax data.
  3. Run guardrail validations (dates, amounts).
  4. Calculate estimated closing costs.
  5. Output validated deed as JSON.
"""

import json
import logging
import warnings

from helpers.llm_helpers import (
    extract_deed_data,
    load_counties,
    match_county,
    validate_amounts,
    validate_dates,
)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

RAW_OCR_TEXT = """
*** RECORDING REQ ***
Doc: DEED-TRUST-0042
County: S. Clara  |  State: CA
Date Signed: 2024-01-15
Date Recorded: 2024-01-10
Grantor:  T.E.S.L.A. Holdings LLC
Grantee:  John  &  Sarah  Connor
Amount: $1,250,000.00 (One Million Two Hundred Thousand Dollars)
APN: 992-001-XA
Status: PRELIMINARY
*** END ***
""".strip()


def main() -> None:
    counties = load_counties("counties.json")
    deed = extract_deed_data(RAW_OCR_TEXT)

    matched_county = match_county(deed.get("county", ""), counties)

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

    flags: list[str] = []
    for w in caught_warnings:
        flag_message = str(w.message)
        flags.append(flag_message)
        logger.warning("VALIDATION FLAG: %s", flag_message)

    amount = deed.get("amount_numeric", 0)
    tax_rate = deed.get("tax_rate")
    estimated_tax = amount * tax_rate if tax_rate and amount else None

    output = {
        "deed": deed,
        "estimated_annual_tax": estimated_tax,
        "validation_flags": flags,
        "flag_count": len(flags),
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()