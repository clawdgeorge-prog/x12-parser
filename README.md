# X12 Parser

**Parse and validate healthcare EDI 835 and 837 transactions in Python or from the command line.**

```
python3 -m src.cli  sample.edi                  # → JSON
python3 -m src.cli  sample.edi --summary        # → human-readable summary
python3 -m src.validate sample.edi               # → structural report
python3 -m src.validate sample.edi --rules examples/rules/premier-835-companion.sample.json
```

X12 EDI is the dominant interchange format for US healthcare administrative data — claim payments, remittance advices, and professional/institutional claims all travel over X12. This library gives you a plain-Python, dependency-free way to pull that data into structured JSON.

---

## Quickstart

```bash
# Install (no external dependencies — stdlib only)
pip install -e .

# Parse an 835 remittance file → JSON
python3 -m src.cli tests/fixtures/sample_835.edi

# Validate an 835 for structural integrity
python3 -m src.validate tests/fixtures/sample_835.edi

# Run the full demo (4 commands, auto-summarised output)
./demo/run.sh
```

### Python API

```python
from src.parser import X12Parser, parse

# From file
parser = X12Parser.from_file("sample.edi")
print(parser.to_json())

# From string
p = parse(edi_text)
print(p.to_json())
```

---

## Features

### Supported transaction types

| ID  | Name | Status |
|-----|------|--------|
| **835** | Healthcare Claim Payment/Advice | ✅ Parsed + summarized + structurally validated |
| **837 P** | Healthcare Claim — Professional (CMS-1500) | ✅ Parsed + summarized + structurally validated |
| **837 I** | Healthcare Claim — Institutional (UB-04) | ✅ Parsed + summarized + structurally validated |
| **837 D** | Healthcare Claim — Dental | ⚙️ Scaffolded parse + variant detection only |

### Envelope structure

ISA/IEA (interchange) → GS/GE (functional group) → ST/SE (transaction set) are fully parsed, including sender/receiver IDs and segment counts.

### Segment coverage

Common 835 and 837 segments are detected and preserved with raw element extraction. Key segments include BPR, TRN, N1, NM1, CLP, SVC, CAS, HI, CLM, SV1, SV2, and many other common segments in the included fixtures.

### Transaction summaries

Each parsed transaction includes a `summary` block with computed fields:

**835 summary:** `payment_amount`, `check_trace`, `total_billed_amount`, `total_allowed_amount`, `total_paid_amount`, `total_adjustment_amount`, `net_difference`, `claim_count`, `service_line_count`, `plb_count`, `duplicate_claim_ids`, `payer_name`, `provider_name`, `bpr_payment_method`, `bpr_payment_method_label`, `claims`

**837 summary:** `total_billed_amount`, `claim_count`, `service_line_count`, `hl_count`, `duplicate_claim_ids`, `billing_provider`, `payer_name`, `submitter_name`, `subscriber_name`, `patient_name`, `bht_id`, `bht_date`, `variant`, `variant_indicator`, `service_line_type`, `hierarchy`, `claims`

**837 hierarchy semantics** — the `hierarchy` block provides:
- `hl_tree`: full list of HL segments with `id`, `parent_id`, `level_code`, `child_code`, and `level_role` (`billing_provider` / `subscriber` / `patient` / `other`)
- `billing_provider_name`, `subscriber_name`, `patient_name`: entity names extracted from the corresponding NM1 loops
- `billing_provider_hl_id`, `subscriber_hl_id`, `patient_hl_id`: HL segment IDs for each hierarchy level

The `claims` list provides one entry per CLM segment with `claim_id`, `clp_billed`, service-line sub-aggregation, and a `has_discrepancy` flag when CLP billed differs from the sum of SV1/SV2 billed amounts.

