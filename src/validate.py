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
from typing import Optional, List

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.parser import X12Parser
from src.payer_rules import load_rule_pack, RulePackError, CompanionRuleEngine


# ── Issue model ────────────────────────────────────────────────────────────────

@dataclass
class Issue:
    severity: str        # "error" | "warning"
    code: str            # short machine-readable code
    message: str         # human-readable description
    category: str = ""   # issue category: envelope, segment_structure, semantic, data_quality, content
    segment_tag: str = ""
    segment_position: int = 0


@dataclass
class ValidationResult:
    clean: bool = True
    issues: list[Issue] = field(default_factory=list)

    def add_error(self, code: str, message: str, tag: str = "", pos: int = 0, category: str = ""):
        cat = category or _ISSUE_CATEGORIES.get(code, "")
        self.issues.append(Issue("error", code, message, cat, tag, pos))
        self.clean = False

    def add_warning(self, code: str, message: str, tag: str = "", pos: int = 0, category: str = ""):
        cat = category or _ISSUE_CATEGORIES.get(code, "")
        self.issues.append(Issue("warning", code, message, cat, tag, pos))


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

        # Well-known inner-segment tags for orphan detection.
        # Covers 835/837 body segments; unknown tags generate a warning.
        VALID_INNER_TAGS = frozenset((
            "BPR", "TRN", "DTM", "N1", "N3", "N4", "REF", "LX", "CLP", "CAS",
            "NM1", "SVC", "ADJ", "DTP", "BHT", "HL", "PER", "SBR", "HI",
            "SV1", "SV2", "SV3", "SV4", "SV5", "DMG", "AMT", "QTY", "CTP",
            "HCP", "CUR", "NTE", "PAT", "LIN", "CR1", "CR2", "CR3", "CR4",
            "CR5", "RDM", "PLB", "RMR", "ENT", "NME", "NX1", "K1",
            "CLM", "BPR", "LQ", "F9", "N2", "G93",
        ))

        # Identify orphan ISA/IEA/GS/GE segments that appear outside interchanges
        in_interchange = False
        in_group = False
        in_transaction = False

        for i, seg in enumerate(raw_segs):
            if seg.tag == "ISA":
                # Multiple ISA/IEA interchanges are valid — only error if ISA appears
                # while we are already inside an open interchange (unclosed ISA).
                if in_interchange:
                    result.add_error("ORPHAN_ISA", f"ISA segment at position {seg.position} "
                                    "appears while a prior interchange has not been closed with IEA",
                                    seg.tag, seg.position)
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
                    se_seg = ts.get("trailer")
                    st_seg = ts.get("header")
                    # If SE is missing entirely (orphan SE caught above), skip count check
                    if not se_seg or se_seg.get("tag") != "SE":
                        continue
                    # If ST is also missing, nothing to check
                    if not st_seg or st_seg.get("tag") != "ST":
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
                    st_pos = st_seg.get("position", 0)
                    se_pos = se_seg.get("position", 0)
                    actual_count = sum(
                        1 for s in raw_segs
                        if st_pos <= s.position <= se_pos
                    )
                    st_control = st_seg.get("elements", {}).get("e2", "?")
                    if declared_count != actual_count:
                        result.add_error(
                            "SE_COUNT_MISMATCH",
                            f"Transaction {ts_idx+1} (ST*...*{st_control}): "
                            f"SE declares {declared_count} segments, "
                            f"but found {actual_count} (positions {st_pos}–{se_pos})",
                            "SE", se_pos,
                        )

        # ── 8. ISA date/time format validation ──────────────────────────────
        # ISA-09: CCYYMMDD, ISA-10: HHMM (or HHMMSS or HHMMdd - take first 4)
        for seg in raw_segs:
            if seg.tag == "ISA":
                date_raw = seg.elements[8].raw.strip() if len(seg.elements) > 8 else ""
                time_raw = seg.elements[9].raw.strip() if len(seg.elements) > 9 else ""
                if date_raw:
                    # Accept formats: CCYYMMDD, CCYYJJJ (julian), or just digits
                    # Reject clearly invalid: wrong length or non-digit
                    if len(date_raw) < 6 or not date_raw.isdigit():
                        result.add_warning(
                            "ISA_DATE_INVALID",
                            f"ISA segment at position {seg.position}: ISA-09 (date) "
                            f"has unexpected format: {date_raw!r} (expected CCYYMMDD)",
                            "ISA", seg.position,
                        )
                if time_raw:
                    # Take first 4 chars (HHMM), ignore seconds or timezone
                    time_part = time_raw[:4]
                    if not (len(time_part) == 4 and time_part.isdigit()):
                        result.add_warning(
                            "ISA_TIME_INVALID",
                            f"ISA segment at position {seg.position}: ISA-10 (time) "
                            f"has unexpected format: {time_raw!r} (expected HHMM)",
                            "ISA", seg.position,
                        )

        # ── 9. Required segments per transaction type ─────────────────────────
        # Minimal sanity check: each transaction type should have its core segments.
        REQUIRED_BY_TYPE = {
            "835": frozenset(("BPR", "TRN", "N1", "CLP")),
            "837": frozenset(("BHT", "NM1", "CLM")),
        }
        for ic in data.get("interchanges", []):
            for fg in ic.get("functional_groups", []):
                for ts_idx, ts in enumerate(fg.get("transactions", [])):
                    set_id = ts.get("set_id", "?")
                    required = REQUIRED_BY_TYPE.get(set_id)
                    if not required:
                        continue
                    # Collect all tags in this transaction
                    all_tags: set[str] = set()
                    for loop in ts.get("loops", []):
                        for seg in loop.get("segments", []):
                            all_tags.add(seg["tag"])
                    missing = required - all_tags
                    if missing:
                        for tag in missing:
                            result.add_error(
                                "REQUIRED_SEGMENT_MISSING",
                                f"Transaction {ts_idx + 1} (set {set_id}): "
                                f"required segment {tag!r} is missing. "
                                f"This may indicate a truncated or invalid file.",
                                tag, 0,
                            )

        # ── 10. Non-numeric amount fields ───────────────────────────────────
        # Check monetary elements that should always be numeric: CLP e2/e3/e4,
        # SVC e2/e3 (billed/paid amounts), CAS e2-e19 (adjustment amounts).
        AMOUNT_TAGS = frozenset(("CLP", "SVC", "CAS"))
        for seg in raw_segs:
            if seg.tag not in AMOUNT_TAGS:
                continue
            if seg.tag == "CLP":
                # e2=billed, e3=allowed, e4=paid, e5=patient responsibility
                for e_idx in (1, 2, 3, 4):  # 0-based indices
                    if e_idx >= len(seg.elements):
                        continue
                    raw = seg.elements[e_idx].raw.strip() if seg.elements[e_idx].raw else ""
                    if raw and not _is_numeric(raw):
                        elem_name = ("billed", "allowed", "paid", "patient_resp")[e_idx - 1] if e_idx <= 4 else f"e{e_idx + 1}"
                        result.add_warning(
                            "NON_NUMERIC_AMOUNT",
                            f"CLP at position {seg.position}: {elem_name} amount "
                            f"({raw!r}) is not a valid number; "
                            f"check for data corruption or incorrect delimiters",
                            "CLP", seg.position,
                        )
            elif seg.tag == "SVC":
                # e2=billed amount, e3=paid amount
                for e_idx in (1, 2):
                    if e_idx >= len(seg.elements):
                        continue
                    raw = seg.elements[e_idx].raw.strip() if seg.elements[e_idx].raw else ""
                    if raw and not _is_numeric(raw):
                        elem_name = ("billed", "paid")[e_idx - 1]
                        result.add_warning(
                            "NON_NUMERIC_AMOUNT",
                            f"SVC at position {seg.position}: {elem_name} amount "
                            f"({raw!r}) is not a valid number",
                            "SVC", seg.position,
                        )
            elif seg.tag == "CAS":
                # e2-e19: adjustment amounts
                for e_idx in range(1, min(len(seg.elements), 19)):
                    raw = seg.elements[e_idx].raw.strip() if seg.elements[e_idx].raw else ""
                    if raw and not _is_numeric(raw):
                        result.add_warning(
                            "NON_NUMERIC_AMOUNT",
                            f"CAS at position {seg.position}: adjustment amount "
                            f"({raw!r}) is not a valid number",
                            "CAS", seg.position,
                        )

        # ── 11. Duplicate claim IDs within a transaction ──────────────────────
        # 835: CLP e1 (claim ID), 837: CLM e1 (claim ID)
        for ic in data.get("interchanges", []):
            for fg in ic.get("functional_groups", []):
                for ts_idx, ts in enumerate(fg.get("transactions", [])):
                    set_id = ts.get("set_id", "?")
                    if set_id not in ("835", "837"):
                        continue
                    claim_id_tag = "CLP" if set_id == "835" else "CLM"
                    seen_ids: List[str] = []
                    duplicate_ids: List[str] = []
                    for loop in ts.get("loops", []):
                        for seg in loop.get("segments", []):
                            if seg["tag"] == claim_id_tag:
                                cid = seg["elements"].get("e1", "").strip()
                                if cid:
                                    if cid in seen_ids and cid not in duplicate_ids:
                                        duplicate_ids.append(cid)
                                    seen_ids.append(cid)
                    for dup_id in duplicate_ids:
                        result.add_warning(
                            "CLAIM_ID_DUPLICATE",
                            f"Transaction {ts_idx + 1} (set {set_id}): "
                            f"claim ID {dup_id!r} appears more than once in the "
                            f"same transaction; possible duplicate or resubmission",
                            claim_id_tag, 0,
                        )

        # ── 12. 835-specific entity checks ───────────────────────────────────
        # N1*PR (payer) and N1*PE (provider) should both be present in a valid 835
        for ic in data.get("interchanges", []):
            for fg in ic.get("functional_groups", []):
                for ts_idx, ts in enumerate(fg.get("transactions", [])):
                    if ts.get("set_id") != "835":
                        continue
                    all_tags: set[str] = set()
                    n1_qualifiers: set[str] = set()
                    for loop in ts.get("loops", []):
                        for seg in loop.get("segments", []):
                            all_tags.add(seg["tag"])
                            if seg["tag"] == "N1":
                                qualifier = seg["elements"].get("e1", "").strip()
                                if qualifier:
                                    n1_qualifiers.add(qualifier)

                    # N1*PR = payer, N1*PE = provider — both expected in 835
                    if "N1" in all_tags and "PR" not in n1_qualifiers:
                        result.add_warning(
                            "N1_PR_MISSING",
                            f"Transaction {ts_idx + 1} (835): "
                            f"N1*PR (payer) segment not found; verify payer identification is present",
                            "N1", 0,
                        )
                    if "N1" in all_tags and "PE" not in n1_qualifiers:
                        result.add_warning(
                            "N1_PE_MISSING",
                            f"Transaction {ts_idx + 1} (835): "
                            f"N1*PE (provider/payee) segment not found; verify provider identification is present",
                            "N1", 0,
                        )

        # ── 13. 837-specific checks ─────────────────────────────────────────
        # NM1*85 (billing provider) should be present in 837
        for ic in data.get("interchanges", []):
            for fg in ic.get("functional_groups", []):
                for ts_idx, ts in enumerate(fg.get("transactions", [])):
                    if ts.get("set_id") != "837":
                        continue
                    nm1_qualifiers: set[str] = set()
                    for loop in ts.get("loops", []):
                        for seg in loop.get("segments", []):
                            if seg["tag"] == "NM1":
                                qualifier = seg["elements"].get("e1", "").strip()
                                if qualifier:
                                    nm1_qualifiers.add(qualifier)

                    has_billing_provider = "85" in nm1_qualifiers or "41" in nm1_qualifiers
                    if not has_billing_provider:
                        result.add_warning(
                            "NM1_BILLING_PROVIDER_MISSING",
                            f"Transaction {ts_idx + 1} (837): "
                            f"NM1*85 (billing provider) or NM1*41 (submitter) not found; "
                            f"entity identification may be incomplete",
                            "NM1", 0,
                        )

                    # Check SV1/SV2/UD presence for variant alignment
                    all_tags = set()
                    for loop in ts.get("loops", []):
                        for seg in loop.get("segments", []):
                            all_tags.add(seg["tag"])
                    has_sv1 = "SV1" in all_tags
                    has_sv2 = "SV2" in all_tags
                    has_ud = "UD" in all_tags
                    # Warn if institutional (SV2) but no HI (diagnosis codes expected)
                    if has_sv2 and "HI" not in all_tags:
                        result.add_warning(
                            "HI_MISSING_INSTITUTIONAL",
                            f"Transaction {ts_idx + 1} (837 Institutional): "
                            f"HI (diagnosis codes) expected but not found; "
                            f"institutional claims typically require diagnosis coding",
                            "HI", 0,
                        )

        # ── 14. CLP status code sanity check ─────────────────────────────────
        # CLP status codes should be in the valid range (1-29 per X12)
        for ic in data.get("interchanges", []):
            for fg in ic.get("functional_groups", []):
                for ts_idx, ts in enumerate(fg.get("transactions", [])):
                    if ts.get("set_id") != "835":
                        continue
                    for loop in ts.get("loops", []):
                        for seg in loop.get("segments", []):
                            if seg["tag"] == "CLP":
                                status = seg["elements"].get("e3", "").strip()
                                if status and not status.isdigit():
                                    result.add_warning(
                                        "CLP_STATUS_INVALID",
                                        f"Transaction {ts_idx + 1}: CLP {seg['elements'].get('e1', '?')!r}: "
                                        f"CLP status code {status!r} is not a valid numeric code; "
                                        f"expected values 1-29 (X12 835 TR3)",
                                        "CLP", seg.get("position", 0),
                                    )
                                elif status and (int(status) < 1 or int(status) > 29):
                                    result.add_warning(
                                        "CLP_STATUS_OUT_OF_RANGE",
                                        f"Transaction {ts_idx + 1}: CLP {seg['elements'].get('e1', '?')!r}: "
                                        f"CLP status code {status!r} is outside the valid range (1-29)",
                                        "CLP", seg.get("position", 0),
                                    )

        return result


