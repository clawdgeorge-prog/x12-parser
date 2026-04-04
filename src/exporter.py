"""
X12 Export Module — CSV, NDJSON, and SQLite-ready normalized output.

Supports structured extraction from parsed 835 and 837 transactions:
  --format csv      → flat CSV files per record type (claims, svc lines, adjustments, entities)
  --format ndjson   → newline-delimited JSON (one object per record)
  --format sqlite   → normalized CSV files + schema.sql ready for SQLite import

Usage:
    python3 -m src.cli <file> --format csv -o output_dir/
    python3 -m src.cli <file> --format ndjson
    python3 -m src.cli <file> --format sqlite -o output_dir/
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys
from typing import Any, Iterator, List, Optional, TextIO


# ── Normalized record builders ─────────────────────────────────────────────────

def _safe(v: Any) -> str:
    """Coerce a value to a safe CSV string."""
    if v is None:
        return ""
    return str(v)


def _fmt_money(v: Any) -> str:
    """Format a numeric value as a plain decimal string."""
    if v is None:
        return ""
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return ""


def _build_835_claim_records(data: dict) -> Iterator[dict]:
    """Yield one claim record dict per 835 CLP loop."""
    for ic in data.get("interchanges", []):
        ic_ctrl = _safe(ic.get("header", {}).get("elements", {}).get("e13", ""))
        isa_sender = _safe(ic.get("isa06_sender", ""))
        isa_receiver = _safe(ic.get("isa08_receiver", ""))
        for fg in ic.get("functional_groups", []):
            gs_ctrl = _safe(fg.get("header", {}).get("elements", {}).get("e6", ""))
            gs_version = _safe(fg.get("header", {}).get("elements", {}).get("e8", ""))
            for ts in fg.get("transactions", []):
                if ts.get("set_id") != "835":
                    continue
                summary = ts.get("summary", {})
                st_ctrl = _safe(ts.get("header", {}).get("elements", {}).get("e2", ""))
                payer = _safe(summary.get("payer_name", ""))
                provider = _safe(summary.get("provider_name", ""))
                payment_amount = _fmt_money(summary.get("payment_amount"))
                check_trace = _safe(summary.get("check_trace", ""))
                bpr_method = _safe(summary.get("bpr_payment_method", ""))
                for claim in summary.get("claims", []):
                    yield {
                        "interchange_ctrl": ic_ctrl,
                        "isa_sender": isa_sender,
                        "isa_receiver": isa_receiver,
                        "gs_ctrl": gs_ctrl,
                        "gs_version": gs_version,
                        "st_ctrl": st_ctrl,
                        "transaction_type": "835",
                        "claim_id": _safe(claim.get("claim_id", "")),
                        "status_code": _safe(claim.get("status_code", "")),
                        "status_label": _safe(claim.get("status_label", "")),
                        "status_category": _safe(claim.get("status_category", "")),
                        "patient_name": _safe(claim.get("patient_name", "")),
                        "clp_billed": _fmt_money(claim.get("clp_billed")),
                        "clp_allowed": _fmt_money(claim.get("clp_allowed")),
                        "clp_paid": _fmt_money(claim.get("clp_paid")),
                        "clp_adjustment": _fmt_money(claim.get("clp_adjustment")),
                        "svc_billed": _fmt_money(claim.get("svc_billed")),
                        "svc_paid": _fmt_money(claim.get("svc_paid")),
                        "service_line_count": _safe(claim.get("service_line_count", "")),
                        "has_billed_discrepancy": str(claim.get("has_billed_discrepancy", False)),
                        "has_paid_discrepancy": str(claim.get("has_paid_discrepancy", False)),
                        "adjustment_group_codes": _safe(
                            ",".join(c.get("code", "") for c in claim.get("adjustment_group_codes", []))
                        ),
                        "payer_name": payer,
                        "provider_name": provider,
                        "payment_amount": payment_amount,
                        "check_trace": check_trace,
                        "bpr_payment_method": bpr_method,
                    }


def _build_837_claim_records(data: dict) -> Iterator[dict]:
    """Yield one claim record dict per 837 CLM loop."""
    for ic in data.get("interchanges", []):
        ic_ctrl = _safe(ic.get("header", {}).get("elements", {}).get("e13", ""))
        isa_sender = _safe(ic.get("isa06_sender", ""))
        isa_receiver = _safe(ic.get("isa08_receiver", ""))
        for fg in ic.get("functional_groups", []):
            gs_ctrl = _safe(fg.get("header", {}).get("elements", {}).get("e6", ""))
            gs_version = _safe(fg.get("header", {}).get("elements", {}).get("e8", ""))
            for ts in fg.get("transactions", []):
                if ts.get("set_id") != "837":
                    continue
                summary = ts.get("summary", {})
                st_ctrl = _safe(ts.get("header", {}).get("elements", {}).get("e2", ""))
                variant = _safe(summary.get("variant", ""))
                variant_indicator = _safe(summary.get("variant_indicator", ""))
                billing_provider = _safe(summary.get("billing_provider", ""))
                payer = _safe(summary.get("payer_name", ""))
                submitter = _safe(summary.get("submitter_name", ""))
                subscriber = _safe(summary.get("subscriber_name", ""))
                patient = _safe(summary.get("patient_name", ""))
                bht_id = _safe(summary.get("bht_id", ""))
                bht_date = _safe(summary.get("bht_date", ""))
                for claim in summary.get("claims", []):
                    yield {
                        "interchange_ctrl": ic_ctrl,
                        "isa_sender": isa_sender,
                        "isa_receiver": isa_receiver,
                        "gs_ctrl": gs_ctrl,
                        "gs_version": gs_version,
                        "st_ctrl": st_ctrl,
                        "transaction_type": "837",
                        "claim_id": _safe(claim.get("claim_id", "")),
                        "variant": variant,
                        "variant_indicator": variant_indicator,
                        "clp_billed": _fmt_money(claim.get("clp_billed")),
                        "total_svc_billed": _fmt_money(claim.get("total_svc_billed")),
                        "total_svc_paid": _fmt_money(claim.get("total_svc_paid")),
                        "service_line_count": _safe(claim.get("service_line_count", "")),
                        "has_discrepancy": str(claim.get("has_discrepancy", False)),
                        "discrepancy_reason": _safe(claim.get("discrepancy_reason", "")),
                        "billing_provider": billing_provider,
                        "payer_name": payer,
                        "submitter_name": submitter,
                        "subscriber_name": subscriber,
                        "patient_name": patient,
                        "bht_id": bht_id,
                        "bht_date": bht_date,
                    }


def _walk_loops_for_svc(loops: list, set_id: str, ic_ctrl: str, isa_sender: str, gs_version: str, st_ctrl: str) -> Iterator[dict]:
    """
    Walk loop sequence to extract service-line records.

    For 835: SVC segments can appear inside DTM loops (DTM*001*SVC). We scan all
    loops for SVC, SV1, SV2 segments. The current_claim_id is tracked from the
    most recent preceding CLP loop (835) or CLM loop (837).

    The LX loop (leader=LX, kind=service) carries the line item sequence number
    (LX*e1) but not the SVC data itself — SVC is in the DTM sub-loop that follows.

    For 837: SV1 (professional) or SV2 (institutional) segments appear directly
    inside the claim loop alongside CLM.
    """
    current_claim_id = ""
    current_lx_seq = 0
    line_num = 0

    for loop in loops:
        leader = loop.get("leader_tag", "")
        kind = loop.get("kind", "")
        loop_id = loop.get("id", "")

        # Track current claim context from CLP (835) or CLM (837)
        if leader in ("CLP", "CLM") and kind == "claim":
            for seg in loop.get("segments", []):
                if seg.get("tag") in ("CLP", "CLM"):
                    elements = seg.get("elements", {})
                    current_claim_id = _safe(elements.get("e1", ""))
                    break
            line_num = 0  # reset per claim

        # Track LX sequence number
        if leader == "LX" and kind == "service":
            for seg in loop.get("segments", []):
                if seg.get("tag") == "LX":
                    elements = seg.get("elements", {})
                    try:
                        current_lx_seq = int(_safe(elements.get("e1", "0")))
                    except ValueError:
                        current_lx_seq += 1
                    break

        # Extract SVC from any loop (835: often inside DTM sub-loop)
        for seg in loop.get("segments", []):
            tag = seg.get("tag", "")
            if tag not in ("SVC", "SV1", "SV2", "SV3", "SV4", "SV5", "SV6", "SV7"):
                continue
            elements = seg.get("elements", {})
            e1_raw = _safe(elements.get("e1", ""))
            # Handle composite: "HC:99213" → procedure code = 99213
            if ":" in e1_raw:
                proc_code = e1_raw.split(":")[-1]
            else:
                proc_code = e1_raw
            line_num += 1
            yield {
                "interchange_ctrl": ic_ctrl,
                "isa_sender": isa_sender,
                "gs_version": gs_version,
                "st_ctrl": st_ctrl,
                "transaction_type": set_id,
                "claim_id": current_claim_id,
                "line_number": str(line_num),
                "procedure_code": proc_code,
                "billed": _fmt_money(elements.get("e2", "")),
                "paid": _fmt_money(elements.get("e3", "")),
            }


def _build_service_line_records(data: dict) -> Iterator[dict]:
    """Yield service-line records from both 835 and 837 by walking loop sequences."""
    for ic in data.get("interchanges", []):
        ic_ctrl = _safe(ic.get("header", {}).get("elements", {}).get("e13", ""))
        isa_sender = _safe(ic.get("isa06_sender", ""))
        for fg in ic.get("functional_groups", []):
            gs_version = _safe(fg.get("header", {}).get("elements", {}).get("e8", ""))
            for ts in fg.get("transactions", []):
                set_id = ts.get("set_id", "")
                st_ctrl = _safe(ts.get("header", {}).get("elements", {}).get("e2", ""))
                loops = ts.get("loops", [])
                yield from _walk_loops_for_svc(loops, set_id, ic_ctrl, isa_sender, gs_version, st_ctrl)


def _build_entity_records(data: dict) -> Iterator[dict]:
    """
    Yield entity records from both 835 and 837.

    Handles two loop patterns:
      1. NM1-led loops (leader_tag=NM1): billing provider, subscriber, patient, etc.
         - NM1*e1 = entity identifier code (e.g. "85", "QC", "IL")
         - NM1*e2 = entity type qualifier
         - NM1*e3/e4/e5 = name fields
         - NM1*e8 = identification code
      2. N1-led loops (leader_tag=N1): payer and payee entities
         - N1*e1 = entity identifier code (e.g. "PR", "PE")
         - N1*e2 = name
         - N1*e3/e4 = address (contained in N3/N4 sub-segments, not N1 itself)
    """
    entity_kind_map = {
        "PR": "payer",
        "PE": "payee",
        "IL": "insured",
        "QC": "patient",
        "85": "billing_provider",
        "41": "submitter",
        "77": "service_location",
        "DK": "unknown",
    }
    loop_kind_map = {
        "entity": "entity",
        "claim": "claim",
        "service": "service",
        "header": "header",
        "amount": "amount",
        "other": "other",
    }

    def _emit(loop, elements, entity_code, ic_ctrl, isa_sender, isa_receiver,
               gs_version, st_ctrl, set_id):
        e1 = _safe(elements.get("e1", ""))
        e2 = _safe(elements.get("e2", ""))
        e3 = _safe(elements.get("e3", ""))
        e4 = _safe(elements.get("e4", ""))
        e5 = _safe(elements.get("e5", ""))
        e8 = _safe(elements.get("e8", ""))
        entity_type = entity_kind_map.get(entity_code, entity_code.lower())
        yield {
            "interchange_ctrl": ic_ctrl,
            "isa_sender": isa_sender,
            "isa_receiver": isa_receiver,
            "gs_version": gs_version,
            "st_ctrl": st_ctrl,
            "transaction_type": set_id,
            "loop_id": _safe(loop.get("id", "")),
            "loop_kind": loop_kind_map.get(loop.get("kind", ""), loop.get("kind", "")),
            "entity_code": entity_code,
            "entity_type": entity_type,
            "nm1_e1_entity_id": e1,
            "nm1_e2_type_qualifier": e2,
            "name_last_org": e3,
            "name_first": e4,
            "name_middle": e5,
            "identification_code": e8,
        }

    for ic in data.get("interchanges", []):
        ic_ctrl = _safe(ic.get("header", {}).get("elements", {}).get("e13", ""))
        isa_sender = _safe(ic.get("isa06_sender", ""))
        isa_receiver = _safe(ic.get("isa08_receiver", ""))
        for fg in ic.get("functional_groups", []):
            gs_version = _safe(fg.get("header", {}).get("elements", {}).get("e8", ""))
            for ts in fg.get("transactions", []):
                set_id = ts.get("set_id", "")
                st_ctrl = _safe(ts.get("header", {}).get("elements", {}).get("e2", ""))
                for loop in ts.get("loops", []):
                    leader_tag = loop.get("leader_tag", "")
                    leader_code = loop.get("leader_code", "")

                    # NM1-led loops: extract from NM1 segment
                    if leader_tag == "NM1":
                        for seg in loop.get("segments", []):
                            if seg.get("tag") == "NM1":
                                yield from _emit(
                                    loop, seg.get("elements", {}), leader_code,
                                    ic_ctrl, isa_sender, isa_receiver,
                                    gs_version, st_ctrl, set_id,
                                )
                                break

                    # N1-led loops: payer (PR) and payee (PE) entities
                    # N1 is both the loop leader and the entity segment
                    elif leader_tag == "N1" and leader_code in ("PR", "PE"):
                        for seg in loop.get("segments", []):
                            if seg.get("tag") == "N1":
                                yield from _emit(
                                    loop, seg.get("elements", {}), leader_code,
                                    ic_ctrl, isa_sender, isa_receiver,
                                    gs_version, st_ctrl, set_id,
                                )
                                break


# ── CSV writer helpers ─────────────────────────────────────────────────────────

CSV_CLAIMS_835_FIELDS = [
    "interchange_ctrl", "isa_sender", "isa_receiver", "gs_ctrl", "gs_version",
    "st_ctrl", "transaction_type", "claim_id", "status_code", "status_label",
    "status_category", "patient_name", "clp_billed", "clp_allowed", "clp_paid",
    "clp_adjustment", "svc_billed", "svc_paid", "service_line_count",
    "has_billed_discrepancy", "has_paid_discrepancy", "adjustment_group_codes",
    "payer_name", "provider_name", "payment_amount", "check_trace", "bpr_payment_method",
]

CSV_CLAIMS_837_FIELDS = [
    "interchange_ctrl", "isa_sender", "isa_receiver", "gs_ctrl", "gs_version",
    "st_ctrl", "transaction_type", "claim_id", "variant", "variant_indicator",
    "clp_billed", "total_svc_billed", "total_svc_paid", "service_line_count",
    "has_discrepancy", "discrepancy_reason", "billing_provider", "payer_name",
    "submitter_name", "subscriber_name", "patient_name", "bht_id", "bht_date",
]

CSV_SVC_LINE_FIELDS = [
    "interchange_ctrl", "isa_sender", "gs_version", "st_ctrl",
    "transaction_type", "claim_id", "line_number", "procedure_code",
    "billed", "paid",
]

CSV_ENTITY_FIELDS = [
    "interchange_ctrl", "isa_sender", "isa_receiver", "gs_version", "st_ctrl",
    "transaction_type", "loop_id", "loop_kind", "entity_code", "entity_type",
    "nm1_e1_entity_id", "nm1_e2_type_qualifier", "name_last_org",
    "name_first", "name_middle", "identification_code",
]


def write_csv(data: dict, output_dir: pathlib.Path) -> dict:
    """
    Write normalized CSV files to output_dir.
    
    Produces:
      claims_835.csv
      claims_837.csv
      service_lines.csv
      entities.csv

    Returns a dict of filename → record count.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    counts = {}

    # 835 claims
    claims_835_path = output_dir / "claims_835.csv"
    with open(claims_835_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_CLAIMS_835_FIELDS)
        w.writeheader()
        for rec in _build_835_claim_records(data):
            w.writerow(rec)
    counts["claims_835.csv"] = sum(1 for _ in _build_835_claim_records(data))

    # 837 claims
    claims_837_path = output_dir / "claims_837.csv"
    with open(claims_837_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_CLAIMS_837_FIELDS)
        w.writeheader()
        for rec in _build_837_claim_records(data):
            w.writerow(rec)
    counts["claims_837.csv"] = sum(1 for _ in _build_837_claim_records(data))

    # Service lines
    svc_path = output_dir / "service_lines.csv"
    with open(svc_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_SVC_LINE_FIELDS)
        w.writeheader()
        for rec in _build_service_line_records(data):
            w.writerow(rec)
    counts["service_lines.csv"] = sum(1 for _ in _build_service_line_records(data))

    # Entities
    entity_path = output_dir / "entities.csv"
    with open(entity_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_ENTITY_FIELDS)
        w.writeheader()
        for rec in _build_entity_records(data):
            w.writerow(rec)
    counts["entities.csv"] = sum(1 for _ in _build_entity_records(data))

    return counts