**835 reconciliation helpers** — the `claims` list provides per-CLP rollups including:
- `clp_billed`, `clp_paid`, `clp_allowed`, `clp_adjustment` (from CLP and CAS segments)
- `svc_billed`, `svc_paid` (sum of SVC service lines within the claim)
- `service_line_count`
- `has_billed_discrepancy` / `has_paid_discrepancy` flags
- `adjustment_group_codes` (enriched with `code` + `label` from CAS group codes)
- `status_label` (human-readable CLP status description) and `status_category` (paid/pended/denied/etc.)

The `discrepancies` list at transaction level contains one entry per flagged mismatch with `type`, `claim_id`, amounts, and a `note` with guidance.

The `plb_summary` block provides `adjustment_by_code` (PLB reason code → total amount), `adjustment_labels` (code → description), and `total_plb_adjustment` for provider-level adjustments.

### Output

JSON with nested envelopes, functional groups, transaction sets, loops, and per-transaction summaries. Each segment carries its raw `elements` dict (`e1`, `e2`, …) for downstream use.

---

## CLI

### Parse mode

```bash
# Pretty-printed JSON (default)
python3 -m src.cli tests/fixtures/sample_835.edi

# Compact JSON (no indentation)
python3 -m src.cli tests/fixtures/sample_835.edi --compact

# Human-readable summary (money amounts, claim counts, discrepancies)
python3 -m src.cli tests/fixtures/sample_835.edi --summary

# Write to file
python3 -m src.cli tests/fixtures/sample_835.edi -o output.json
```

### Validate mode

Structural validation checks include:

- ISA/IEA, GS/GE, ST/SE envelope pairing
- Orphan segment detection (envelope segments appearing outside valid context)
- Empty transaction / empty group detection
- SE segment-count signal validation
- ISA date (CCYYMMDD) and time (HHMM) format warnings
- **Required segment checks** (BPR, TRN, N1, CLP for 835; BHT, NM1, CLM for 837)
- **Non-numeric amount warnings** (CLP, SVC, CAS monetary fields)
- **Duplicate claim ID warnings** (CLP for 835, CLM for 837)
- Unknown segment tag warnings
- **837 variant detection** — automatically detects Professional / Institutional / Dental from SV1/SV2/UD segments; warns when institutional claims lack HI diagnosis codes
- **835 entity checks** — warns when N1*PR (payer) or N1*PE (provider) is absent
- **837 billing provider check** — warns when NM1 billing provider entity is absent
- **CLP status code validation** — warns on non-numeric or out-of-range (1–29) CLP status codes
- **Issue categories** — every issue is tagged: `envelope`, `segment_structure`, `semantic`, `data_quality`, `content`
- **Actionable recommendations** in JSON output (`--verbose` for text)
- **Optional companion-guide / payer rule packs** via `--rules <pack.json>` for bounded trading-partner checks

```bash
# Human-readable report
python3 -m src.validate tests/fixtures/sample_835.edi

# With actionable recommendations
python3 -m src.validate tests/fixtures/sample_835.edi --verbose

# JSON report with recommendations
python3 -m src.validate tests/fixtures/sample_835.edi --json -o report.json

# Apply an optional JSON payer-rule pack
python3 -m src.validate tests/fixtures/sample_835_rich.edi \
  --json \
  --rules examples/rules/premier-835-companion.sample.json

# Write report to file
python3 -m src.validate tests/fixtures/sample_835.edi -o report.txt
```

These checks are intentionally **bounded operational checks**, not full TR3/SNIP certification. They are meant to catch common structural and data-quality problems while keeping support-boundary claims honest.

### Companion-guide / payer rules foundation

A small config-driven foundation now exists for payer-specific rules:
- JSON rule packs only (no extra dependencies)
- pack matching by `transaction_set`, `version`, `payer_name_contains`, and/or `payer_id`
- bounded rule types:
  - segment presence: `required`, `recommended`, `forbidden`
  - simple value assertions: `equals`, `starts_with`, `in`
- issues flow through the normal validator output as standard warnings/errors