def _is_numeric(value: str) -> bool:
    """Return True if value is a valid numeric string (int or float)."""
    if not value:
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


# ── Schema-driven validation rules ──────────────────────────────────────────
# Externalized rule table: maps transaction type → segment → rule dict.
# Each rule: {"required": bool, "severity": str, "description": str, "context": callable|None}
# context is an optional function(parser, ts) → bool; if False the rule is skipped.
#
# X12 TR3 segments (approximate — not full schema, but useful structural guidance):
#
# 835 required segments (X12 005010X221A1): BPR, TRN, N1(PR), CLP
#   Recommended: N1(PE), DTM, CAS, REF, PER, LX, SVC, PLB
#
# 837 required segments (X12 005010X222A1 / X223A1):
#   Professional: BHT, NM1(41), HL (billing provider), NM1(85), CLM, SV1
#   Institutional: BHT, NM1(41), HL (billing provider), NM1(85), CLM, SV2, HI
#   Dental:       BHT, NM1(41), HL (billing provider), NM1(85), CLM, UD, HI


def _835_has_n1_role(parser: X12Parser, ts: dict) -> bool:
    """Return True if the 835 transaction has N1 with given qualifier."""
    return True  # always check


_VALIDATION_RULES: dict[str, dict[str, dict]] = {
    "835": {
        "BPR": {
            "required": True,
            "severity": "error",
            "description": "BPR (Beginning Segment for Payment/Remittance) is required",
        },
        "TRN": {
            "required": True,
            "severity": "error",
            "description": "TRN (Trace) segment is required for payment traceability",
        },
        "N1": {
            "required": True,
            "severity": "error",
            "description": "N1 (Payer Name) segment is required in 835",
        },
        "CLP": {
            "required": True,
            "severity": "error",
            "description": "CLP (Claim Payment) segment is required for each claim payment",
        },
        "PLB": {
            "required": False,
            "severity": "warning",
            "description": "PLB (Provider-Level Adjustment) segment is optional but recommended for accounting reconciliation",
        },
        "CAS": {
            "required": False,
            "severity": "warning",
            "description": "CAS (Claim Adjustment) segment is optional but common; its presence reconciles paid vs. billed",
        },
        "SVC": {
            "required": False,
            "severity": "warning",
            "description": "SVC (Service Line) segments are recommended for per-service-line paid amount detail",
        },
    },
    "837": {
        "BHT": {
            "required": True,
            "severity": "error",
            "description": "BHT (Beginning of Hierarchical Transaction) segment is required",
        },
        "NM1": {
            "required": True,
            "severity": "error",
            "description": "NM1 (Individual or Organization Name) segment is required (submitter, receiver, billing provider)",
        },
        "CLM": {
            "required": True,
            "severity": "error",
            "description": "CLM (Claim Information) segment is required for each claim",
        },
        "HI": {
            "required": False,  # Required for institutional; optional for professional
            "severity": "warning",
            "description": "HI (Health Care Information) diagnosis codes recommended for claim completeness",
        },
        "SV1": {
            "required": False,  # Professional only
            "severity": "warning",
            "description": "SV1 (Professional Service) expected for professional claims (837P)",
        },
        "SV2": {
            "required": False,  # Institutional only
            "severity": "warning",
            "description": "SV2 (Institutional Service) expected for institutional claims (837I)",
        },
        "UD": {
            "required": False,  # Dental only
            "severity": "warning",
            "description": "UD (Dental Service) expected for dental claims (837D)",
        },
    },
}

