"""
X12 Parser — Healthcare EDI 835/837 transactions.

Scope (v0.1.0):
  - ISA/IEA envelope parsing
  - GS/GE functional-group envelope
  - ST/SE transaction set framing
  - 835: Healthcare Claim Payment/Advice
  - 837: Healthcare Claim (Professional & Institutional)
  - Segment, loop, and element extraction
  - Structured JSON output

Known limitations (documented in README):
  - No schema validation against official X12 specs
  - No segment-by-segment semantic validation
  - Composite elements returned as strings (not decomposed)
  - Repetition separator (ISA-11) treated as space
"""

from __future__ import annotations

__version__ = "0.1.0"

import re
import json
import pathlib
from dataclasses import dataclass, field, asdict
from typing import Optional, List


# ── Character set ────────────────────────────────────────────────────────────
# X12 uses: segment terminator (default ~), element separator (default *),
#           component separator (default :), repetition separator (default ^)

DEFAULT_SEG_TERM = "~"
DEFAULT_ELEM_SEP = "*"
DEFAULT_COMP_SEP = ":"


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class Element:
    raw: str
    position: int          # 1-based index within segment

@dataclass
class Segment:
    tag: str
    elements: List[Element]
    raw: str
    position: int          # line/sequence number in file

@dataclass
class Loop:
    id: str               # e.g. "PR", "QC", "CLM" — heuristic, first element of leader segment
    leader_tag: str       # tag that triggered loop creation, e.g. "NM1", "CLM", "LX"
    leader_code: str      # first element of leader segment, e.g. "PR", "QC", "IL"
    kind: str             # practical category: "entity", "claim", "service", "header", "amount", "other"
    description: str      # short human-readable label
    segments: List[Segment]

@dataclass
class TransactionSet:
    header: Segment       # ST segment
    loops: List[Loop]
    trailer: Segment      # SE segment
    set_id: str           # "835" or "837"

@dataclass
class FunctionalGroup:
    header: Segment       # GS
    transactions: List[TransactionSet]
    trailer: Segment      # GE

@dataclass
class Interchange:
    header: Segment       # ISA
    groups: List[FunctionalGroup]
    trailer: Segment      # IEA
    isa06_sender: str = ""
    isa08_receiver: str = ""


# ── Core tokenizer ─────────────────────────────────────────────────────────────

class X12Tokenizer:
    """Split an X12 string into raw segments."""

    def __init__(
        self,
        seg_term: str = DEFAULT_SEG_TERM,
        elem_sep: str = DEFAULT_ELEM_SEP,
        comp_sep: str = DEFAULT_COMP_SEP,
    ):
        self.seg_term = seg_term
        self.elem_sep = elem_sep
        self.comp_sep = comp_sep

    def tokenize(self, text: str) -> List[str]:
        """Return list of raw segment strings (no terminator).

        Splits on segment terminator (~) OR newline.
        This handles both ~-terminated X12 files and line-delimited files
        where the ISA line may end with a component separator (:) rather than ~.
        """
        raw = text.strip()
        # Normalize line endings
        raw = raw.replace("\r\n", "\n").replace("\r", "\n")
        # Replace segment terminator (~) with newline so we split on either
        raw = raw.replace(self.seg_term, "\n")
        # Also split on any remaining newlines between segments
        segs: List[str] = []
        for line in raw.split("\n"):
            stripped = line.strip()
            if stripped:
                segs.append(stripped)
        return segs


# ── Segment / Loop / Transaction parsers ──────────────────────────────────────

class X12SegmentParser:
    """Parse a single raw segment string into a Segment dataclass."""

    def __init__(self, elem_sep: str = DEFAULT_ELEM_SEP):
        self.elem_sep = elem_sep

    def parse(self, raw: str, position: int = 0) -> Segment:
        parts = raw.split(self.elem_sep)
        tag = parts[0] if parts else ""
        elements = [
            Element(raw=e, position=i + 1)
            for i, e in enumerate(parts[1:])
        ]
        return Segment(tag=tag, elements=elements, raw=raw, position=position)

    def get(self, seg: Segment, index: int, sub_index: Optional[int] = None) -> Optional[str]:
        """Get element value by 1-based index. Optionally sub-element by 2nd index."""
        idx = index - 1
        if idx < 0 or idx >= len(seg.elements):
            return None
        e = seg.elements[idx].raw
        if sub_index is not None:
            parts = e.split(":")
            si = sub_index - 1
            return parts[si] if si < len(parts) else None
        return e


