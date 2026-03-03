# propy

Propy sends raw OCR deed text to Claude (Anthropic) for structured field extraction. The extracted county is fuzzy-matched against a local `counties.json` reference file to resolve applicable tax rates. Two deterministic guardrail validations then run: (1) date integrity — `date_recorded` must not precede `date_signed`, and (2) amount discrepancy — the numeric dollar amount is compared against the written-out amount. Validation flags are surfaced in the response rather than halting the pipeline, so issues are flagged for human review. Estimated annual property tax is calculated from the resolved county tax rate.

---

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — for dependency management and running scripts
- **Docker & Docker Compose** — only needed for Option 2 (Docker/Swagger approach)
- **An Anthropic API key** — get one from https://console.anthropic.com/settings/keys

---

## Running the Code

### Option 1: Local (zero-setup)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run main.py
```

Dependencies auto-resolve from the inline PEP 723 script metadata — no `uv sync` or venv needed. Output is printed as JSON to stdout.

---

### Option 2: Docker + Swagger UI

1. Create a `.env` file with your API key (no quotes around the value):
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

2. Build the image and start the container:
   ```bash
   make up
   ```
   Swagger UI will be available at `http://localhost:8000/docs`.

3. Open `http://localhost:8000/docs` in your browser.

4. Click **Try it out** on the `POST /validate-deed` endpoint and hit **Execute**. The default payload is pre-filled with sample OCR text.

5. To stop the container:
   ```bash
   make down
   ```

<!-- screenshot: swagger ui -->

#### Makefile commands

| Command | Description |
|---------|-------------|
| `make up` | Build image and start container (Swagger at http://localhost:8000/docs) |
| `make down` | Stop and remove the container |
| `make build` | Build the Docker image without starting |
| `make logs` | Tail container logs |

---

## Example Response

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
