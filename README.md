# X12 Parser

**Parse and validate healthcare EDI 835 and 837 transactions in Python or from the command line.**

```
python3 -m src.cli  sample.edi                  # → JSON
python3 -m src.validate sample.edi               # → structural report
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
| **835** | Healthcare Claim Payment/Advice | ✅ Parsed |
| **837 P** | Healthcare Claim — Professional (CMS-1500) | ✅ Parsed |
| **837 I** | Healthcare Claim — Institutional (UB-04) | ✅ Parsed |

### Envelope structure

ISA/IEA (interchange) → GS/GE (functional group) → ST/SE (transaction set) are fully parsed, including sender/receiver IDs and segment counts.

### Segment coverage

Common 835 and 837 segments are detected and preserved with raw element extraction. Key segments include BPR, TRN, N1, NM1, CLP, SVC, CAS, HI, CLM, SV1, SV2, and many other common segments in the included fixtures.

### Output

JSON with nested envelopes, transaction sets, and loops. Each segment carries its raw `elements` dict (`e1`, `e2`, …) for downstream use.

---

## CLI

### Parse mode

```bash
# Pretty-printed JSON (default)
python3 -m src.cli tests/fixtures/sample_835.edi

# Compact JSON (no indentation)
python3 -m src.cli tests/fixtures/sample_835.edi --compact

# Write to file
python3 -m src.cli tests/fixtures/sample_835.edi -o output.json
```

### Validate mode

Validates ISA/IEA, GS/GE, and ST/SE pairing; orphan segments; empty groups/transactions; and SE segment-count signals.

```bash
# Human-readable report
python3 -m src.validate tests/fixtures/sample_835.edi

# Write report to file
python3 -m src.validate tests/fixtures/sample_835.edi -o report.txt
```

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
│   ├── parser.py         — core parser (tokenizer, segment, loop, envelope)
│   ├── cli.py             — parse CLI (json output)
│   └── validate.py       — validate CLI (structural report)
├── tests/
│   ├── test_parser.py    — pytest unit tests
│   └── fixtures/         — sample EDI files
│       ├── sample_835.edi              — basic 835
│       ├── sample_835_rich.edi          — richer 835 (PLB, ADJ, multi-N1)
│       ├── sample_837_prof.edi          — basic 837 professional
│       ├── sample_837_prof_rich.edi      — richer 837 professional
│       ├── sample_837_institutional.edi   — basic 837 institutional
│       ├── sample_multi_transaction.edi   — multiple ST/SE in one GS/GE
│       ├── sample_multi_interchange.edi  — multiple ISA/IEA interchanges
│       └── sample_whitespace_irregular.edi — irregular CR/LF/space layout
├── demo/
│   ├── run.sh            — demo script (4 commands, auto-summarised)
│   └── *.txt / *.json    — pre-generated sample outputs
├── DEMO.md               — demo walkthrough and sample output
├── run_tests.py          — manual test runner
├── pyproject.toml
└── README.md
```

---

## Limitations

X12 Parser v0.1.0 is a **parser and structural checker**, not a full X12 validator:

| What it does | What it doesn't do |
|---|---|
| Tokenise on standard delimiters and attempt ISA-based delimiter detection | Guarantee support for every non-standard delimiter variant |
| Parse envelope structure (ISA/GS/ST/SE/GE/IEA) | Schema-validate segment order or required elements |
| Extract sender/receiver from ISA header | Validate X12 code values (e.g. "85" vs "86") |
| Detect and group loops by segment leader | Produce official X12 loop IDs (output uses heuristic keys) |
| Structural envelope validation (pairing, counts, orphans) | Cross-segment semantic reconciliation (e.g. CLP vs SVC amounts) |
| Preserve all segment elements as raw strings | Fully decompose composite elements into schema-aware sub-fields |

**Transaction types:** Only 835, 837 Professional, and 837 Institutional are supported. 277, 278, 834, and others are not yet implemented.

**Large files** have not been stress-tested.

---

## Running tests

```bash
# With pytest
PYTHONPATH=. python3 -m pytest tests/test_parser.py -v

# Without pytest
python3 run_tests.py
```