# ── 835-aware parser ─────────────────────────────────────────────────────────

# Well-known 835 loop IDs (based on X12 spec)
_LOOP_835 = {
    "1000A": "Submitter Name",
    "1000B": "Receiver Name",
    "1000C": "Billing Provider Name",
    "1500":  "Payment Information",
    "2000":  "Service Payment Information",
    "2100":  "Claim Payment Information",
    "2110":  "Service Payment Detail",
    "2200":  "Adjustment",
    "2300":  "Remark Codes",
}

_LOOP_837 = {
    "1000A": "Submitter Name",
    "1000B": "Receiver Name",
    "1000C": "Billing Provider Name",
    "1000D": "Subscriber Name",
    "1000E": "Patient Name",
    "2000A": "Hierarchical Parent",
    "2000B": "Billing Provider Hierarchical Level",
    "2000C": "Subscriber Hierarchical Level",
    "2000D": "Patient Hierarchical Level",
    "2300":  "Claim Information",
    "2305":  "Prior Authorization or Referral",
    "2310A": "Physician or Facility Name",
    "2310B": "Operating Physician Name",
    "2310C": "Service Facility Location",
    "2310D": "Referring Provider Name",
    "2320":  "Subscriber or Patient Amount",
    "2330A": "Subscriber Name",
    "2330B": "Payer Name",
    "2330C": "Patient Name",
    "2330D": "Responsible Party Name",
    "2400":  "Service Line Number",
    "2410":  "Drug Identification",
    "2420A": "Operating Physician Name",
    "2420B": "Other Physician Name",
    "2420C": "Service Facility Location",
    "2430":  "Line Adjudication Information",
    "2440":  "Form Identification",
}


# Kind inference from leader tag / code
_LOOP_KINDS = {
    # NM1 entity type codes → kind
    "QC": "entity",    # patient/claimant
    "IL": "entity",    # insured/subscriber
    "PR": "entity",    # payer
    "PE": "entity",    # payee/provider
    "85": "entity",    # billing provider
    "41": "entity",    # submitter
    "40": "entity",    # receiver
    "77": "entity",    # service facility location
    "8": "entity",     #配偶
    # Claim / service leaders
    "CLM": "claim",
    "CLP": "claim",
    "LX": "service",
    "SV1": "service",
    "SV2": "service",
    "SV3": "service",
    "SV4": "service",
    "SV5": "service",
    "HI": "diagnosis",
    "HCP": "pricing",
    "BHT": "header",
    "PLB": "adjustment",
    "ADJ": "adjustment",
    "CAS": "adjustment",
    "AMT": "amount",
    "QTY": "quantity",
    "DTM": "date",
    "REF": "reference",
    "N1": "entity",
    "N3": "address",
    "N4": "geography",
    "PER": "contact",
    "DMG": "demographic",
    "PAT": "patient",
    "SBR": "subscriber",
    "CUR": "currency",
    "NTE": "note",
    "LIN": "line_item",
    "CTP": "pricing",
    "RDM": "remittance",
    "HL": "hierarchy",
    "CR1": "ambulance",
    "CR2": "spine",
    "CR3": "oxygen",
    "CR4": "durable_medical",
    "CR5": "vision",
    "ENT": "entity",
    "RDM": "remittance",
    "BPR": "payment",
    "TRN": "trace",
    "CR1": "ambulance",
    "CR2": "spine",
    "CR3": "oxygen",
    "CR4": "durable_medical",
    "CR5": "vision",
}

