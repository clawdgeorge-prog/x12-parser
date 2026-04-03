"""Tests for X12 Parser — fixtures 835 and 837."""

import json
import pathlib
import sys

# Add src to path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.parser import (
    X12Parser, X12Tokenizer, X12SegmentParser,
    parse, parse_file,
    DEFAULT_ELEM_SEP, DEFAULT_COMP_SEP, DEFAULT_SEG_TERM,
)


FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# ── Tokenizer tests ───────────────────────────────────────────────────────────

class TestTokenizer:
    def test_basic_split(self):
        t = X12Tokenizer()
        segs = t.tokenize("ST*835*0001~SE*15*0001~")
        assert segs == ["ST*835*0001", "SE*15*0001"]

    def test_multiline(self):
        t = X12Tokenizer()
        text = "ST*835*0001\nSE*15*0001\nIEA*1*000001"
        segs = t.tokenize(text)
        assert segs == ["ST*835*0001", "SE*15*0001", "IEA*1*000001"]

    def test_crlf_normalized(self):
        t = X12Tokenizer()
        segs = t.tokenize("ST*835*0001\r\nSE*15*0001\rIEA*1*000001")
        assert segs == ["ST*835*0001", "SE*15*0001", "IEA*1*000001"]


# ── Segment parser tests ───────────────────────────────────────────────────────

class TestSegmentParser:
    def test_parse_st(self):
        p = X12SegmentParser(elem_sep="*")
        seg = p.parse("ST*835*0001*005010X221A1", position=1)
        assert seg.tag == "ST"
        assert seg.elements[0].raw == "835"
        assert seg.elements[1].raw == "0001"

    def test_get_element(self):
        p = X12SegmentParser(elem_sep="*")
        seg = p.parse("BPR*H*1000*C*ACH", position=1)
        assert p.get(seg, 1) == "H"
        assert p.get(seg, 2) == "1000"
        assert p.get(seg, 99) is None

    def test_get_sub_element(self):
        p = X12SegmentParser(elem_sep="*")
        # Build a segment with a composite element at e3: "12:345"
        # CLM*e1*extra*e3=12:345
        seg = p.parse("CLM*CLM001*extra*12:345", position=1)
        # e1=CLM001, e2=extra, e3=12:345
        sub = p.get(seg, 3, sub_index=1)
        assert sub == "12", f"Expected '12', got {sub!r}"
        sub2 = p.get(seg, 3, sub_index=2)
        assert sub2 == "345", f"Expected '345', got {sub2!r}"


# ── File-level fixture tests ───────────────────────────────────────────────────

class Test835:
    @classmethod
    def setup_class(cls):
        fixture = FIXTURES / "sample_835.edi"
        cls.parser = X12Parser.from_file(fixture)
        cls.data = cls.parser.to_dict()

    def test_interchange_header(self):
        ic = self.data["interchanges"][0]
        assert ic["header"]["tag"] == "ISA"
        assert ic["isa06_sender"] == "SUBMITTER"
        assert ic["isa08_receiver"] == "RECEIVER"

    def test_gs_envelope(self):
        ic = self.data["interchanges"][0]
        fg = ic["functional_groups"][0]
        assert fg["header"]["tag"] == "GS"

    def test_transaction_set(self):
        ic = self.data["interchanges"][0]
        fg = ic["functional_groups"][0]
        ts = fg["transactions"][0]
        assert ts["header"]["tag"] == "ST"
        assert ts["set_id"] == "835"

    def test_loops_present(self):
        ic = self.data["interchanges"][0]
        fg = ic["functional_groups"][0]
        ts = fg["transactions"][0]
        loop_ids = [l["id"] for l in ts["loops"]]
        assert "PR" in loop_ids or "PE" in loop_ids or "QC" in loop_ids

    def test_segment_count_reasonable(self):
        ic = self.data["interchanges"][0]
        fg = ic["functional_groups"][0]
        ts = fg["transactions"][0]
        total = sum(len(l["segments"]) for l in ts["loops"])
        assert total >= 5, "Should have at least 5 segments inside transaction"

    def test_iea_trailer_present(self):
        ic = self.data["interchanges"][0]
        assert ic["trailer"]["tag"] == "IEA"