# ── NDJSON output ─────────────────────────────────────────────────────────────

def emit_ndjson(data: dict, file: Optional[TextIO] = None) -> int:
    """
    Emit newline-delimited JSON for each record in the parsed X12 tree.

    Emits one JSON object per line for:
      - each interchange
      - each functional group within an interchange
      - each transaction set within a functional group
      - each loop within a transaction set
      - each segment within a loop (optional via include_segments flag)

    Records are ordered top-down (interchange → group → transaction → loop).

    Returns the total number of NDJSON records written.
    """
    count = 0
    out = file or sys.stdout

    for ic in data.get("interchanges", []):
        # Interchange-level record
        ic_rec = {
            "_record_type": "interchange",
            "interchange_ctrl": _safe(ic.get("header", {}).get("elements", {}).get("e13", "")),
            "isa_sender": _safe(ic.get("isa06_sender", "")),
            "isa_receiver": _safe(ic.get("isa08_receiver", "")),
            "isa_date": _safe(ic.get("header", {}).get("elements", {}).get("e9", "")),
            "isa_time": _safe(ic.get("header", {}).get("elements", {}).get("e10", "")),
            "gs_count": len(ic.get("functional_groups", [])),
        }
        out.write(json.dumps(ic_rec, ensure_ascii=False) + "\n")
        count += 1

        for fg in ic.get("functional_groups", []):
            gs = fg.get("header", {})
            # Functional group record
            fg_rec = {
                "_record_type": "functional_group",
                "interchange_ctrl": _safe(ic.get("header", {}).get("elements", {}).get("e13", "")),
                "gs_ctrl": _safe(gs.get("elements", {}).get("e6", "")),
                "gs_version": _safe(gs.get("elements", {}).get("e8", "")),
                "gs_type": _safe(gs.get("elements", {}).get("e1", "")),
                "gs_sender": _safe(gs.get("elements", {}).get("e2", "")),
                "gs_receiver": _safe(gs.get("elements", {}).get("e3", "")),
                "gs_date": _safe(gs.get("elements", {}).get("e4", "")),
                "transaction_count": len(fg.get("transactions", [])),
            }
            out.write(json.dumps(fg_rec, ensure_ascii=False) + "\n")
            count += 1

            for ts in fg.get("transactions", []):
                st = ts.get("header", {})
                set_id = _safe(ts.get("set_id", "?"))
                # Transaction set record
                ts_rec = {
                    "_record_type": "transaction_set",
                    "interchange_ctrl": _safe(ic.get("header", {}).get("elements", {}).get("e13", "")),
                    "gs_ctrl": _safe(gs.get("elements", {}).get("e6", "")),
                    "st_ctrl": _safe(st.get("elements", {}).get("e2", "")),
                    "set_id": set_id,
                    "summary": ts.get("summary", {}),
                    "loop_count": len(ts.get("loops", [])),
                }
                out.write(json.dumps(ts_rec, ensure_ascii=False) + "\n")
                count += 1

                for loop in ts.get("loops", []):
                    # Loop record — compact representation
                    seg_tags = [s.get("tag", "") for s in loop.get("segments", [])]
                    first_nm1 = None
                    for seg in loop.get("segments", []):
                        if seg.get("tag") == "NM1":
                            elements = seg.get("elements", {})
                            first_nm1 = {
                                "entity_code": _safe(loop.get("leader_code", "")),
                                "name_last_org": _safe(elements.get("e3", "")),
                                "name_first": _safe(elements.get("e4", "")),
                                "id_code": _safe(elements.get("e8", "")),
                            }
                            break
                    loop_rec = {
                        "_record_type": "loop",
                        "interchange_ctrl": _safe(ic.get("header", {}).get("elements", {}).get("e13", "")),
                        "st_ctrl": _safe(st.get("elements", {}).get("e2", "")),
                        "set_id": set_id,
                        "loop_id": _safe(loop.get("id", "")),
                        "loop_kind": _safe(loop.get("kind", "")),
                        "leader_tag": _safe(loop.get("leader_tag", "")),
                        "leader_code": _safe(loop.get("leader_code", "")),
                        "description": _safe(loop.get("description", "")),
                        "segment_count": len(loop.get("segments", [])),
                        "segment_tags": seg_tags,
                        "nm1": first_nm1,
                    }
                    out.write(json.dumps(loop_rec, ensure_ascii=False) + "\n")
                    count += 1

    return count


