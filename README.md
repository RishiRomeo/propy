# propy

This pipeline accepts raw OCR deed text and sends it to Claude (Anthropic) for structured field extraction. The extracted county is fuzzy-matched against a local `counties.json` reference file to resolve the applicable tax rate. There are guardrails in place to flag review from a human in the loop instead of gracefully exiting. These guardrails flags any ocr text from being passed to the LLM with a recorded date earlier than a signed date, and also flags discrepancies between the numerical int (amount) and written out number.


## Prerequisites
`python ">=3.11"` - single script run
`uv` - single script https://docs.astral.sh/uv/getting-started/installation/
`DockerDesktop` - Docker / Swagger
anthropic API key - [https://platform.claude.com/docs/en/api/admin/api_keys/retrieve ](https://platform.claude.com/settings/keys)

## Running the code

### Option 1: Local (zero-setup) - easiest for non-engineers

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run main.py
```

Dependencies auto-resolve from the inline [PEP 723](https://peps.python.org/pep-0723/) script metadata — no `uv sync` or virtual environment needed.

### Option 2: Docker + Swagger UI

```bash
# 1. Create a .env file
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# 2. Start the stack
make up

# 3. Open the interactive docs
open http://localhost:8000/docs
```

- Click **Try it out** on the `POST /validate-deed` endpoint, then **Execute**.
- The default payload is pre-filled with sample OCR text but you can change this to any deed text.
- *This port will remain open until you tear the container down using the command in the next step*
- Tear down with `make down`.

<!-- screenshot: swagger ui -->

## Example response

```json
{
  "deed": {
    "doc_number": "DEED-TRUST-0042",
    "county": "S. Clara",
    "state": "CA",
    "date_signed": "2024-01-15",
    "date_recorded": "2024-01-10",
    "grantor": "T.E.S.L.A. Holdings LLC",
    "grantee": "John & Sarah Connor",
    "amount_numeric": 1250000.0,
    "amount_written": "One Million Two Hundred Thousand Dollars",
    "apn": "992-001-XA",
    "status": "PRELIMINARY",
    "county_resolved": "Santa Clara",
    "tax_rate": 0.012
  },
  "estimated_annual_tax": 15000.0,
  "validation_flags": [
    "DATE INTEGRITY ERROR: date_recorded (2024-01-10) is BEFORE date_signed (2024-01-15). This is legally impossible and must be reviewed.",
    "AMOUNT DISCREPANCY: Numeric amount ($1,250,000.00) does not match written amount ('One Million Two Hundred Thousand Dollars' = $1,201,200.00). Difference: $48,800.00. Accepting numeric value as canonical."
  ],
  "flag_count": 2
}
```

<!-- screenshot: example response -->