# Issue category taxonomy — groups related issues for human-readable reporting
_ISSUE_CATEGORIES: dict[str, str] = {
    # Companion / payer rules
    "PAYER_RULE_REQUIRED_SEGMENT_MISSING": "semantic",
    "PAYER_RULE_RECOMMENDED_SEGMENT_MISSING": "semantic",
    "PAYER_RULE_FORBIDDEN_SEGMENT_PRESENT": "semantic",
    "PAYER_RULE_VALUE_MISMATCH": "data_quality",
    # Envelope
    "ISA_IEA_MISMATCH":      "envelope",
    "GS_GE_MISMATCH":        "envelope",
    "ST_SE_MISMATCH":        "envelope",
    "ORPHAN_ISA":            "envelope",
    "ORPHAN_IEA":            "envelope",
    "ORPHAN_GS":             "envelope",
    "ORPHAN_GE":             "envelope",
    "ORPHAN_ST":             "envelope",
    "ORPHAN_SE":             "envelope",
    # Segment structure
    "SE_COUNT_MISMATCH":     "segment_structure",
    "SE_NO_COUNT":           "segment_structure",
    "SE_INVALID_COUNT":      "segment_structure",
    "EMPTY_TRANSACTION":    "segment_structure",
    "EMPTY_GROUP":          "segment_structure",
    # Semantic / content
    "REQUIRED_SEGMENT_MISSING":  "semantic",
    "N1_PR_MISSING":         "semantic",
    "N1_PE_MISSING":         "semantic",
    "NM1_BILLING_PROVIDER_MISSING": "semantic",
    "SVC_DATE_MISSING":      "semantic",
    # Data quality
    "ISA_DATE_INVALID":      "data_quality",
    "ISA_TIME_INVALID":      "data_quality",
    "NON_NUMERIC_AMOUNT":    "data_quality",
    "CLAIM_ID_DUPLICATE":    "data_quality",
    # Content
    "UNKNOWN_SEGMENT":       "content",
}

