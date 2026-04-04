# External 835 Compatibility Report

_Date: 2026-04-04_

## Purpose

This note summarizes external/public 835 compatibility testing performed after the initial top-5 parser hardening campaign. The goal was to validate the parser against public 835 examples outside the repo's original fixture set and to identify any practical gaps that only show up on external samples.

## Tested External/Public Samples

### 1. Healthcare Data Insight sample
- Local file: `external-test-files/hdi_835_all_fields.dat`
- Source family: public example linked from Healthcare Data Insight's 835 example page / public GitHub example repository
- Characteristics:
  - fully enveloped 835
  - multiple service lines
  - CAS adjustments
  - includes `TS3` and `MOA`
  - useful as a richer external-style sample

### 2. Jobisez sample
- Local file: `external-test-files/jobisez_sample_835.edi`
- Source family: public sample content published on Jobisez
- Characteristics:
  - transaction-set-only sample (starts at `ST`)
  - does **not** include a full ISA/GS envelope
  - useful for defensive behavior testing, not for full-envelope validation

## Test Matrix

The following operations were exercised against the available external samples:
- parse to JSON
- CLI summary mode
- validator JSON / verbose output
- NDJSON export
- CSV export
- SQLite bundle export

Machine-generated run summary:
- `external-test-results/external_835_test_summary.json`

## Results

### HDI sample
**Current status:** compatible in a bounded, practical sense.

What works:
- JSON parsing
- CLI summary mode
- validator execution
- NDJSON export
- CSV export
- SQLite bundle export

Important note:
- The sample includes `TS3` and `MOA` segments. The parser now tolerates these without crashing.
- These segments are currently preserved but not deeply semanticized.

### Jobisez sample
**Current status:** tolerated gracefully as a partial/bare transaction sample.

What works:
- parser does not crash
- summary mode does not crash
- exports do not crash

Bounded behavior:
- because the file does not contain a full ISA/GS/GE/IEA envelope, the parser returns empty interchanges and the validator correctly treats it as structurally incomplete for full-envelope expectations
- this is expected behavior, not a parser defect

## External-Facing Fixes Made During This Pass

### Summary-mode crash fixed
An external HDI sample surfaced a real bug in CLI summary rendering:
- discrepancy rendering assumed every discrepancy type carried the same fields
- some discrepancy types provide `clp_paid` rather than `clp_billed`

Fix applied:
- summary rendering is now type-aware and uses safer field access per discrepancy type
- result: external summary mode no longer crashes on this sample

### TS3 / MOA / MIA / TS2 handling decision
Decision:
- classify `TS3`, `MOA`, `MIA`, and `TS2` as tolerated / known-optional segments
- preserve them in parse output / loop structure
- add descriptive loop names for these segments in 835 context
- do **not** claim deep semantic support yet (no dedicated field extraction)

This keeps behavior useful without overstating support.

## What This Testing Does *Not* Prove

This pass does **not** prove:
- full compatibility with payer-specific 835 variants
- support for arbitrary large real-world remits
- full TR3/SNIP compliance
- deep semantic support for every optional 835 segment

It *does* prove that the parser is no longer limited to its original internal fixtures and can handle at least one richer external/public 835 sample without crashing, including through summary and export flows.

## Current Compatibility Posture

Best honest summary:

> The parser has been validated against internal fixtures plus a small number of public external 835 samples. Core parsing and export paths work on those samples, including a richer external file containing optional segments like TS3 and MOA. Optional segments may be tolerated without being deeply semanticized, and compatibility should still be treated as bounded rather than universal.

## Recommended Next Steps

1. Continue searching for additional public/de-identified 835 examples.
2. Add one or two more representative external-style fixtures if licensing and size are appropriate.
3. Consider a lightweight compatibility matrix in docs by segment family or sample family.
4. If more real-world 835 samples repeatedly include certain optional segments, promote those segments from tolerated to more explicitly modeled.
5. If larger public/de-identified files are found, incorporate one into the demo/benchmark surface with clear source attribution and support-boundary notes.
