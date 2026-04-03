#!/usr/bin/env python3
"""
X12 Structural Validator — CLI for envelope and structural integrity checks.

Validates ISA/IEA, GS/GE, ST/SE pairing; orphan segments; empty
transactions/groups; and SE segment-count signals.

Usage:
    python3 -m src.validate <input.edi> [--json] [-o <report.json>]

Exit codes:
    0 — clean (no structural errors found)
    1 — structural errors found
    2 — could not parse the file
"""
from __future__ import annotations

import argparse
import json
import sys
import pathlib
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.parser import X12Parser


# ── Issue model ────────────────────────────────────────────────────────────────

@dataclass
class Issue:
    severity: str        # "error" | "warning"
    code: str            # short machine-readable code
    message: str         # human-readable description
    segment_tag: str = ""
    segment_position: int = 0


@dataclass
class ValidationResult:
    clean: bool = True
    issues: list[Issue] = field(default_factory=list)

    def add_error(self, code: str, message: str, tag: str = "", pos: int = 0):
        self.issues.append(Issue("error", code, message, tag, pos))
        self.clean = False

    def add_warning(self, code: str, message: str, tag: str = "", pos: int = 0):
        self.issues.append(Issue("warning", code, message, tag, pos))


# ── Core validation ───────────────────────────────────────────────────────────

