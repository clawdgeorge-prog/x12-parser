# X12 Parser — Demo

## What this demo shows

1. **Parse** an 835 EDI file → structured JSON
2. **Validate** an 835 EDI file → structural report
3. **Parse** an 837 EDI file → structured JSON
4. **Validate** a clean fixture → clean pass
5. **Summarize** an 835 or 837 file → human-readable summary (money amounts, claim counts, discrepancies)

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

## Pre-generated outputs

| File | Description |
|------|-------------|
| `sample_835_parsed.json` | Pre-generated compact JSON for `sample_835.edi` |
| `sample_835_validate.txt` | Validation report for `sample_835.edi` (shows error) |
| `sample_ws_validate.txt`  | Validation report for the whitespace-irregular fixture (clean) |
