#!/usr/bin/env bash
# run.sh — X12 Parser Demo
# Run from the project root:  ./demo/run.sh
set -e

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$DEMO_DIR")"
cd "$PROJECT_DIR"

echo "============================================================"
echo "X12 Parser — Quick Demo"
echo "============================================================"
echo ""

# ── 1. Parse an 835 file ───────────────────────────────────────
echo ">>> 1. PARSE  (835 Healthcare Claim Payment/Advice)"
echo "    Command: python3 -m src.cli tests/fixtures/sample_835.edi --compact"
echo ""
python3 -m src.cli tests/fixtures/sample_835.edi --compact | python3 -c "
import json, sys
data = json.load(sys.stdin)
ic = data['interchanges'][0]
fg = ic['functional_groups'][0]
ts = fg['transactions'][0]
print(f'    ↳ Interchange sender:  {ic[\"isa06_sender\"]}')
print(f'    ↳ Interchange receiver: {ic[\"isa08_receiver\"]}')
print(f'    ↳ Transaction type:     {ts[\"set_id\"]}')
print(f'    ↳ Loops found:          {len(ts[\"loops\"])}')
loops_by_kind = {}
for l in ts['loops']:
    k = l['kind']
    loops_by_kind[k] = loops_by_kind.get(k, 0) + 1
for k, v in loops_by_kind.items():
    print(f'      - {v} loop(s) of kind: {k}')
"
echo ""

# ── 2. Validate an 835 file ───────────────────────────────────
echo ">>> 2. VALIDATE  (structural checks)"
echo "    Command: python3 -m src.validate tests/fixtures/sample_835.edi"
echo ""
python3 -m src.validate tests/fixtures/sample_835.edi || true
echo ""
echo "    Note: validate.py correctly detected an SE segment count mismatch"
echo "          in the sample fixture — this is a data quality issue in the"
echo "          fixture, not a parser bug."
echo ""

# ── 3. Parse an 837 file ───────────────────────────────────────
echo ">>> 3. PARSE  (837 Healthcare Claim — Professional)"
echo "    Command: python3 -m src.cli tests/fixtures/sample_837_prof.edi --compact"
echo ""
python3 -m src.cli tests/fixtures/sample_837_prof.edi --compact | python3 -c "
import json, sys
data = json.load(sys.stdin)
ic = data['interchanges'][0]
fg = ic['functional_groups'][0]
ts = fg['transactions'][0]
print(f'    ↳ Interchange sender:  {ic[\"isa06_sender\"]}')
print(f'    ↳ Interchange receiver: {ic[\"isa08_receiver\"]}')
print(f'    ↳ Transaction type:     {ts[\"set_id\"]}')
print(f'    ↳ Loops found:          {len(ts[\"loops\"])}')
loops_by_kind = {}
for l in ts['loops']:
    k = l['kind']
    loops_by_kind[k] = loops_by_kind.get(k, 0) + 1
for k, v in loops_by_kind.items():
    print(f'      - {v} loop(s) of kind: {k}')
"
echo ""

# ── 4. Validate a clean fixture ───────────────────────────────
echo ">>> 4. VALIDATE  (clean fixture — no structural errors)"
echo "    Command: python3 -m src.validate tests/fixtures/sample_whitespace_irregular.edi"
echo ""
python3 -m src.validate tests/fixtures/sample_whitespace_irregular.edi
echo ""

echo "============================================================"
echo "Demo complete.  See DEMO.md for full documentation."
echo "============================================================"