# ── SQLite schema + CSV bundle ───────────────────────────────────────────────

SQLITE_SCHEMA = """\
-- X12 Parser — SQLite Import Schema
-- Version: 0.2.1
-- Usage:
--   sqlite3 output.db < schema.sql
--   sqlite3 output.db -cmd ".import claims_835.csv claims_835" .quit
--   (repeat .import for each CSV file)
--
-- Or use the --format sqlite option of the CLI which generates all files at once.

-- interchanges (one row per ISA envelope)
CREATE TABLE IF NOT EXISTS interchanges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interchange_ctrl TEXT,
    isa_sender TEXT,
    isa_receiver TEXT,
    isa_date TEXT,
    isa_time TEXT,
    gs_count INTEGER
);

-- functional_groups (one row per GS envelope)
CREATE TABLE IF NOT EXISTS functional_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interchange_ctrl TEXT,
    gs_ctrl TEXT,
    gs_type TEXT,
    gs_sender TEXT,
    gs_receiver TEXT,
    gs_date TEXT,
    gs_version TEXT,
    transaction_count INTEGER
);

-- transactions (one row per ST/SE transaction set)
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interchange_ctrl TEXT,
    gs_ctrl TEXT,
    st_ctrl TEXT,
    set_id TEXT,
    payment_amount REAL,
    total_billed_amount REAL,
    total_paid_amount REAL,
    claim_count INTEGER,
    loop_count INTEGER,
    -- summary JSON stored as text for flexibility
    summary_json TEXT
);

-- claims_835 (one row per CLP loop from 835 transactions)
CREATE TABLE IF NOT EXISTS claims_835 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interchange_ctrl TEXT,
    isa_sender TEXT,
    isa_receiver TEXT,
    gs_ctrl TEXT,
    gs_version TEXT,
    st_ctrl TEXT,
    transaction_type TEXT,
    claim_id TEXT,
    status_code TEXT,
    status_label TEXT,
    status_category TEXT,
    patient_name TEXT,
    clp_billed REAL,
    clp_allowed REAL,
    clp_paid REAL,
    clp_adjustment REAL,
    svc_billed REAL,
    svc_paid REAL,
    service_line_count INTEGER,
    has_billed_discrepancy INTEGER,
    has_paid_discrepancy INTEGER,
    adjustment_group_codes TEXT,
    payer_name TEXT,
    provider_name TEXT,
    payment_amount REAL,
    check_trace TEXT,
    bpr_payment_method TEXT
);

-- claims_837 (one row per CLM loop from 837 transactions)
CREATE TABLE IF NOT EXISTS claims_837 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interchange_ctrl TEXT,
    isa_sender TEXT,
    isa_receiver TEXT,
    gs_ctrl TEXT,
    gs_version TEXT,
    st_ctrl TEXT,
    transaction_type TEXT,
    claim_id TEXT,
    variant TEXT,
    variant_indicator TEXT,
    clp_billed REAL,
    total_svc_billed REAL,
    total_svc_paid REAL,
    service_line_count INTEGER,
    has_discrepancy INTEGER,
    discrepancy_reason TEXT,
    billing_provider TEXT,
    payer_name TEXT,
    submitter_name TEXT,
    subscriber_name TEXT,
    patient_name TEXT,
    bht_id TEXT,
    bht_date TEXT
);

-- service_lines (one row per service line from both 835 and 837)
CREATE TABLE IF NOT EXISTS service_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interchange_ctrl TEXT,
    isa_sender TEXT,
    gs_version TEXT,
    st_ctrl TEXT,
    transaction_type TEXT,
    claim_id TEXT,
    line_number INTEGER,
    procedure_code TEXT,
    billed REAL,
    paid REAL
);

-- entities (one row per NM1 loop from both 835 and 837)
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interchange_ctrl TEXT,
    isa_sender TEXT,
    isa_receiver TEXT,
    gs_version TEXT,
    st_ctrl TEXT,
    transaction_type TEXT,
    loop_id TEXT,
    loop_kind TEXT,
    entity_code TEXT,
    entity_type TEXT,
    nm1_e1_entity_id TEXT,
    nm1_e2_type_qualifier TEXT,
    name_last_org TEXT,
    name_first TEXT,
    name_middle TEXT,
    identification_code TEXT
);
"""