class Test837Professional:
    @classmethod
    def setup_class(cls):
        fixture = FIXTURES / "sample_837_prof.edi"
        cls.parser = X12Parser.from_file(fixture)
        cls.data = cls.parser.to_dict()

    def test_interchange_header(self):
        ic = self.data["interchanges"][0]
        assert ic["header"]["tag"] == "ISA"

    def test_transaction_set_id(self):
        ic = self.data["interchanges"][0]
        fg = ic["functional_groups"][0]
        ts = fg["transactions"][0]
        assert ts["set_id"] == "837"

    def test_hierarchical_levels(self):
        ic = self.data["interchanges"][0]
        fg = ic["functional_groups"][0]
        ts = fg["transactions"][0]
        # HL segments should appear in loops
        all_tags = []
        for loop in ts["loops"]:
            for seg in loop["segments"]:
                all_tags.append(seg["tag"])
        assert "HL" in all_tags

    def test_bht_present(self):
        ic = self.data["interchanges"][0]
        fg = ic["functional_groups"][0]
        ts = fg["transactions"][0]
        all_tags = []
        for loop in ts["loops"]:
            for seg in loop["segments"]:
                all_tags.append(seg["tag"])
        assert "BHT" in all_tags

    def test_svc_present(self):
        ic = self.data["interchanges"][0]
        fg = ic["functional_groups"][0]
        ts = fg["transactions"][0]
        all_tags = []
        for loop in ts["loops"]:
            for seg in loop["segments"]:
                all_tags.append(seg["tag"])
        assert "SV1" in all_tags or "SV2" in all_tags


class Test837Institutional:
    @classmethod
    def setup_class(cls):
        fixture = FIXTURES / "sample_837_institutional.edi"
        cls.parser = X12Parser.from_file(fixture)
        cls.data = cls.parser.to_dict()

    def test_interchange_header(self):
        ic = self.data["interchanges"][0]
        assert ic["header"]["tag"] == "ISA"

    def test_transaction_set_id(self):
        ic = self.data["interchanges"][0]
        fg = ic["functional_groups"][0]
        ts = fg["transactions"][0]
        assert ts["set_id"] == "837"

    def test_sv2_present(self):
        ic = self.data["interchanges"][0]
        fg = ic["functional_groups"][0]
        ts = fg["transactions"][0]
        all_tags = []
        for loop in ts["loops"]:
            for seg in loop["segments"]:
                all_tags.append(seg["tag"])
        assert "SV2" in all_tags, "Institutional claims use SV2"


# ── Loop metadata ─────────────────────────────────────────────────────────────

class TestLoopMetadata:
    """Verify that loop output includes enriched metadata fields."""

    def test_835_loop_has_all_metadata_fields(self):
        fixture = FIXTURES / "sample_835.edi"
        data = X12Parser.from_file(fixture).to_dict()
        ts = data["interchanges"][0]["functional_groups"][0]["transactions"][0]
        for loop in ts["loops"]:
            assert "leader_tag" in loop, f"loop {loop['id']} missing leader_tag"
            assert "leader_code" in loop, f"loop {loop['id']} missing leader_code"
            assert "kind" in loop, f"loop {loop['id']} missing kind"
            assert "description" in loop, f"loop {loop['id']} missing description"
            assert loop["leader_tag"] != "", f"loop {loop['id']} has empty leader_tag"
            assert loop["kind"] != "", f"loop {loop['id']} has empty kind"
            assert loop["description"] != "", f"loop {loop['id']} has empty description"

    def test_835_loop_kind_values_recognized(self):
        fixture = FIXTURES / "sample_835.edi"
        data = X12Parser.from_file(fixture).to_dict()
        ts = data["interchanges"][0]["functional_groups"][0]["transactions"][0]
        valid_kinds = {
            "entity", "claim", "service", "header", "adjustment",
            "amount", "date", "reference", "diagnosis", "payment",
            "trace", "other",
        }
        for loop in ts["loops"]:
            assert loop["kind"] in valid_kinds, \
                f"loop {loop['id']} has unknown kind: {loop['kind']}"

    def test_835_plb_loop_kind_is_adjustment(self):
        fixture = FIXTURES / "sample_835_rich.edi"
        data = X12Parser.from_file(fixture).to_dict()
        ts = data["interchanges"][0]["functional_groups"][0]["transactions"][0]
        plb_loops = [l for l in ts["loops"] if l["leader_tag"] == "PLB"]
        assert len(plb_loops) >= 1, "PLB loop not found in rich 835"
        for l in plb_loops:
            assert l["kind"] == "adjustment", f"PLB loop has kind={l['kind']}"

    def test_837_nm1_loops_kind_is_entity(self):
        fixture = FIXTURES / "sample_837_prof.edi"
        data = X12Parser.from_file(fixture).to_dict()
        ts = data["interchanges"][0]["functional_groups"][0]["transactions"][0]
        nm1_loops = [l for l in ts["loops"] if l["leader_tag"] == "NM1"]
        assert len(nm1_loops) >= 1
        for l in nm1_loops:
            assert l["kind"] == "entity", f"NM1 loop has kind={l['kind']}"

    def test_837_svc_loops_kind_is_service(self):
        fixture = FIXTURES / "sample_837_prof.edi"
        data = X12Parser.from_file(fixture).to_dict()
        ts = data["interchanges"][0]["functional_groups"][0]["transactions"][0]
        svc_loops = [l for l in ts["loops"] if l["leader_tag"] in ("SV1", "SV2", "LX")]
        assert len(svc_loops) >= 1
        for l in svc_loops:
            assert l["kind"] in ("service",), f"{l['leader_tag']} loop has kind={l['kind']}"


