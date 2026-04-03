# X12 Parser — Healthcare EDI 835 / 837

**Version 0.1.0** — Initial release

## Overview

A Python library and CLI for parsing X12 EDI transactions, focused on:

- **835** — Healthcare Claim Payment/Advice
- **837** — Healthcare Claim (Professional & Institutional)

> **v0.1.0 positioning:** A practical parser / extractor for common 835 and 837 structures. Suitable for prototyping, inspection, and downstream transformation. Not yet a full X12 standards validator — loop IDs are inferred heuristically and no schema or semantic validation is performed.

## Project Structure

```
x12-parser/
├── src/
│   ├── __init__.py       — package init
│   ├── parser.py        — core parser (tokenizer, segment, loop, transaction)
│   ├── cli.py            — CLI: parse and emit JSON
│   └── validate.py       — CLI: structural validation report
├── tests/
│   ├── test_parser.py    — pytest-based tests
│   └── fixtures/
│       ├── sample_835.edi              — basic 835 (2 claims, 2LX)
│       ├── sample_835_rich.edi          — richer 835 (PLB, ADJ, multiple N1/REF)
│       ├── sample_837_prof.edi          — basic 837 professional
│       ├── sample_837_prof_rich.edi      — richer 837 professional (more HL levels)
│       ├── sample_837_institutional.edi   — basic 837 institutional
│       ├── sample_multi_transaction.edi   — multiple ST/SE in one GS/GE
│       ├── sample_multi_interchange.edi  — multiple ISA/IEA interchanges
│       └── sample_whitespace_irregular.edi — irregular CR/LF/space layout
├── run_tests.py          — manual test runner (no pytest needed)
└── pyproject.toml
```

## Installation

```bash
# No external dependencies (stdlib only)
pip install -e .
```

## Usage

### Python API

```python
from src.parser import parse_file, parse, X12Parser

# Parse from file
parser = X12Parser.from_file("sample.edi")
print(parser.to_json())

# Parse from string
from src.parser import parse
p = parse(edi_text)
print(p.to_json())
```

### CLI — Parse mode

```bash
# Print JSON to stdout
python3 -m src.cli tests/fixtures/sample_835.edi

# Write JSON to file
python3 -m src.cli tests/fixtures/sample_835.edi -o output.json

# Compact (no indentation)
python3 -m src.cli tests/fixtures/sample_835.edi --compact
```

### CLI — Validate mode

```bash
# Human-readable structural validation report
python3 -m src.validate tests/fixtures/sample_835.edi

# Report + JSON output
python3 -m src.validate tests/fixtures/sample_835.edi -o validation.json

# Compact (for machine consumption)
python3 -m src.validate tests/fixtures/sample_835.edi --compact
```

Validate mode checks:
- ISA / IEA interchange pairing and count match
- GS / GE functional group pairing and count match
- ST / SE transaction set pairing and count match
- Orphan segments (segments appearing outside valid envelopes)
- Empty groups or transactions (GS..GE or ST..SE with no inner content)
- Malformed nesting signals (segment count mismatches)

Exit code: `0` = clean, `1` = structural errors found, `2` = could not parse.

### Run Tests

```bash
# With pytest
PYTHONPATH=. python3 -m pytest tests/test_parser.py -v

# Without pytest
python3 run_tests.py
```

## Support Matrix — v0.1.0

### Envelope Structure

| Segment | Description | Status |
|---------|-------------|--------|
| ISA/IEA | Interchange envelope | ✅ Parsed |
| GS/GE | Functional group envelope | ✅ Parsed |
| ST/SE | Transaction set framing | ✅ Parsed |

### 835 Segments Detected

| Segment | Name | Status |
|---------|------|--------|
| BPR | Financial Information | ✅ Detected & preserved |
| TRN | Trace Number | ✅ Detected & preserved |
| DTM | Date/Time Reference | ✅ Detected & preserved |
| N1 | Payer/Provider Name | ✅ Detected & preserved |
| N3/N4 | Address | ✅ Detected & preserved |
| REF | Reference Identification | ✅ Detected & preserved |
| LX | Claim/Service Line Counter | ✅ Detected & preserved |
| CLP | Claim Information | ✅ Detected & preserved |
| CAS | Claim-level Adjustments | ✅ Detected & preserved |
| NM1 | Individual Name (QC, PR, PE) | ✅ Detected & preserved |
| SVC | Service Line Information | ✅ Detected & preserved |
| ADJ | Adjustment | ✅ Detected & preserved |
| SE | Transaction Set Trailer | ✅ Parsed |
| GE | Functional Group Trailer | ✅ Parsed |
| IEA | Interchange Trailer | ✅ Parsed |

### 837 Segments Detected

| Segment | Name | Status |
|---------|------|--------|
| BHT | Beginning of Hierarchical Transaction | ✅ Detected & preserved |
| HL | Hierarchical Level | ✅ Detected & preserved |
| NM1 | Name segments (85 IL PR 41 40 77 77 etc.) | ✅ Detected & preserved |
| PER | Contact Information | ✅ Detected & preserved |
| SBR | Subscriber Information | ✅ Detected & preserved |
| CLM | Claim Information | ✅ Detected & preserved |
| HI | Health Care Diagnosis Codes | ✅ Detected & preserved |
| SV1 | Professional Service (CMS-1500) | ✅ Detected & preserved |
| SV2 | Institutional Service (UB-04) | ✅ Detected & preserved |
| DTP | Date/Time | ✅ Detected & preserved |
| REF | Reference | ✅ Detected & preserved |
| N3/N4 | Address | ✅ Detected & preserved |
| DMG | Demographic Information | ✅ Detected & preserved |
| SE | Transaction Set Trailer | ✅ Parsed |

## Assumptions

1. **Delimiter detection** — v0.1.0 assumes standard X12 delimiters: `*` (element separator), `:` (component separator), `~` (segment terminator). Non-standard separators may cause incorrect parsing.
2. **Repetition separator** — ISA-11 (repetition separator) is treated as `^` but is not currently used to split fields.
3. **Fixed-width ISA** — The ISA is assumed to be in the standard X12 fixed-width format (position-based) and element positions are extracted accordingly.
4. **Loop construction** — Loops are inferred heuristically from segment leader patterns (NM1, CLM, N1, LX, etc.) rather than explicit loop IDs in the data. Loop IDs in output may not match official X12 loop nomenclature.
5. **Composite elements** — Returned as raw strings (e.g., `12:345`) — not decomposed into sub-components.
6. **ISA sender/receiver** — ISA-06 is the sender ID; ISA-08 is the receiver ID.

## Known Limitations

- ❌ No X12 schema validation (segment order, required elements, code values)
- ❌ No cross-segment semantic validation (e.g., CLP amount vs. SVC amount reconciliation)
- ❌ No 277/278/834 transaction support
- ❌ No handling of transaction sets without ISA/IEA wrappers (bare ST/SE)
- ❌ No handling of escaped delimiters within data elements
- ❌ No unicode/escape character handling beyond basic UTF-8
- ⚠️ Loop IDs are inferred heuristically — may not match official X12 loop nomenclature
- ⚠️ Large files not stress-tested
- ⚠️ validate.py performs structural/envelope validation only — it is not an X12 schema validator

## Output Format

The parser produces JSON with this structure:

```json
{
  "version": "0.1.0",
  "interchanges": [
    {
      "header": { "tag": "ISA", "elements": {...}, "raw": "...", "position": 1 },
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
                  "segments": [{ "tag": "N1", "elements": {...} }]
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

Each `elements` dict maps `e{N}` (1-based) → raw string value.