def write_sqlite_bundle(data: dict, output_dir: pathlib.Path) -> dict:
    """
    Write a SQLite-ready normalized export bundle to output_dir.

    Produces:
      schema.sql       — CREATE TABLE statements
      interchanges.csv — one row per ISA envelope
      functional_groups.csv — one row per GS envelope
      transactions.csv — one row per ST/SE transaction set
      claims_835.csv   — one row per CLP from 835
      claims_837.csv   — one row per CLM from 837
      service_lines.csv — one row per service line
      entities.csv     — one row per NM1 loop

    Also writes a IMPORT_GUIDE.txt with quick-reference SQLite commands.

    Returns a dict of filename → record count.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write schema
    (output_dir / "schema.sql").write_text(SQLITE_SCHEMA)

    counts = {}

    # Interchanges
    ic_fields = ["interchange_ctrl", "isa_sender", "isa_receiver", "isa_date", "isa_time", "gs_count"]
    ic_path = output_dir / "interchanges.csv"
    with open(ic_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ic_fields)
        w.writeheader()
        for ic in data.get("interchanges", []):
            ic_header = ic.get("header", {})
            elements = ic_header.get("elements", {})
            isa_date = elements.get("e9", "")
            isa_time = elements.get("e10", "")
            # Fix time format (HHMM → HH:MM:SS if 4 digits)
            if len(str(isa_time)) >= 4:
                try:
                    hh, mm = isa_time[:2], isa_time[2:4]
                    isa_time = f"{hh}:{mm}:00"
                except (ValueError, TypeError):
                    pass
            row = {
                "interchange_ctrl": _safe(elements.get("e13", "")),
                "isa_sender": _safe(ic.get("isa06_sender", "")),
                "isa_receiver": _safe(ic.get("isa08_receiver", "")),
                "isa_date": _fmt_isa_date(isa_date),
                "isa_time": _safe(isa_time),
                "gs_count": str(len(ic.get("functional_groups", []))),
            }
            w.writerow(row)
    counts["interchanges.csv"] = sum(1 for _ in data.get("interchanges", []))

    # Functional groups
    fg_fields = ["interchange_ctrl", "gs_ctrl", "gs_type", "gs_sender", "gs_receiver", "gs_date", "gs_version", "transaction_count"]
    fg_path = output_dir / "functional_groups.csv"
    fg_count = 0
    with open(fg_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fg_fields)
        w.writeheader()
        for ic in data.get("interchanges", []):
            ic_ctrl = _safe(ic.get("header", {}).get("elements", {}).get("e13", ""))
            for fg in ic.get("functional_groups", []):
                gs = fg.get("header", {})
                gs_elements = gs.get("elements", {})
                row = {
                    "interchange_ctrl": ic_ctrl,
                    "gs_ctrl": _safe(gs_elements.get("e6", "")),
                    "gs_type": _safe(gs_elements.get("e1", "")),
                    "gs_sender": _safe(gs_elements.get("e2", "")),
                    "gs_receiver": _safe(gs_elements.get("e3", "")),
                    "gs_date": _fmt_gs_date(_safe(gs_elements.get("e4", ""))),
                    "gs_version": _safe(gs_elements.get("e8", "")),
                    "transaction_count": str(len(fg.get("transactions", []))),
                }
                w.writerow(row)
                fg_count += 1
    counts["functional_groups.csv"] = fg_count

    # Transactions
    ts_fields = ["interchange_ctrl", "gs_ctrl", "st_ctrl", "set_id", "payment_amount",
                 "total_billed_amount", "total_paid_amount", "claim_count", "loop_count", "summary_json"]
    ts_path = output_dir / "transactions.csv"
    ts_count = 0
    with open(ts_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ts_fields)
        w.writeheader()
        for ic in data.get("interchanges", []):
            ic_ctrl = _safe(ic.get("header", {}).get("elements", {}).get("e13", ""))
            for fg in ic.get("functional_groups", []):
                gs_ctrl = _safe(fg.get("header", {}).get("elements", {}).get("e6", ""))
                for ts in fg.get("transactions", []):
                    st = ts.get("header", {})
                    summary = ts.get("summary", {})
                    row = {
                        "interchange_ctrl": ic_ctrl,
                        "gs_ctrl": gs_ctrl,
                        "st_ctrl": _safe(st.get("elements", {}).get("e2", "")),
                        "set_id": _safe(ts.get("set_id", "")),
                        "payment_amount": _fmt_money(summary.get("payment_amount")),
                        "total_billed_amount": _fmt_money(summary.get("total_billed_amount")),
                        "total_paid_amount": _fmt_money(summary.get("total_paid_amount")),
                        "claim_count": _safe(summary.get("claim_count", "")),
                        "loop_count": _safe(summary.get("loop_count", "")),
                        "summary_json": "",  # populated below
                    }
                    # Write with summary JSON
                    summary_copy = {k: v for k, v in row.items()}
                    summary_copy["summary_json"] = json.dumps(summary, ensure_ascii=False)
                    w.writerow(summary_copy)
                    ts_count += 1
    counts["transactions.csv"] = ts_count

    # 835 claims (overwrite with full fields from the helper)
    claims_835_path = output_dir / "claims_835.csv"
    with open(claims_835_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_CLAIMS_835_FIELDS)
        w.writeheader()
        for rec in _build_835_claim_records(data):
            w.writerow(rec)
    # Count needs re-iteration — collect first
    c835_count = sum(1 for _ in _build_835_claim_records(data))
    counts["claims_835.csv"] = c835_count

    # 837 claims
    claims_837_path = output_dir / "claims_837.csv"
    with open(claims_837_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_CLAIMS_837_FIELDS)
        w.writeheader()
        for rec in _build_837_claim_records(data):
            w.writerow(rec)
    c837_count = sum(1 for _ in _build_837_claim_records(data))
    counts["claims_837.csv"] = c837_count

    # Service lines
    svc_path = output_dir / "service_lines.csv"
    with open(svc_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_SVC_LINE_FIELDS)
        w.writeheader()
        for rec in _build_service_line_records(data):
            w.writerow(rec)
    svc_count = sum(1 for _ in _build_service_line_records(data))
    counts["service_lines.csv"] = svc_count

    # Entities
    entity_path = output_dir / "entities.csv"
    with open(entity_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_ENTITY_FIELDS)
        w.writeheader()
        for rec in _build_entity_records(data):
            w.writerow(rec)
    entity_count = sum(1 for _ in _build_entity_records(data))
    counts["entities.csv"] = entity_count

    # Import guide
    guide = f"""\