# ── Rich 835 fixture ─────────────────────────────────────────────────────────

class Test835Rich:
    @classmethod
    def setup_class(cls):
        fixture = FIXTURES / "sample_835_rich.edi"
        cls.parser = X12Parser.from_file(fixture)
        cls.data = cls.parser.to_dict()

    def test_interchange_header(self):
        ic = self.data["interchanges"][0]
        assert ic["header"]["tag"] == "ISA"

    def test_transaction_set_id(self):
        ic = self.data["interchanges"][0]
        ts = ic["functional_groups"][0]["transactions"][0]
        assert ts["set_id"] == "835"

    def test_has_plb_segments(self):
        ic = self.data["interchanges"][0]
        ts = ic["functional_groups"][0]["transactions"][0]
        all_tags = [s["tag"] for l in ts["loops"] for s in l["segments"]]
        assert "PLB" in all_tags, "Rich 835 should contain PLB segments"

    def test_multiple_lx_loops(self):
        ic = self.data["interchanges"][0]
        ts = ic["functional_groups"][0]["transactions"][0]
        lx_loops = [l for l in ts["loops"] if l["leader_tag"] == "LX"]
        assert len(lx_loops) >= 3, f"Expected >=3 LX loops, got {len(lx_loops)}"

    def test_has_per_segment(self):
        ic = self.data["interchanges"][0]
        ts = ic["functional_groups"][0]["transactions"][0]
        all_tags = [s["tag"] for l in ts["loops"] for s in l["segments"]]
        assert "PER" in all_tags

    def test_se_count_present(self):
        ic = self.data["interchanges"][0]
        ts = ic["functional_groups"][0]["transactions"][0]
        assert ts["trailer"]["elements"]["e1"] not in (None, "", "0")


# ── Rich 837 Professional fixture ─────────────────────────────────────────────

class Test837ProfRich:
    @classmethod
    def setup_class(cls):
        fixture = FIXTURES / "sample_837_prof_rich.edi"
        cls.parser = X12Parser.from_file(fixture)
        cls.data = cls.parser.to_dict()

    def test_interchange_header(self):
        ic = self.data["interchanges"][0]
        assert ic["header"]["tag"] == "ISA"

    def test_transaction_set_id(self):
        ts = self.data["interchanges"][0]["functional_groups"][0]["transactions"][0]
        assert ts["set_id"] == "837"

    def test_multiple_hl_levels(self):
        ts = self.data["interchanges"][0]["functional_groups"][0]["transactions"][0]
        hl_loops = [l for l in ts["loops"] if l["leader_tag"] == "HL"]
        assert len(hl_loops) >= 2, f"Expected >=2 HL loops, got {len(hl_loops)}"

    def test_has_nested_subscriber_hl(self):
        ts = self.data["interchanges"][0]["functional_groups"][0]["transactions"][0]
        # Find subscriber-level HL loops (child of billing provider HL, HL ID "2")
        subscriber_hls = [l for l in ts["loops"] if l["leader_tag"] == "HL" and l["leader_code"] == "2"]
        assert len(subscriber_hls) >= 1, f"Expected at least 1 subscriber HL loop, got {len(subscriber_hls)}"