class X12Validator:
    """
    Structural validator for X12 files.

    Checks envelope pairing (ISA/IEA, GS/GE, ST/SE), orphan segments,
    empty groups/transactions, and SE segment-count signals.
    Does NOT perform schema/segment-order validation.
    """

    def __init__(self, parser: X12Parser):
        self.parser = parser

    def validate(self) -> ValidationResult:
        result = ValidationResult()
        data = self.parser.to_dict()
        raw_segs = self.parser.segments

        # ── 1. ISA/IEA global pairing ──────────────────────────────────────
        isa_count = sum(1 for s in raw_segs if s.tag == "ISA")
        iea_count = sum(1 for s in raw_segs if s.tag == "IEA")
        if isa_count != iea_count:
            result.add_error(
                "ISA_IEA_MISMATCH",
                f"ISA count ({isa_count}) != IEA count ({iea_count}); "
                f"each interchange requires exactly one ISA and one IEA",
            )

        # ── 2. GS/GE pairing per interchange ───────────────────────────────
        for ic_idx, ic in enumerate(data.get("interchanges", [])):
            ic_start_pos = ic["header"].get("position", 0)
            ic_fg_count = len(ic.get("functional_groups", []))
            gs_count = sum(
                1 for s in raw_segs
                if s.tag == "GS"
                and ic_start_pos <= s.position
                <= (ic.get("trailer", {}).get("position", 999999))
            )
            ge_count = sum(
                1 for s in raw_segs
                if s.tag == "GE"
                and ic_start_pos <= s.position
                <= (ic.get("trailer", {}).get("position", 999999))
            )
            if gs_count != ge_count:
                result.add_error(
                    "GS_GE_MISMATCH",
                    f"Interchange {ic_idx + 1}: GS count ({gs_count}) != GE count ({ge_count})",
                )

        # ── 3. ST/SE pairing per functional group ─────────────────────────
        for ic in data.get("interchanges", []):
            for fg_idx, fg in enumerate(ic.get("functional_groups", [])):
                fg_start_pos = fg["header"].get("position", 0)
                fg_end_pos = fg["trailer"].get("position", 999999)
                st_count = sum(
                    1 for s in raw_segs
                    if s.tag == "ST"
                    and fg_start_pos <= s.position <= fg_end_pos
                )
                se_count = sum(
                    1 for s in raw_segs
                    if s.tag == "SE"
                    and fg_start_pos <= s.position <= fg_end_pos
                )
                if st_count != se_count:
                    result.add_error(
                        "ST_SE_MISMATCH",
                        f"Functional group {fg_idx + 1} (IC {ic.get('header', {}).get('position', '?')}): "
                        f"ST count ({st_count}) != SE count ({se_count})",
                    )

        # ── 4. Empty transactions (ST..SE with no body segments) ────────────
        for ic in data.get("interchanges", []):
            for fg in ic.get("functional_groups", []):
                for ts_idx, ts in enumerate(fg.get("transactions", [])):
                    st_pos = ts["header"].get("position", 0)
                    se_pos = ts["trailer"].get("position", 0)
                    # Count segments strictly between ST and SE
                    body_count = sum(
                        1 for s in raw_segs
                        if st_pos < s.position < se_pos
                        and s.tag not in ("ISA", "IEA", "GS", "GE", "ST", "SE")
                    )
                    if body_count == 0:
                        result.add_error(
                            "EMPTY_TRANSACTION",
                            f"Transaction {ts_idx + 1} (ST at position {st_pos}): "
                            f"no segments between ST and SE",
                        )

        # ── 5. Empty groups (GS..GE with no ST/SE pairs) ────────────────────
        for ic in data.get("interchanges", []):
            for fg_idx, fg in enumerate(ic.get("functional_groups", [])):
                gs_pos = fg["header"].get("position", 0)
                ge_pos = fg["trailer"].get("position", 0)
                has_st = any(
                    s.tag == "ST"
                    for s in raw_segs
                    if gs_pos < s.position < ge_pos
                )
                if not has_st:
                    result.add_warning(
                        "EMPTY_GROUP",
                        f"Functional group {fg_idx + 1} (GS at position {gs_pos}): "
                        f"no ST/SE transaction sets found between GS and GE",
                    )

        # ── 6. Orphan segments (between envelope boundaries) ─────────────────
        #    Collect valid envelope positions
        envelope_positions: set[int] = set()
        for s in raw_segs:
            if s.tag in ("ISA", "IEA", "GS", "GE", "ST", "SE"):
                envelope_positions.add(s.position)

        #    ISA header occupies positions 1 through the first ISA's end
        #    (ISA is always a single raw segment at its declared position)
        isa_positions = [s.position for s in raw_segs if s.tag == "ISA"]
        if isa_positions:
            # The ISA segment itself is valid; anything between ISA and first GS is orphan
            first_gs = next((s.position for s in raw_segs if s.tag == "GS"), None)
            if first_gs:
                for s in raw_segs:
                    if s.tag not in ("ISA", "IEA", "GS", "GE", "ST", "SE", "SE") \
                       and not envelope_positions.intersection(
                           {s.position - 1, s.position, s.position + 1}):
                        pass  # handled below

        #    More precise: find segments that fall between envelope boundaries
        #    but are not valid inner segments
        VALID_INNER_TAGS = frozenset((
            "BPR", "TRN", "DTM", "N1", "N3", "N4", "REF", "LX", "CLP", "CAS",
            "NM1", "SVC", "ADJ", "DTP", "BHT", "HL", "PER", "SBR", "HI",
            "SV1", "SV2", "SV3", "SV4", "SV5", "DMG", "AMT", "QTY", "CTP",
            "HCP", "CUR", "NTE", "PAT", "LIN", "CR1", "CR2", "CR3", "CR4",
            "CR5", "RDM", "PLB", "RMR", "ENT", "NME", "NX1", "LX", "K1",
        ))

        # Identify orphan ISA/IEA/GS/GE segments that appear outside interchanges
        found_isa = False
        in_interchange = False
        in_group = False
        in_transaction = False

        for i, seg in enumerate(raw_segs):
            if seg.tag == "ISA":
                if found_isa and not in_interchange:
                    result.add_error("ORPHAN_ISA", f"Extra ISA segment at position {seg.position}; "
                                    "already outside a prior interchange", seg.tag, seg.position)
                found_isa = True
                in_interchange = True
            elif seg.tag == "IEA":
                if not in_interchange:
                    result.add_error("ORPHAN_IEA", f"Orphan IEA at position {seg.position} "
                                    "(no preceding ISA)", seg.tag, seg.position)
                in_interchange = False
            elif seg.tag == "GS":
                if not in_interchange:
                    result.add_error("ORPHAN_GS", f"Orphan GS at position {seg.position} "
                                    "(outside any ISA/IEA pair)", seg.tag, seg.position)
                in_group = True
            elif seg.tag == "GE":
                if not in_group:
                    result.add_error("ORPHAN_GE", f"Orphan GE at position {seg.position} "
                                    "(no preceding GS)", seg.tag, seg.position)
                in_group = False
            elif seg.tag == "ST":
                if not in_group:
                    result.add_error("ORPHAN_ST", f"Orphan ST at position {seg.position} "
                                    "(outside any GS/GE pair)", seg.tag, seg.position)
                in_transaction = True
            elif seg.tag == "SE":
                if not in_transaction:
                    result.add_error("ORPHAN_SE", f"Orphan SE at position {seg.position} "
                                    "(no preceding ST)", seg.tag, seg.position)
                in_transaction = False
            elif seg.tag not in VALID_INNER_TAGS:
                # Unknown segment tag — may be a typo or unsupported segment
                result.add_warning(
                    "UNKNOWN_SEGMENT",
                    f"Unknown segment tag '{seg.tag}' at position {seg.position}; "
                    "may indicate a typo or unsupported transaction type",
                    seg.tag, seg.position,
                )

        # ── 7. SE segment-count signal check ───────────────────────────────
        # SE element 1 is the segment count. Compare against actual body count.
        for ic in data.get("interchanges", []):
            for fg in ic.get("functional_groups", []):
                for ts_idx, ts in enumerate(fg.get("transactions", [])):
                    se_seg = ts.get("trailer", {})
                    if not se_seg or se_seg.get("tag") != "SE":
                        continue
                    e1 = se_seg.get("elements", {}).get("e1")
                    if e1 is None:
                        result.add_warning(
                            "SE_NO_COUNT",
                            f"Transaction {ts_idx+1}: SE segment has no segment-count element (e1)",
                        )
                        continue
                    try:
                        declared_count = int(e1)
                    except ValueError:
                        result.add_warning(
                            "SE_INVALID_COUNT",
                            f"Transaction {ts_idx+1}: SE e1 is not a valid integer: {e1!r}",
                        )
                        continue
                    # Actual: ST (1) + body segments + SE (1)
                    st_pos = ts["header"].get("position", 0)
                    se_pos = se_seg.get("position", 0)
                    actual_count = sum(
                        1 for s in raw_segs
                        if st_pos <= s.position <= se_pos
                    )
                    if declared_count != actual_count:
                        result.add_error(
                            "SE_COUNT_MISMATCH",
                            f"Transaction {ts_idx+1}: SE declares {declared_count} segments, "
                            f"but found {actual_count} (positions {st_pos}–{se_pos})",
                            "SE", se_pos,
                        )

        return result