X12 Parser — SQLite Import Guide
=================================

1. Create the database and load the schema:
   sqlite3 x12.db < schema.sql

2. Import each CSV file (repeat for each file):
   sqlite3 x12.db -cmd ".mode csv" -cmd ".import interchanges.csv interchanges" .quit
   sqlite3 x12.db -cmd ".mode csv" -cmd ".import functional_groups.csv functional_groups" .quit
   sqlite3 x12.db -cmd ".mode csv" -cmd ".import transactions.csv transactions" .quit
   sqlite3 x12.db -cmd ".mode csv" -cmd ".import claims_835.csv claims_835" .quit
   sqlite3 x12.db -cmd ".mode csv" -cmd ".import claims_837.csv claims_837" .quit
   sqlite3 x12.db -cmd ".mode csv" -cmd ".import service_lines.csv service_lines" .quit
   sqlite3 x12.db -cmd ".mode csv" -cmd ".import entities.csv entities" .quit

3. Verify:
   sqlite3 x12.db "SELECT COUNT(*) AS total_claims FROM claims_835;"
   sqlite3 x12.db "SELECT * FROM claims_835 LIMIT 5;"

Exported record counts:
"""
    for fname, cnt in sorted(counts.items()):
        guide += f"  {fname}: {cnt} records\n"
    (output_dir / "IMPORT_GUIDE.txt").write_text(guide)

    return counts


def _fmt_isa_date(v: str) -> str:
    """Format ISA date CCYYMMDD → CCYY-MM-DD."""
    v = str(v).strip()
    if len(v) >= 8:
        return f"{v[:4]}-{v[4:6]}-{v[6:8]}"
    return v


def _fmt_gs_date(v: str) -> str:
    """Format GS date CCYYMMDD → CCYY-MM-DD."""
    return _fmt_isa_date(v)