# Extended VALID_INNER_TAGS after the class ends


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
                cat = f" [{issue.category}]" if verbose and issue.category else ""
                lines.append(f"  [{issue.code}]{cat}{pos}  {issue.message}")
                if verbose:
                    rec = _ISSUE_RECOMMENDATIONS.get(issue.code, "")
                    if rec:
                        lines.append(f"           → {rec}")
        if warnings:
            lines.append(f"\n⚠️   {len(warnings)} WARNING(S):")
            for issue in warnings:
                pos = f" [pos {issue.segment_position}]" if issue.segment_position else ""
                cat = f" [{issue.category}]" if verbose and issue.category else ""
                lines.append(f"  [{issue.code}]{cat}{pos}  {issue.message}")
                if verbose:
                    rec = _ISSUE_RECOMMENDATIONS.get(issue.code, "")
                    if rec:
                        lines.append(f"           → {rec}")

    lines.append("\n" + "=" * 60)
    if result.clean:
        lines.append("Result: CLEAN")
    else:
        lines.append("Result: ERRORS FOUND")
    lines.append("=" * 60)
    return "\n".join(lines)


# Recommendation catalog — maps issue codes to actionable guidance
_ISSUE_RECOMMENDATIONS = {
    "PAYER_RULE_REQUIRED_SEGMENT_MISSING": "A matched companion-guide rule expected this segment. Review the payer/trading-partner implementation guide and add the missing segment if the rule pack is correct.",
    "PAYER_RULE_RECOMMENDED_SEGMENT_MISSING": "A matched companion-guide rule recommends this segment. Review the payer rule pack and companion guide to decide whether this should be informational only or supplied upstream.",
    "PAYER_RULE_FORBIDDEN_SEGMENT_PRESENT": "A matched companion-guide rule marked this segment as forbidden. Verify the trading-partner guide and remove or remap the segment if needed.",
    "PAYER_RULE_VALUE_MISMATCH": "A matched companion-guide rule expected a different element value. Compare the raw segment against the payer-specific implementation guide and update the file or the rule pack.",
    "ISA_IEA_MISMATCH": "Each interchange must have exactly one ISA and one IEA trailer. "
        "Verify the file was not truncated or corrupted during transfer.",
    "GS_GE_MISMATCH": "Each functional group must have matching GS and GE counts. "
        "Check that the GE trailer count matches the GS count.",
    "ST_SE_MISMATCH": "Each transaction set must have matching ST and SE counts. "
        "Check that the SE trailer count matches the ST count.",
    "EMPTY_TRANSACTION": "This transaction has no body segments between ST and SE. "
        "Verify the file was not truncated or the transaction was intentionally empty.",
    "EMPTY_GROUP": "This functional group has no transaction sets. The GS/GE pair should "
        "enclose one or more ST/SE pairs.",
    "ORPHAN_ISA": "An ISA segment appeared while a prior interchange was still open. "
        "All ISA segments must be closed with a matching IEA before the next ISA.",
    "ORPHAN_IEA": "An IEA trailer appeared without a preceding ISA header. "
        "Verify the file structure is correct.",
    "ORPHAN_GS": "A GS segment appeared outside of an ISA/IEA interchange. "
        "All functional groups must be inside an interchange.",
    "ORPHAN_GE": "A GE trailer appeared without a preceding GS header. "
        "Verify the functional group structure.",
    "ORPHAN_ST": "An ST segment appeared outside of a GS/GE functional group. "
        "All transaction sets must be inside a functional group.",
    "ORPHAN_SE": "An SE trailer appeared without a preceding ST header. "
        "Verify the transaction set structure.",
    "SE_COUNT_MISMATCH": "The segment count in SE e1 does not match the actual number "
        "of segments between ST and SE (inclusive). "
        "Recount segments or correct the SE trailer count.",
    "SE_NO_COUNT": "The SE trailer is missing the segment-count element (e1). "
        "Add the correct segment count to the SE.",
    "SE_INVALID_COUNT": "SE e1 is not a parseable integer. "
        "Ensure SE e1 contains a valid numeric segment count.",
    "ISA_DATE_INVALID": "ISA-09 (date) has an unexpected format. "
        "Expected CCYYMMDD; verify the ISA header was not corrupted.",
    "ISA_TIME_INVALID": "ISA-10 (time) has an unexpected format. "
        "Expected HHMM; verify the ISA header was not corrupted.",
    "REQUIRED_SEGMENT_MISSING": "A required segment for this transaction type is missing. "
        "The file may be truncated or not a valid X12 instance of this type.",
    "NON_NUMERIC_AMOUNT": "A monetary field contains a non-numeric value. "
        "This may indicate a delimiter problem (e.g., a stray asterisk in an amount field) "
        "or data corruption. Review the raw segment.",
    "CLAIM_ID_DUPLICATE": "A claim ID appears more than once in the same transaction. "
        "Verify whether this is an intentional resubmission or a data entry error.",
    "UNKNOWN_SEGMENT": "An unrecognized segment tag was encountered. "
        "This may be a typo, an unsupported optional segment, or an unsupported "
        "transaction type. Verify the transaction set version and type.",
    "N1_PR_MISSING": "N1*PR (payer name) is expected in 835 transactions. "
        "Verify the payer identification is complete for reconciliation purposes.",
    "N1_PE_MISSING": "N1*PE (provider/payee name) is expected in 835 transactions. "
        "Verify the provider identification is complete for reconciliation purposes.",
    "NM1_BILLING_PROVIDER_MISSING": "NM1*85 (billing provider) or NM1*41 (submitter) "
        "is expected in 837 transactions for proper entity identification. "
        "Verify the billing provider information is present.",
    "HI_MISSING_INSTITUTIONAL": "837 Institutional claims typically include HI (diagnosis codes) "
        "segments. Verify whether diagnosis information is missing or filed under a different segment.",
    "CLP_STATUS_INVALID": "CLP status code should be a numeric value 1-29 per X12 835 TR3. "
        "Verify the CLP segment element 3 contains a valid status code.",
    "CLP_STATUS_OUT_OF_RANGE": "CLP status code is outside the valid X12 range of 1-29. "
        "Valid codes: 1=Primary, 2=Secondary, 3=Tertiary, 4=Denied, 5=Pended, "
        "9-11=Forwarded, 12=Resubmission, 19-25=Dental forwarded, 27-29=Vision forwarded.",
}