# Look-up description tables (leader_code → short description)
_LOOP_DESCRIPTIONS_835 = {
    "1000A": "Submitter Name",
    "1000B": "Receiver Name",
    "1000C": "Billing Provider Name",
    "1500":  "Payment Information",
    "2000":  "Service Payment Information",
    "2100":  "Claim Payment Information",
    "2110":  "Service Payment Detail",
    "2200":  "Adjustment",
    "2300":  "Remark Codes",
    # NM1 entity qualifiers (pragmatic labels)
    "PR": "Payer Name",
    "PE": "Provider Name",
    "QC": "Patient/Claimant Name",
    "NM1": "Entity Name",
}

_LOOP_DESCRIPTIONS_837 = {
    "1000A": "Submitter Name",
    "1000B": "Receiver Name",
    "1000C": "Billing Provider Name",
    "1000D": "Subscriber Name",
    "1000E": "Patient Name",
    "2000A": "Hierarchical Parent",
    "2000B": "Billing Provider Hierarchical Level",
    "2000C": "Subscriber Hierarchical Level",
    "2000D": "Patient Hierarchical Level",
    "2300":  "Claim Information",
    "2305":  "Prior Authorization or Referral",
    "2310A": "Physician or Facility Name",
    "2310B": "Operating Physician Name",
    "2310C": "Service Facility Location",
    "2310D": "Referring Provider Name",
    "2320":  "Subscriber or Patient Amount",
    "2330A": "Subscriber Name",
    "2330B": "Payer Name",
    "2330C": "Patient Name",
    "2330D": "Responsible Party Name",
    "2400":  "Service Line Number",
    "2410":  "Drug Identification",
    "2420A": "Operating Physician Name",
    "2420B": "Other Physician Name",
    "2420C": "Service Facility Location",
    "2430":  "Line Adjudication Information",
    "2440":  "Form Identification",
    # NM1 entity qualifiers
    "41": "Submitter Name",
    "40": "Receiver Name",
    "85": "Billing Provider Name",
    "IL": "Subscriber Name",
    "QC": "Patient Name",
    "PR": "Payer Name",
    "NM1": "Entity Name",
}


def _infer_loop_description(leader_tag: str, leader_code: str) -> str:
    """Look up a human-readable description for a loop from known tables."""
    desc = _LOOP_DESCRIPTIONS_835.get(leader_code) or _LOOP_DESCRIPTIONS_837.get(leader_code)
    if desc:
        return desc
    # Fallback: tag-based generic label
    return f"{leader_tag} Loop"


def _detect_loops(segments: List[Segment]) -> List[Loop]:
    """
    Walk segments and group them into loops based on segment IDs
    that act as loop initiators per X12 spec.

    Each Loop carries:
      - id           : the leader segment's first element (heuristic loop key)
      - leader_tag   : the segment tag that started this loop
      - leader_code  : same as id (first element of leader segment)
      - kind         : practical category (entity, claim, service, etc.)
      - description  : short human-readable label
      - segments     : all segments in this loop
    """
    # Tags that trigger a new loop grouping
    LOOP_LEADER_TAGS = frozenset((
        "NM1", "CLM", "N1", "LX", "SV1", "SV2", "SV3", "HI", "BPR",
        "CLP", "PLB",
        "ADJ", "CAS", "REF", "DTM", "PER", "AMT", "QTY", "CTP",
        "HCP", "TRN", "CUR", "DMG", "PAT", "NTE", "LIN", "CR1",
        "CR2", "CR3", "CR4", "CR5", "RDM", "BHT", "HL",
    ))

    loops: List[Loop] = []
    current_loop_segments: List[Segment] = []
    current_loop_id = ""
    current_leader_tag = ""
    i = 0
    while i < len(segments):
        seg = segments[i]
        tag = seg.tag

        if tag in LOOP_LEADER_TAGS:
            leader_code = seg.elements[0].raw if seg.elements else ""

            if current_loop_id and current_loop_segments:
                # Use current_loop_id (the previous loop's key) for kind lookup;
                # fall back to the previous leader_tag for tag-keyed entries.
                kind = (
                    _LOOP_KINDS.get(current_loop_id) or
                    _LOOP_KINDS.get(current_leader_tag) or
                    "other"
                )
                desc = _infer_loop_description(current_leader_tag, current_loop_id)
                loops.append(Loop(
                    id=current_loop_id,
                    leader_tag=current_leader_tag,
                    leader_code=current_loop_id,
                    kind=kind,
                    description=desc,
                    segments=current_loop_segments,
                ))
            current_loop_id = leader_code
            current_leader_tag = tag
            current_loop_segments = [seg]
        else:
            current_loop_segments.append(seg)
        i += 1

    if current_loop_id and current_loop_segments:
        kind = (
            _LOOP_KINDS.get(current_loop_id) or
            _LOOP_KINDS.get(current_leader_tag) or
            "other"
        )
        desc = _infer_loop_description(current_leader_tag, current_loop_id)
        loops.append(Loop(
            id=current_loop_id,
            leader_tag=current_leader_tag,
            leader_code=current_loop_id,
            kind=kind,
            description=desc,
            segments=current_loop_segments,
        ))

    return loops