# ── Multi-transaction fixture ─────────────────────────────────────────────────

class TestMultiTransaction:
    @classmethod
    def setup_class(cls):
        fixture = FIXTURES / "sample_multi_transaction.edi"
        cls.parser = X12Parser.from_file(fixture)
        cls.data = cls.parser.to_dict()

    def test_three_transactions_in_one_group(self):
        fg = self.data["interchanges"][0]["functional_groups"][0]
        assert len(fg["transactions"]) == 3

    def test_all_set_id_835(self):
        fg = self.data["interchanges"][0]["functional_groups"][0]
        assert all(ts["set_id"] == "835" for ts in fg["transactions"])

    def test_distinct_transaction_ids(self):
        fg = self.data["interchanges"][0]["functional_groups"][0]
        ids = [ts["header"]["elements"]["e2"] for ts in fg["transactions"]]
        assert len(set(ids)) == 3

    def test_each_transaction_has_loops(self):
        fg = self.data["interchanges"][0]["functional_groups"][0]
        assert all(len(ts["loops"]) >= 1 for ts in fg["transactions"])


# ── Multi-interchange fixture ──────────────────────────────────────────────────

class TestMultiInterchange:
    @classmethod
    def setup_class(cls):
        fixture = FIXTURES / "sample_multi_interchange.edi"
        cls.parser = X12Parser.from_file(fixture)
        cls.data = cls.parser.to_dict()

    def test_three_interchanges(self):
        assert len(self.data["interchanges"]) == 3

    def test_ic1_is_835(self):
        ts = self.data["interchanges"][0]["functional_groups"][0]["transactions"][0]
        assert ts["set_id"] == "835"

    def test_ic2_is_835(self):
        ts = self.data["interchanges"][1]["functional_groups"][0]["transactions"][0]
        assert ts["set_id"] == "835"

    def test_ic3_is_837(self):
        ts = self.data["interchanges"][2]["functional_groups"][0]["transactions"][0]
        assert ts["set_id"] == "837"

    def test_ic3_sender_extracted(self):
        ic3 = self.data["interchanges"][2]
        assert ic3["isa06_sender"] == "THIRDIC"
        assert ic3["isa08_receiver"] == "THIRDRCV"


# ── Whitespace-irregular fixture ──────────────────────────────────────────────

class TestWhitespaceIrregular:
    @classmethod
    def setup_class(cls):
        fixture = FIXTURES / "sample_whitespace_irregular.edi"
        cls.parser = X12Parser.from_file(fixture)
        cls.data = cls.parser.to_dict()

    def test_parses_without_crash(self):
        # Should not raise
        ic = self.data["interchanges"][0]
        assert ic["header"]["tag"] == "ISA"

    def test_transaction_is_835(self):
        ts = self.data["interchanges"][0]["functional_groups"][0]["transactions"][0]
        assert ts["set_id"] == "835"

    def test_has_clp_loop(self):
        ts = self.data["interchanges"][0]["functional_groups"][0]["transactions"][0]
        assert any(l["leader_tag"] == "CLP" for l in ts["loops"])

    def test_has_nm1_qc_loop(self):
        ts = self.data["interchanges"][0]["functional_groups"][0]["transactions"][0]
        assert any(l["leader_code"] == "QC" for l in ts["loops"])


# ── JSON roundtrip ─────────────────────────────────────────────────────────────

def test_json_serializable():
    fixture = FIXTURES / "sample_835.edi"
    parser = X12Parser.from_file(fixture)
    data = parser.to_dict()
    # Should not raise
    json.dumps(data)
    assert True


def test_json_serializable_837():
    fixture = FIXTURES / "sample_837_prof.edi"
    parser = X12Parser.from_file(fixture)
    data = parser.to_dict()
    json.dumps(data)
    assert True


# ── Helper parser functions ─────────────────────────────────────────────────────

def test_parse_file_function():
    fixture = FIXTURES / "sample_835.edi"
    p = parse_file(fixture)
    assert len(p.interchanges) >= 1


def test_parse_function():
    text = (FIXTURES / "sample_835.edi").read_text()
    p = parse(text)
    assert len(p.interchanges) >= 1
    ic = p.interchanges[0]
    assert ic.header.tag == "ISA"
    assert len(ic.groups) >= 1
    assert len(ic.groups[0].transactions) >= 1
    assert ic.groups[0].transactions[0].set_id == "835"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
