"""
llm_helpers.py

Handles:
- Loading reference data from counties.json
- LLM-based extraction of deed fields via Anthropic Claude
- Fuzzy county name matching (deterministic, not LLM-dependent)
- Guardrail validations (date logic, amount discrepancy)
"""

import json
import logging
import re
import warnings
from datetime import datetime
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path

import anthropic
from word2number import w2n

logger = logging.getLogger(__name__)

def load_counties(path: str = "counties.json") -> list[dict]:
    """Load county reference data from a local JSON file."""
    file_path = Path(__file__).parent / path
    if not file_path.exists():
        raise FileNotFoundError(f"Counties file not found at: {file_path.resolve()}")
    with open(file_path, "r") as f:
        counties = json.load(f)
    logger.info("Loaded %d counties from %s", len(counties), path)
    return counties



_ABBREVIATION_MAP: dict[str, list[str]] = {
    "s.":  ["santa", "san", "south", "saint"],
    "sn.": ["san"],
    "st.": ["saint"],
    "n.":  ["north", "new"],
    "ft.": ["fort"],
    "mt.": ["mount", "mountain"],
    "e.":  ["east"],
    "w.":  ["west"],
}


def _expand_abbreviations(text: str) -> list[str]:
    """
    Generate all plausible expansions of abbreviated county names.

    Instead of guessing which expansion is correct,  produce every
    candidate and let the fuzzy matcher score them against the reference
    list.  This way 'S. Clara' -> ['santa clara', 'san clara', 'south clara', ...]
    and difflib picks 'santa clara' because that is what exists in
    counties.json. 
    """
    tokens = text.lower().split()
    candidates: list[list[str]] = [[]]

    for token in tokens:
        if token in _ABBREVIATION_MAP:
            candidates = [
                existing + [expansion]
                for existing in candidates
                for expansion in _ABBREVIATION_MAP[token]
            ]
        else:
            candidates = [existing + [token] for existing in candidates]

    return [" ".join(c) for c in candidates]


def match_county(raw_name: str, counties: list[dict]) -> dict | None:
    """
    Match a potentially abbreviated / messy county name against the
    reference list by expanding all possible abbreviations and picking
    the best fuzzy match across all candidates.
    """
    county_lookup = {c["name"].lower(): c for c in counties}
    county_names_lower = list(county_lookup.keys())

    candidates = _expand_abbreviations(raw_name.strip())
    logger.debug("County expansion candidates: %s", candidates)

    best_match: str | None = None
    best_score: float = 0.0

    for candidate in candidates:
        if candidate in county_lookup:
            logger.info("Exact county match: '%s' -> '%s'", raw_name, county_lookup[candidate]["name"])
            return county_lookup[candidate]

        close = get_close_matches(candidate, county_names_lower, n=1, cutoff=0.6)
        if close:
            score = SequenceMatcher(None, candidate, close[0]).ratio()
            if score > best_score:
                best_score = score
                best_match = close[0]

    if best_match:
        matched = county_lookup[best_match]
        logger.info("Fuzzy county match: '%s' -> '%s' (score: %.3f)", raw_name, matched["name"], best_score)
        return matched

    logger.warning("No county match found for: '%s'", raw_name)
    return None


_EXTRACTION_PROMPT = """\
You are a document-parsing assistant.  Extract the following fields from the
OCR-scanned deed text below and return ONLY valid JSON (no markdown, no
explanation).

Required JSON keys:
- doc_number        (string)
- county            (string, as written in the document)
- state             (string)
- date_signed       (string, ISO-8601: YYYY-MM-DD)
- date_recorded     (string, ISO-8601: YYYY-MM-DD)
- grantor           (string)
- grantee           (string)
- amount_numeric    (number -- the dollar figure as a plain number, no symbols)
- amount_written    (string -- the written-out dollar amount exactly as it appears)
- apn               (string)
- status            (string)

OCR Text:
{ocr_text}
"""


def extract_deed_data(ocr_text: str, model: str = "claude-sonnet-4-20250514") -> dict:
    """
    Send the raw OCR text to Claude and get back a structured dict of deed
    fields.
    """
    client = anthropic.Anthropic()

    logger.info("Sending OCR text to Claude (%s) for extraction", model)

    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": _EXTRACTION_PROMPT.format(ocr_text=ocr_text),
            }
        ],
    )

    raw_response = message.content[0].text
    logger.info("Received LLM response")
    logger.debug("Raw LLM response:\n%s", raw_response)

    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_response.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM response as JSON: %s", exc)
        raise ValueError(f"LLM did not return valid JSON: {exc}") from exc

    return data


def validate_dates(date_signed: str, date_recorded: str) -> None:
    """
    GUARDRAIL 1: date_recorded must NEVER be before date_signed.

    If it is, we raise a warning (not an exception) so the pipeline can
    continue while the issue is flagged for human review.
    """
    try:
        signed = datetime.fromisoformat(date_signed)
        recorded = datetime.fromisoformat(date_recorded)
    except ValueError as exc:
        warnings.warn(
            f"Could not parse dates for validation -- date_signed='{date_signed}', "
            f"date_recorded='{date_recorded}': {exc}",
            UserWarning,
            stacklevel=2,
        )
        return

    if recorded < signed:
        warnings.warn(
            f"DATE INTEGRITY ERROR: date_recorded ({date_recorded}) is BEFORE "
            f"date_signed ({date_signed}). This is legally impossible and must "
            f"be reviewed.",
            UserWarning,
            stacklevel=2,
        )
        logger.warning(
            "Date integrity failure -- recorded %s < signed %s",
            date_recorded,
            date_signed,
        )
    else:
        logger.info("Date check passed: signed %s -> recorded %s", date_signed, date_recorded)


def _parse_written_amount(written: str) -> int | None:
    """
    Best-effort conversion of a written dollar string to an integer.
    Returns None if parsing fails.
    """
    cleaned = written.lower()
    cleaned = cleaned.replace("dollars", "").replace("dollar", "")
    cleaned = cleaned.replace(",", "").replace("-", " ").strip()

    try:
        return w2n.word_to_num(cleaned)
    except ValueError:
        logger.warning("Could not convert written amount to number: '%s'", written)
        return None


def validate_amounts(amount_numeric: float, amount_written: str) -> None:
    """
    GUARDRAIL 2: Compare the numeric dollar amount with the written-out
    amount.  If they differ, raise a warning and accept the numeric value
    as canonical.
    """
    written_value = _parse_written_amount(amount_written)

    if written_value is None:
        warnings.warn(
            f"AMOUNT PARSE WARNING: Could not interpret the written amount "
            f"'{amount_written}'. Accepting numeric value ${amount_numeric:,.2f} "
            f"as canonical.",
            UserWarning,
            stacklevel=2,
        )
        return

    if abs(amount_numeric - written_value) > 0.01:
        warnings.warn(
            f"AMOUNT DISCREPANCY: Numeric amount (${amount_numeric:,.2f}) does not "
            f"match written amount ('{amount_written}' = ${written_value:,.2f}). "
            f"Difference: ${abs(amount_numeric - written_value):,.2f}. "
            f"Accepting numeric value as canonical.",
            UserWarning,
            stacklevel=2,
        )
        logger.warning(
            "Amount mismatch -- numeric=%.2f, written=%d, diff=%.2f",
            amount_numeric,
            written_value,
            abs(amount_numeric - written_value),
        )
    else:
        logger.info(
            "Amount check passed: numeric=$%s matches written='%s'",
            f"{amount_numeric:,.2f}",
            amount_written,
        )