This is intentionally not a full companion-guide interpreter. It is a thin framework for encoding a few high-value payer quirks honestly.

**Exit codes:** `0` = clean, `1` = structural errors found, `2` = could not parse.

---

## Installation

```bash
pip install -e .
```

Requires Python 3.9+. No third-party dependencies.

---

## Project structure

```
x12-parser/
├── src/
│   ├── __init__.py       — package entry point
│   ├── parser.py         — core parser (tokenizer, segment, loop, envelope, summary)
│   ├── cli.py             — parse CLI (json output)
│   └── validate.py       — validate CLI (structural report + recommendations)
├── tests/
│   ├── test_parser.py    — pytest unit tests
│   ├── test_validate.py  — pytest validator tests
│   └── fixtures/         — sample EDI files
│       ├── sample_835.edi              — basic 835 (2 claims)
│       ├── sample_835_rich.edi          — richer 835 (PLB, 4 LX, PER, 4 claims)
│       ├── sample_837_prof.edi          — basic 837 professional
│       ├── sample_837_prof_rich.edi      — richer 837 professional (nested HL)
│       ├── sample_837_institutional.edi   — basic 837 institutional (SV2)
│       ├── sample_multi_transaction.edi   — multiple ST/SE in one GS/GE
│       ├── sample_multi_interchange.edi  — multiple ISA/IEA interchanges
│       ├── sample_whitespace_irregular.edi — irregular CR/LF/space layout
│       └── (edge-case fixtures for validation)
├── demo/
│   ├── run.sh            — demo script (4 commands, auto-summarised)
│   └── *.txt / *.json    — pre-generated sample outputs
├── examples/
│   └── rules/
│       ├── premier-835-companion.sample.json
│       └── medicare-837i-companion.sample.json
├── DEMO.md               — demo walkthrough and sample output
├── run_tests.py          — manual test runner
├── ROADMAP.md            — gap analysis and planned improvements
├── pyproject.toml
└── README.md
```

---

## Limitations

X12 Parser is a **parser and structural checker**, not a full X12 validator:

| What it does | What it doesn't do |
|---|---|
| Tokenise on standard X12 delimiters (`*`, `:`, `~`) and tolerate irregular whitespace/newlines | Guarantee support for non-standard delimiter variants |
| Parse envelope structure (ISA/GS/ST/SE/GE/IEA) | Schema-validate segment order against X12 spec |
| Extract sender/receiver from ISA header | Validate X12 code values (e.g. "85" vs "86") |
| Detect and group loops by segment leader | Produce official X12 loop IDs (output uses heuristic keys) |
| Structural envelope validation + new semantic checks | Full TR3 schema compliance (element-level required/conditional rules) |
| Optional small JSON payer-rule packs for companion-guide quirks | Full payer companion-guide coverage or automatic interpretation of proprietary PDFs |
| Transaction summaries with financial totals + 837 hierarchy semantics | Cross-segment semantic reconciliation — billed/paid discrepancies flagged but not auto-corrected |
| Preserve all segment elements as raw strings | Fully decompose composite elements into schema-aware sub-fields |
| Non-numeric amount field warnings | Corrective auto-fixing of malformed numeric fields |

**Transaction types:** 835, 837 Professional, and 837 Institutional are the primary supported transaction types. 837 Dental currently has bounded support: it parses, is identified as dental, and participates in summary/validation flows, but dental-specific semantics are not yet modeled deeply enough to claim full support. 277, 278, 834, and others are not yet implemented.

**Large files** have not been stress-tested.

---

## Running tests

```bash
# With pytest (recommended)
PYTHONPATH=. python3 -m pytest tests/test_parser.py tests/test_validate.py -v

# Without pytest
python3 run_tests.py

# Both together
python3 run_tests.py && PYTHONPATH=. python3 -m pytest tests/test_parser.py tests/test_validate.py -v
```