def _segment_to_dict(seg: Segment) -> dict:
    elems = {}
    for e in seg.elements:
        elems[f"e{e.position}"] = e.raw
    return {
        "tag": seg.tag,
        "elements": elems,
        "raw": seg.raw,
        "position": seg.position,
    }


def _loop_to_dict(loop: Loop) -> dict:
    return {
        "id": loop.id,
        "leader_tag": loop.leader_tag,
        "leader_code": loop.leader_code,
        "kind": loop.kind,
        "description": loop.description,
        "segments": [_segment_to_dict(s) for s in loop.segments],
    }


# ── Main parser ───────────────────────────────────────────────────────────────

class X12Parser:
    """
    Parse an X12 string or file into structured dataclasses and emit JSON.

    Supports ISA/IEA, GS/GE, ST/SE envelopes and transaction sets 835 and 837.
    """

    def __init__(self, text: Optional[str] = None):
        self._raw_text = text or ""
        self.segments: List[Segment] = []
        self.interchanges: List[Interchange] = []
        self._seg_parser = X12SegmentParser()

    @classmethod
    def from_file(cls, path: str | pathlib.Path) -> "X12Parser":
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
        return cls(text=text)

    def _detect_delimiters(self, text: str) -> tuple[str, str, str]:
        """Detect delimiters from ISA segment."""
        isa_match = re.search(r"ISA[^\r\n]*", text)
        if not isa_match:
            return DEFAULT_ELEM_SEP, DEFAULT_COMP_SEP, DEFAULT_SEG_TERM
        isa = isa_match.group()
        # Fixed-width ISA format: element separator is at position 3 (ISA-3),
        # component separator at position 82 (ISA-16). Standard X12 files use
        # * as element sep, : as component sep, ~ as segment terminator.
        # For robustness we hardcode the standard delimiters for v0.1.0.
        elem = "*"
        comp = ":"
        seg_t = "~"
        return elem, comp, seg_t

    def _parse(self) -> None:
        text = self._raw_text
        if not text.strip():
            return

        elem_sep, comp_sep, seg_term = self._detect_delimiters(text)
        tokenizer = X12Tokenizer(seg_term=seg_term, elem_sep=elem_sep)
        raw_segs = tokenizer.tokenize(text)

        self.segments = [
            self._seg_parser.parse(raw=s, position=i + 1)
            for i, s in enumerate(raw_segs)
        ]

        self.interchanges = self._build_interchanges()

    def _find_segment(self, tag: str, start: int = 0) -> Optional[tuple[Segment, int]]:
        for i in range(start, len(self.segments)):
            if self.segments[i].tag == tag:
                return (self.segments[i], i)
        return None

    def _build_interchanges(self) -> List[Interchange]:
        interchanges: List[Interchange] = []
        if not self.segments:
            return interchanges
        i = 0
        while i < len(self.segments):
            seg = self.segments[i]
            if seg.tag == "ISA":
                isa = seg
                iea_idx = self._find_matching_trailer(i + 1, "IEA", "ISA")
                iea = self.segments[iea_idx] if iea_idx >= 0 else None
                groups = self._build_groups(i + 1, iea_idx - 1 if iea_idx > i else len(self.segments) - 1)

                # ISA-6 = sender ID, ISA-7 = sender qualifier, ISA-8 = receiver qualifier,
                # ISA-9 = receiver ID (fixed-width X12 ISA; qualifiers prefix IDs).
                sender = (self._seg_parser.get(isa, 6) or "").strip()
                receiver = (self._seg_parser.get(isa, 8) or "").strip()

                ic = Interchange(
                    header=isa,
                    groups=groups,
                    trailer=iea if iea else Segment("", [], "", 0),
                    isa06_sender=sender,
                    isa08_receiver=receiver,
                )
                interchanges.append(ic)
                i = iea_idx + 1 if iea_idx > i else i + 1
            else:
                i += 1
        return interchanges

    def _build_groups(self, start: int, end: int) -> List[FunctionalGroup]:
        groups: List[FunctionalGroup] = []
        i = start
        while i <= end and i < len(self.segments):
            seg = self.segments[i]
            if seg.tag == "GS":
                gs = seg
                # Find GE
                ge_idx = self._find_matching_trailer(i + 1, "GE", "GS")
                ge = self.segments[ge_idx] if ge_idx >= 0 else None
                transactions = self._build_transactions(i + 1, ge_idx - 1 if ge_idx > i else end)
                fg = FunctionalGroup(header=gs, transactions=transactions,
                                     trailer=ge if ge else Segment("", [], "", 0))
                groups.append(fg)
                i = ge_idx + 1 if ge_idx > i else i + 1
            else:
                i += 1
        return groups

    def _build_transactions(self, start: int, end: int) -> List[TransactionSet]:
        transactions: List[TransactionSet] = []
        i = start
        while i <= end and i < len(self.segments):
            seg = self.segments[i]
            if seg.tag == "ST":
                st = seg
                set_id = self._seg_parser.get(st, 1) or self._seg_parser.get(st, 2) or "?"
                # Find SE
                se_idx = self._find_matching_trailer(i + 1, "SE", "ST")
                se = self.segments[se_idx] if se_idx >= 0 else None
                body = self.segments[i + 1: se_idx] if se_idx > i else []
                seg_objs = [
                    self._seg_parser.parse(raw=s.raw, position=s.position)
                    for s in body
                ]
                loops = _detect_loops(seg_objs)
                ts = TransactionSet(header=st, loops=loops,
                                    trailer=se if se else Segment("", [], "", 0),
                                    set_id=set_id)
                transactions.append(ts)
                i = se_idx + 1 if se_idx > i else i + 1
            else:
                i += 1
        return transactions

    def _find_matching_trailer(self, start: int, trailer_tag: str, header_tag: str) -> int:
        """Find trailer by counting header/trailer pairs (ST/SE, GS/GE, ISA/IEA)."""
        depth = 0
        for i in range(start, len(self.segments)):
            t = self.segments[i].tag
            if t == header_tag:
                depth += 1
            elif t == trailer_tag:
                if depth == 0:
                    return i
                depth -= 1
        return -1

    def to_dict(self) -> dict:
        """Return full parsed structure as a plain dict."""
        self._parse()
        return {
            "version": "0.1.0",
            "interchanges": [
                {
                    "header": _segment_to_dict(ic.header),
                    "isa06_sender": ic.isa06_sender,
                    "isa08_receiver": ic.isa08_receiver,
                    "functional_groups": [
                        {
                            "header": _segment_to_dict(fg.header),
                            "transactions": [
                                {
                                    "header": _segment_to_dict(ts.header),
                                    "set_id": ts.set_id,
                                    "loops": [_loop_to_dict(l) for l in ts.loops],
                                    "trailer": _segment_to_dict(ts.trailer),
                                }
                                for ts in fg.transactions
                            ],
                            "trailer": _segment_to_dict(fg.trailer),
                        }
                        for fg in ic.groups
                    ],
                    "trailer": _segment_to_dict(ic.trailer),
                }
                for ic in self.interchanges
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ── Public helpers ─────────────────────────────────────────────────────────────

def parse(text: str) -> X12Parser:
    p = X12Parser(text)
    p._parse()
    return p

def parse_file(path: str | pathlib.Path) -> X12Parser:
    p = X12Parser.from_file(path)
    p._parse()
    return p