def format_json(result: ValidationResult) -> str:
    """JSON report for machine consumption."""
    issues_out = []
    for i in result.issues:
        rec = _ISSUE_RECOMMENDATIONS.get(i.code, "No specific recommendation available.")
        issues_out.append({
            "severity": i.severity,
            "code": i.code,
            "category": i.category,
            "message": i.message,
            "segment_tag": i.segment_tag,
            "segment_position": i.segment_position,
            "recommendation": rec,
        })
    return json.dumps(
        {
            "clean": result.clean,
            "issue_count": len(result.issues),
            "error_count": sum(1 for i in result.issues if i.severity == "error"),
            "warning_count": sum(1 for i in result.issues if i.severity == "warning"),
            "issues": issues_out,
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
    parser.add_argument("--rules", type=pathlib.Path, help="Optional JSON companion-guide / payer rule pack")

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

    if args.rules:
        try:
            pack = load_rule_pack(args.rules)
        except (OSError, json.JSONDecodeError, RulePackError) as exc:
            print(f"ERROR: could not load rule pack {args.rules}: {exc}", file=sys.stderr)
            sys.exit(2)
        companion = CompanionRuleEngine(x12).apply_pack(pack)
        for issue in companion.issues:
            if issue.severity == "error":
                result.add_error(issue.code, issue.message, issue.segment_tag, issue.segment_position)
            else:
                result.add_warning(issue.code, issue.message, issue.segment_tag, issue.segment_position)

    if args.json:
        text = format_json(result)
        if args.compact:
            text = json.dumps(json.loads(text), separators=(",", ":"))
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