# ── Report formatters ─────────────────────────────────────────────────────────

def format_report(result: ValidationResult, verbose: bool = False) -> str:
    """Human-readable text report."""
    lines = []
    lines.append("=" * 60)
    lines.append("X12 STRUCTURAL VALIDATION REPORT")
    lines.append("=" * 60)

    if result.clean:
        lines.append("\n✅  No structural errors found.")
    else:
        errors = [i for i in result.issues if i.severity == "error"]
        warnings = [i for i in result.issues if i.severity == "warning"]
        if errors:
            lines.append(f"\n❌  {len(errors)} ERROR(S):")
            for issue in errors:
                pos = f" [pos {issue.segment_position}]" if issue.segment_position else ""
                lines.append(f"  [{issue.code}]{pos}  {issue.message}")
        if warnings:
            lines.append(f"\n⚠️   {len(warnings)} WARNING(S):")
            for issue in warnings:
                pos = f" [pos {issue.segment_position}]" if issue.segment_position else ""
                lines.append(f"  [{issue.code}]{pos}  {issue.message}")

    lines.append("\n" + "=" * 60)
    if result.clean:
        lines.append("Result: CLEAN")
    else:
        lines.append("Result: ERRORS FOUND")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_json(result: ValidationResult) -> str:
    """JSON report for machine consumption."""
    return json.dumps(
        {
            "clean": result.clean,
            "issue_count": len(result.issues),
            "error_count": sum(1 for i in result.issues if i.severity == "error"),
            "warning_count": sum(1 for i in result.issues if i.severity == "warning"),
            "issues": [
                {
                    "severity": i.severity,
                    "code": i.code,
                    "message": i.message,
                    "segment_tag": i.segment_tag,
                    "segment_position": i.segment_position,
                }
                for i in result.issues
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="X12 Structural Validator — check envelope pairing and structural integrity",
    )
    parser.add_argument("file", type=pathlib.Path, help="Input X12 EDI file")
    parser.add_argument("-o", "--output", type=pathlib.Path, help="Write report to file")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--compact", action="store_true", help="Compact JSON (no indent)")
    parser.add_argument("--verbose", action="store_true", help="Show warnings in text report")

    args = parser.parse_args()

    if not args.file.exists():
        print(f"ERROR: file not found: {args.file}", file=sys.stderr)
        sys.exit(2)

    try:
        x12 = X12Parser.from_file(args.file)
        # Force parse to run (to catch early syntax errors)
        x12._parse()
    except Exception as exc:
        print(f"ERROR: could not parse {args.file}: {exc}", file=sys.stderr)
        sys.exit(2)

    validator = X12Validator(x12)
    result = validator.validate()

    if args.json:
        indent = None if args.compact else 2
        text = json.dumps(
            {
                "clean": result.clean,
                "issue_count": len(result.issues),
                "error_count": sum(1 for i in result.issues if i.severity == "error"),
                "warning_count": sum(1 for i in result.issues if i.severity == "warning"),
                "issues": [
                    {
                        "severity": i.severity,
                        "code": i.code,
                        "message": i.message,
                        "segment_tag": i.segment_tag,
                        "segment_position": i.segment_position,
                    }
                    for i in result.issues
                ],
            },
            indent=indent,
            ensure_ascii=False,
        )
    else:
        text = format_report(result, verbose=args.verbose)

    if args.output:
        args.output.write_text(text)
        status = "CLEAN" if result.clean else "ERRORS"
        print(f"[{status}] Report written: {args.output}")
    else:
        print(text)

    sys.exit(0 if result.clean else 1)


if __name__ == "__main__":
    main()
