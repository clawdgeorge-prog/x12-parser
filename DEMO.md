# X12 Parser — Demo

## What this demo shows

1. **Parse** an 835 EDI file → structured JSON
2. **Validate** an 835 EDI file → structural report
3. **Parse** an 837 EDI file → structured JSON
4. **Validate** a clean fixture → clean pass
5. **Summarize** an 835 or 837 file → human-readable summary (money amounts, claim counts, discrepancies)
6. **Export** → CSV, NDJSON, or SQLite-ready normalized CSV bundle

> Note: 837 Dental is included only as a bounded scaffold/demo case. Variant detection works, but dental-specific semantics are not yet deep enough to treat it as full production-grade support.

---

## Run the demo

```bash
# From the project root
./demo/run.sh
```

Or run each command individually:

```bash
# Parse 835 → JSON (compact)
python3 -m src.cli tests/fixtures/sample_835.edi --compact

# Summarize 835 → human-readable summary
python3 -m src.cli tests/fixtures/sample_835.edi --summary

# Validate 835 → structural report
python3 -m src.validate tests/fixtures/sample_835.edi

# Parse 837 → JSON (compact)
python3 -m src.cli tests/fixtures/sample_837_prof.edi --compact

# Summarize 837 → human-readable summary (includes HL hierarchy)
python3 -m src.cli tests/fixtures/sample_837_prof.edi --summary

# Validate a clean fixture
python3 -m src.validate tests/fixtures/sample_whitespace_irregular.edi

# Export 835 → CSV (claims, service lines, entities)
python3 -m src.cli tests/fixtures/sample_835.edi --format csv -o extracts/

# Export 835 → NDJSON (newline-delimited JSON, one record per line)
python3 -m src.cli tests/fixtures/sample_835.edi --format ndjson

# Export 835 → SQLite bundle (normalized CSVs + schema.sql)
python3 -m src.cli tests/fixtures/sample_835.edi --format sqlite -o db_export/
```

---

## Sample output

### Parse 835 — key fields extracted

```
↳ Interchange sender:  SUBMITTER
↳ Interchange receiver: RECEIVER
↳ Transaction type:     835
↳ Loops found:          9
  - 3 loop(s) of kind: entity
  - 2 loop(s) of kind: service
  - 2 loop(s) of kind: claim
  - 1 loop(s) of kind: adjustment
  - 1 loop(s) of kind: payment
```

### Validate 835 — structural report

```
============================================================
X12 STRUCTURAL VALIDATION REPORT
============================================================

❌  1 ERROR(S):
  [SE_COUNT_MISMATCH] [pos 32]  Transaction 1: SE declares 28
  segments, but found 30 (positions 3–32)

============================================================
Result: ERRORS FOUND
============================================================
```

> The SE count mismatch is a known data quirk in the sample fixture —
> `validate.py` is working correctly by detecting it.

### Parse 837 — key fields extracted

```
↳ Interchange sender:  SUBMITTER
↳ Interchange receiver: RECEIVER
↳ Transaction type:     837
↳ Loops found:          12
  - 4 loop(s) of kind: entity
  - 3 loop(s) of kind: hierarchy
  - 2 loop(s) of kind: claim
  - 1 loop(s) of kind: service
  - 1 loop(s) of kind: diagnosis
  - 1 loop(s) of kind: header
```

### Validate clean fixture

```
============================================================
X12 STRUCTURAL VALIDATION REPORT
============================================================

✅  No structural errors found.

============================================================
Result: CLEAN
============================================================
```

### Export CSV — sample claims_835.csv output

```
claim_id,status_code,clp_billed,clp_paid,svc_billed,svc_paid,service_line_count,payer_name,provider_name,...
CLP001,?,0.00,0.00,250.00,150.00,1,INSURANCE COMPANY ONE,PROVIDER CLINIC,...
CLP002,?,0.00,0.00,150.00,120.00,1,INSURANCE COMPANY ONE,PROVIDER CLINIC,...
```

### Export NDJSON — sample records

```
{"_record_type": "interchange", "interchange_ctrl": "000000001", ...}
{"_record_type": "functional_group", "gs_version": "005010X221A1", ...}
{"_record_type": "transaction_set", "set_id": "835", "summary": {...}, ...}
{"_record_type": "loop", "loop_id": "PR", "loop_kind": "entity", ...}
```

---

## Output format — parsed JSON

The parser emits nested JSON:

```json
{
  "version": "0.1.0",
  "interchanges": [
    {
      "header": { "tag": "ISA", "elements": { "e1": "00", ... }, "raw": "ISA*00*..." },
      "isa06_sender": "SUBMITTER",
      "isa08_receiver": "RECEIVER",
      "functional_groups": [
        {
          "header": { "tag": "GS", ... },
          "transactions": [
            {
              "header": { "tag": "ST", ... },
              "set_id": "835",
              "loops": [
                {
                  "id": "PR",
                  "leader_tag": "N1",
                  "leader_code": "PR",
                  "kind": "entity",
                  "description": "Payer Name",
                  "segments": [
                    { "tag": "N1", "elements": { "e1": "PR", "e2": "INSURANCE COMPANY ONE", ... } }
                  ]
                }
              ],
              "trailer": { "tag": "SE", ... }
            }
          ],
          "trailer": { "tag": "GE", ... }
        }
      ],
      "trailer": { "tag": "IEA", ... }
    }
  ]
}
```

Each `elements` dict maps `e{N}` (1-based) to its raw string value.

---

## Output modes reference

| Format | Flag | Output | Use case |
|--------|------|--------|----------|
| JSON (default) | `--format json` | Full nested JSON | Full structure, loop-level detail |
| NDJSON | `--format ndjson` | One JSON object per line | Streaming, log-friendly, large files |
| CSV | `--format csv -o dir/` | Flat CSV files per record type | Spreadsheet review, analytics |
| SQLite | `--format sqlite -o dir/` | Normalized CSVs + schema.sql | Database import, SQL queries |

### CSV/SQLite bundle — file inventory

| File | Description |
|------|-------------|
| `claims_835.csv` | One row per CLP loop (835 remits) |
| `claims_837.csv` | One row per CLM loop (837 claims) |
| `service_lines.csv` | One row per SVC/SV1/SV2 service line |
| `entities.csv` | One row per NM1/N1 entity (payer, provider, patient) |
| `interchanges.csv` | One row per ISA envelope |
| `functional_groups.csv` | One row per GS envelope |
| `transactions.csv` | One row per ST/SE transaction set |
| `schema.sql` | SQLite CREATE TABLE statements |
| `IMPORT_GUIDE.txt` | Quick-reference import commands |

---

## Pre-generated outputs

| File | Description |
|------|-------------|
| `sample_835_parsed.json` | Pre-generated compact JSON for `sample_835.edi` |
| `sample_835_validate.txt` | Validation report for `sample_835.edi` (shows error) |
| `sample_ws_validate.txt`  | Validation report for the whitespace-irregular fixture (clean) |
