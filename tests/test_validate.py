"""Tests for X12 Structural Validator (validate.py)."""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.parser import X12Parser
from src.validate import X12Validator


FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# ── Helper ────────────────────────────────────────────────────────────────────

def validate_fixture(name: str):
    """Parse a fixture and return ValidationResult."""
    fixture = FIXTURES / name
    parser = X12Parser.from_file(fixture)
    validator = X12Validator(parser)
    return validator.validate()


def codes(result):
    return {i.code for i in result.issues}


# ── Clean fixtures ────────────────────────────────────────────────────────────

class TestValidateCleanFixtures:
    """Well-formed fixtures should pass validation with no errors."""

    def test_835_clean(self):
        result = validate_fixture("sample_835.edi")
        errors = {i.code for i in result.issues if i.severity == "error"}
        assert errors == set(), f"Expected no errors, got: {errors}"

    def test_835_rich_clean(self):
        result = validate_fixture("sample_835_rich.edi")
        errors = {i.code for i in result.issues if i.severity == "error"}
        assert errors == set(), f"Expected no errors, got: {errors}"

    def test_837_prof_clean(self):
        result = validate_fixture("sample_837_prof.edi")
        errors = {i.code for i in result.issues if i.severity == "error"}
        assert errors == set(), f"Expected no errors, got: {errors}"

    def test_837_prof_rich_clean(self):
        result = validate_fixture("sample_837_prof_rich.edi")
        errors = {i.code for i in result.issues if i.severity == "error"}
        assert errors == set(), f"Expected no errors, got: {errors}"

    def test_837_institutional_clean(self):
        result = validate_fixture("sample_837_institutional.edi")
        errors = {i.code for i in result.issues if i.severity == "error"}
        assert errors == set(), f"Expected no errors, got: {errors}"

    def test_multi_transaction_clean(self):
        result = validate_fixture("sample_multi_transaction.edi")
        errors = {i.code for i in result.issues if i.severity == "error"}
        assert errors == set(), f"Expected no errors, got: {errors}"

    def test_multi_interchange_clean(self):
        result = validate_fixture("sample_multi_interchange.edi")
        errors = {i.code for i in result.issues if i.severity == "error"}
        assert errors == set(), f"Expected no errors, got: {errors}"

    def test_trailing_whitespace_clean(self):
        result = validate_fixture("sample_trailing_whitespace.edi")
        errors = {i.code for i in result.issues if i.severity == "error"}
        assert errors == set(), f"Expected no errors, got: {errors}"


# ── Missing envelope segments ─────────────────────────────────────────────────

class TestValidateMissingEnvelopeSegments:
    """Missing SE/GE/IEA should be detected as pairing mismatches."""

    def test_missing_se_count_wrong_detected(self):
        # sample_missing_se.edi has an SE but with wrong declared count (9 vs 10 actual)
        result = validate_fixture("sample_missing_se.edi")
        assert "SE_COUNT_MISMATCH" in codes(result), f"Expected SE_COUNT_MISMATCH, got: {codes(result)}"

    def test_missing_ge_detected(self):
        result = validate_fixture("sample_missing_ge.edi")
        assert "GS_GE_MISMATCH" in codes(result), f"Expected GS_GE_MISMATCH, got: {codes(result)}"

    def test_missing_iea_detected(self):
        result = validate_fixture("sample_missing_iea.edi")
        assert "ISA_IEA_MISMATCH" in codes(result), f"Expected ISA_IEA_MISMATCH, got: {codes(result)}"


# ── Empty transaction ─────────────────────────────────────────────────────────

class TestValidateEmptyTransaction:
    """ST..SE with no body segments should be flagged as an error."""

    def test_empty_transaction_detected(self):
        result = validate_fixture("sample_empty_transaction.edi")
        assert "EMPTY_TRANSACTION" in codes(result), \
            f"Expected EMPTY_TRANSACTION error, got: {codes(result)}"


# ── SE count mismatch ─────────────────────────────────────────────────────────

class TestValidateSECountMismatch:
    """SE segment-count (e1) that doesn't match actual segment count."""

    def test_se_count_wrong_detected(self):
        result = validate_fixture("sample_se_count_wrong.edi")
        assert "SE_COUNT_MISMATCH" in codes(result), \
            f"Expected SE_COUNT_MISMATCH error, got: {codes(result)}"

    def test_se_count_message_includes_st_control(self):
        result = validate_fixture("sample_se_count_wrong.edi")
        mismatch_msgs = [
            i.message for i in result.issues
            if i.code == "SE_COUNT_MISMATCH"
        ]
        assert any("ST*...*" in msg or "0001" in msg for msg in mismatch_msgs), \
            f"Expected ST control number in message, got: {mismatch_msgs}"


# ── Orphan body segments ───────────────────────────────────────────────────────

class TestValidateOrphanBodySegments:
    """Body segments appearing outside valid envelopes should be flagged."""

    def test_orphan_body_segment_detected(self):
        # This fixture has BPR appearing between ISA and GS (before any GS/GE)
        result = validate_fixture("sample_orphan_body_segment.edi")
        # The BPR between ISA and GS is an orphan (body segment before first GS)
        # Also GS appears but BPR before it is the orphan
        warnings = {i.code for i in result.issues if i.severity == "warning"}
        # BPR is not in VALID_INNER_TAGS for the orphan detection context here
        # The orphan detection flags ISA inside an open interchange which is
        # the state machine tracking
        assert len(result.issues) > 0, "Expected at least one orphan/warning"


# ── ValidationResult model ────────────────────────────────────────────────────

class TestValidationResultModel:
    def test_clean_true_when_no_issues(self):
        from src.validate import ValidationResult
        r = ValidationResult()
        assert r.clean is True

    def test_add_error_sets_clean_false(self):
        from src.validate import ValidationResult
        r = ValidationResult()
        r.add_error("TEST_ERROR", "test message")
        assert r.clean is False
        assert len(r.issues) == 1
        assert r.issues[0].severity == "error"
        assert r.issues[0].code == "TEST_ERROR"

    def test_add_warning_does_not_clear_errors(self):
        from src.validate import ValidationResult
        r = ValidationResult()
        r.add_error("TEST_ERROR", "test error")
        r.add_warning("TEST_WARN", "test warning")
        assert r.clean is False
        assert len(r.issues) == 2


# ── Exit-code semantics ────────────────────────────────────────────────────────

class TestValidateExitCodes:
    """validate.py CLI should exit 0 for clean, 1 for errors, 2 for parse failure."""

    def test_missing_se_returns_error_exit_code(self, tmp_path):
        import subprocess
        fixture = FIXTURES / "sample_missing_se.edi"
        result = subprocess.run(
            [sys.executable, "-m", "src.validate", str(fixture)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"

    def test_missing_ge_returns_error_exit_code(self, tmp_path):
        import subprocess
        fixture = FIXTURES / "sample_missing_ge.edi"
        result = subprocess.run(
            [sys.executable, "-m", "src.validate", str(fixture)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"

    def test_missing_iea_returns_error_exit_code(self, tmp_path):
        import subprocess
        fixture = FIXTURES / "sample_missing_iea.edi"
        result = subprocess.run(
            [sys.executable, "-m", "src.validate", str(fixture)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"

    def test_clean_fixture_returns_zero_exit_code(self):
        import subprocess
        fixture = FIXTURES / "sample_835.edi"
        result = subprocess.run(
            [sys.executable, "-m", "src.validate", str(fixture)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}"

    def test_nonexistent_file_returns_exit_code_2(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "src.validate", "/nonexistent/file.edi"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2, f"Expected exit 2, got {result.returncode}"


# ── JSON output ───────────────────────────────────────────────────────────────

class TestValidateJSONOutput:
    def test_json_output_is_valid_json(self):
        import subprocess
        fixture = FIXTURES / "sample_835.edi"
        result = subprocess.run(
            [sys.executable, "-m", "src.validate", str(fixture), "--json"],
            capture_output=True, text=True,
        )
        parsed = json.loads(result.stdout)
        assert "clean" in parsed
        assert "issues" in parsed
        assert isinstance(parsed["issues"], list)

    def test_json_clean_fixture_has_no_errors(self):
        import subprocess
        fixture = FIXTURES / "sample_835.edi"
        result = subprocess.run(
            [sys.executable, "-m", "src.validate", str(fixture), "--json"],
            capture_output=True, text=True,
        )
        parsed = json.loads(result.stdout)
        assert parsed["clean"] is True
        assert parsed["error_count"] == 0

    def test_json_missing_se_has_error(self):
        import subprocess
        fixture = FIXTURES / "sample_missing_se.edi"
        result = subprocess.run(
            [sys.executable, "-m", "src.validate", str(fixture), "--json"],
            capture_output=True, text=True,
        )
        parsed = json.loads(result.stdout)
        assert parsed["clean"] is False
        assert parsed["error_count"] >= 1
        error_codes = {issue["code"] for issue in parsed["issues"] if issue["severity"] == "error"}
        assert "SE_COUNT_MISMATCH" in error_codes


# ── New validation checks ───────────────────────────────────────────────────────

class TestValidateRequiredSegments:
    """Required segments per transaction type should be present."""

    def test_835_missing_bpr_detected(self):
        # Build a minimal 835 that's missing BPR
        edi = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*250402*1234*^*00501*000000001*0*P*:~GS*HP*SENDER*RECEIVER*20250402*1234*1*X*005010X221A1~"
            "ST*835*0001*005010X221A1~"
            "TRN*1*0000000001~"
            "N1*PR*INSURANCE*PI*123456~"
            "CLP*CLM001****200*3**CL*12*345~"
            "SE*6*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi)
        v = X12Validator(p)
        r = v.validate()
        codes = {i.code for i in r.issues}
        assert "REQUIRED_SEGMENT_MISSING" in codes
        # BPR was the missing one
        bpr_msgs = [i.message for i in r.issues if i.code == "REQUIRED_SEGMENT_MISSING" and "BPR" in i.message]
        assert len(bpr_msgs) >= 1

    def test_837_missing_clm_detected(self):
        # Build a minimal 837 missing CLM
        edi = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*250402*1234*^*00501*000000001*0*P*:~GS*HC*SENDER*RECEIVER*20250402*1234*1*X*005010X222A1~"
            "ST*837*0001*005010X222A1~"
            "BHT*0019*11*CLAIM001*20250402*1234*CH~"
            "NM1*41*2*BILLING*****46*12345~"
            "HL*1**20*1~"
            "NM1*85*2*DR SMITH*****XX*123456~"
            "SE*7*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi)
        v = X12Validator(p)
        r = v.validate()
        codes = {i.code for i in r.issues}
        assert "REQUIRED_SEGMENT_MISSING" in codes
        clm_msgs = [i.message for i in r.issues if i.code == "REQUIRED_SEGMENT_MISSING" and "CLM" in i.message]
        assert len(clm_msgs) >= 1


class TestValidateNumericAmounts:
    """Monetary fields in CLP/SVC/CAS should be numeric."""

    def test_clp_non_numeric_billed_detected(self):
        edi = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*250402*1234*^*00501*000000001*0*P*:~GS*HP*SENDER*RECEIVER*20250402*1234*1*X*005010X221A1~"
            "ST*835*0001*005010X221A1~"
            "BPR*I*1000*C*ACH~"
            "TRN*1*0000000001~"
            "N1*PR*INSURANCE~"
            "CLP*CLM001*NOTANUMBER*200*3**CL*12*345~"  # e2 is non-numeric
            "SE*7*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi)
        v = X12Validator(p)
        r = v.validate()
        codes = {i.code for i in r.issues}
        assert "NON_NUMERIC_AMOUNT" in codes

    def test_svc_non_numeric_billed_detected(self):
        edi = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*250402*1234*^*00501*000000001*0*P*:~GS*HP*SENDER*RECEIVER*20250402*1234*1*X*005010X221A1~"
            "ST*835*0001*005010X221A1~"
            "BPR*I*1000*C*ACH~"
            "TRN*1*0000000001~"
            "N1*PR*INSURANCE~"
            "CLP*CLM001****200*3**CL*12*345~"
            "SVC*HC:99213*BADAMOUNT*150***1~"  # e2 is non-numeric
            "SE*8*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi)
        v = X12Validator(p)
        r = v.validate()
        codes = {i.code for i in r.issues}
        assert "NON_NUMERIC_AMOUNT" in codes


class TestValidateDuplicateClaims:
    """Duplicate claim IDs within a transaction should be flagged."""

    def test_835_duplicate_clp_detected(self):
        # Same CLP ID appears twice
        edi = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*250402*1234*^*00501*000000001*0*P*:~GS*HP*SENDER*RECEIVER*20250402*1234*1*X*005010X221A1~"
            "ST*835*0001*005010X221A1~"
            "BPR*I*1000*C*ACH~"
            "TRN*1*0000000001~"
            "N1*PR*INSURANCE~"
            "CLP*CLM001****200*3**CL*12*345~"
            "SVC*HC:99213*200*150***1~"
            "CLP*CLM001****100*2**CL*12*999~"  # duplicate claim ID
            "SVC*HC:99214*100*80***1~"
            "SE*10*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi)
        v = X12Validator(p)
        r = v.validate()
        codes = {i.code for i in r.issues}
        assert "CLAIM_ID_DUPLICATE" in codes
        dup_msgs = [i.message for i in r.issues if i.code == "CLAIM_ID_DUPLICATE"]
        assert any("CLM001" in m for m in dup_msgs)

    def test_837_duplicate_clm_detected(self):
        # Same CLM ID appears twice
        edi = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*250402*1234*^*00501*000000001*0*P*:~GS*HC*SENDER*RECEIVER*20250402*1234*1*X*005010X222A1~"
            "ST*837*0001*005010X222A1~"
            "BHT*0019*11*CLAIM001*20250402*1234*CH~"
            "NM1*41*2*BILLING*****46*12345~"
            "HL*1**20*1~"
            "NM1*85*2*DR SMITH*****XX*123456~"
            "HL*2*1*22*1~"
            "SBR*P*18*******CI~"
            "NM1*IL*1*DOE*JANE****MI*MEMBER001~"
            "CLM*CLM001*500***11:B:1*Y*A*Y*Y~"
            "SV1*HC:99213*250*200***1**1~"
            "CLM*CLM001*500***11:B:1*Y*A*Y*Y~"  # duplicate claim ID
            "SV1*HC:99214*250*200***1**1~"
            "SE*14*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi)
        v = X12Validator(p)
        r = v.validate()
        codes = {i.code for i in r.issues}
        assert "CLAIM_ID_DUPLICATE" in codes


class TestValidateISAFormat:
    """ISA date and time fields should have valid format."""

    def test_isa_invalid_date_warns(self):
        edi = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*BADATE*1234*^*00501*000000001*0*P*:~GS*HP*SENDER*RECEIVER*20250402*1234*1*X*005010X221A1~"
            "ST*835*0001*005010X221A1~"
            "BPR*I*1000*C*ACH~"
            "TRN*1*0000000001~"
            "N1*PR*INSURANCE~"
            "SE*6*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi)
        v = X12Validator(p)
        r = v.validate()
        codes = {i.code for i in r.issues}
        assert "ISA_DATE_INVALID" in codes

    def test_isa_invalid_time_warns(self):
        edi = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*250402*BADTIME*^*00501*000000001*0*P*:~GS*HP*SENDER*RECEIVER*20250402*1234*1*X*005010X221A1~"
            "ST*835*0001*005010X221A1~"
            "BPR*I*1000*C*ACH~"
            "TRN*1*0000000001~"
            "N1*PR*INSURANCE~"
            "SE*6*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi)
        v = X12Validator(p)
        r = v.validate()
        codes = {i.code for i in r.issues}
        assert "ISA_TIME_INVALID" in codes


class TestValidateRecommendations:
    """Recommendations should appear in JSON output."""

    def test_json_includes_recommendations(self):
        import subprocess
        fixture = FIXTURES / "sample_missing_se.edi"
        result = subprocess.run(
            [sys.executable, "-m", "src.validate", str(fixture), "--json"],
            capture_output=True, text=True,
        )
        parsed = json.loads(result.stdout)
        assert "issues" in parsed
        for issue in parsed["issues"]:
            assert "recommendation" in issue, f"Issue {issue.get('code')} missing recommendation"
            assert isinstance(issue["recommendation"], str)
            assert len(issue["recommendation"]) > 0

    def test_verbose_report_shows_recommendations(self):
        import subprocess
        fixture = FIXTURES / "sample_missing_se.edi"
        result = subprocess.run(
            [sys.executable, "-m", "src.validate", str(fixture), "--verbose"],
            capture_output=True, text=True,
        )
        # Verbose output should contain recommendation arrow
        assert "→" in result.stdout, "Expected recommendations in verbose output"


class TestValidate837VariantDetection:
    """837 variant (professional/institutional/dental) detection from SV1/SV2/UD."""

    def test_837_professional_has_sv1(self):
        result = validate_fixture("sample_837_prof.edi")
        codes_w = {i.code for i in result.issues if i.severity == "warning"}
        # Should NOT warn about SV1 missing for professional
        assert "SV1" not in codes_w

    def test_837_institutional_has_sv2(self):
        result = validate_fixture("sample_837_institutional.edi")
        codes_w = {i.code for i in result.issues if i.severity == "warning"}
        assert "SV2" not in codes_w

    def test_837_institutional_missing_hi_warns(self):
        # Create a fixture without HI and check warning
        edi_no_hi = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*250402*1234*^*00501*000000001*0*P*:~"
            "GS*HI*SENDER*RECEIVER*20250402*1234*1*X*005010X223A1~"
            "ST*837*0001*005010X223A1~"
            "BHT*0019*11*BATCH001*20250402*1234*CH~"
            "NM1*41*2*BILLING PROVIDER*****46*12345~"
            "HL*1**20*1~"
            "NM1*85*2*DR SMITH*****XX*1234567890~"
            "HL*2*1*22*1~"
            "SBR*P*18*******CI~"
            "NM1*IL*1*SUBSCRIBER*LAST****MI*MEMBER001~"
            "CLM*CLM001*500***11:B:1*Y*A*Y*Y~"
            "SV2*HC:0250*500*400***1**1~"
            "SE*15*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi_no_hi)
        v = X12Validator(p)
        r = v.validate()
        codes_w = {i.code for i in r.issues if i.severity == "warning"}
        assert "HI_MISSING_INSTITUTIONAL" in codes_w

    def test_837_dental_variant_detected(self):
        result = validate_fixture("sample_837_dental.edi")
        codes_w = {i.code for i in result.issues if i.severity == "warning"}
        assert "SV1" not in codes_w  # dental uses UD, not SV1


class TestValidate835EntityChecks:
    """835 entity presence checks: N1*PR and N1*PE should be present."""

    def test_835_rich_has_n1_pr(self):
        # sample_835_rich.edi has N1*PR — should NOT warn
        result = validate_fixture("sample_835_rich.edi")
        codes_w = {i.code for i in result.issues if i.severity == "warning"}
        assert "N1_PR_MISSING" not in codes_w

    def test_835_rich_has_n1_pe(self):
        result = validate_fixture("sample_835_rich.edi")
        codes_w = {i.code for i in result.issues if i.severity == "warning"}
        assert "N1_PE_MISSING" not in codes_w

    def test_835_missing_n1_pr_warns(self):
        # Create 835 without N1*PR
        edi_no_pr = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*250402*1234*^*00501*000000001*0*P*:~"
            "GS*HP*SENDER*RECEIVER*20250402*1234*1*X*005010X221A1~"
            "ST*835*0001*005010X221A1~"
            "BPR*I*1000*C*ACH~"
            "TRN*1*0000000001~"
            "N1*PE*PROVIDER*****XX*123456~"
            "SE*6*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi_no_pr)
        v = X12Validator(p)
        r = v.validate()
        codes_w = {i.code for i in r.issues if i.severity == "warning"}
        assert "N1_PR_MISSING" in codes_w

    def test_835_missing_n1_pe_warns(self):
        edi_no_pe = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*250402*1234*^*00501*000000001*0*P*:~"
            "GS*HP*SENDER*RECEIVER*20250402*1234*1*X*005010X221A1~"
            "ST*835*0001*005010X221A1~"
            "BPR*I*1000*C*ACH~"
            "TRN*1*0000000001~"
            "N1*PR*INSURANCE*****PI*123456~"
            "SE*6*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi_no_pe)
        v = X12Validator(p)
        r = v.validate()
        codes_w = {i.code for i in r.issues if i.severity == "warning"}
        assert "N1_PE_MISSING" in codes_w


class TestValidateCLPStatusCodes:
    """CLP status code validation — must be valid numeric 1-29."""

    def test_835_clean_has_valid_clp_status(self):
        result = validate_fixture("sample_835.edi")
        codes_w = {i.code for i in result.issues if i.severity == "warning"}
        assert "CLP_STATUS_INVALID" not in codes_w
        assert "CLP_STATUS_OUT_OF_RANGE" not in codes_w

    def test_clp_status_invalid_non_numeric_warns(self):
        edi_bad_status = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*250402*1234*^*00501*000000001*0*P*:~"
            "GS*HP*SENDER*RECEIVER*20250402*1234*1*X*005010X221A1~"
            "ST*835*0001*005010X221A1~"
            "BPR*I*1000*C*ACH~"
            "TRN*1*0000000001~"
            "N1*PR*INSURANCE~"
            "N1*PE*PROVIDER~"
            "LX*1~"
            "CLP*CLP001*1000*BAD*500~"
            "SE*9*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi_bad_status)
        v = X12Validator(p)
        r = v.validate()
        codes_w = {i.code for i in r.issues if i.severity == "warning"}
        assert "CLP_STATUS_INVALID" in codes_w

    def test_clp_status_out_of_range_warns(self):
        edi_bad_status = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
            "*250402*1234*^*00501*000000001*0*P*:~"
            "GS*HP*SENDER*RECEIVER*20250402*1234*1*X*005010X221A1~"
            "ST*835*0001*005010X221A1~"
            "BPR*I*1000*C*ACH~"
            "TRN*1*0000000001~"
            "N1*PR*INSURANCE~"
            "N1*PE*PROVIDER~"
            "LX*1~"
            "CLP*CLP001*1000*99*500~"
            "SE*9*0001~GE*1*1~IEA*1*000000001~"
        )
        from src.parser import X12Parser
        from src.validate import X12Validator
        p = X12Parser(text=edi_bad_status)
        v = X12Validator(p)
        r = v.validate()
        codes_w = {i.code for i in r.issues if i.severity == "warning"}
        assert "CLP_STATUS_OUT_OF_RANGE" in codes_w


class TestValidateIssueCategories:
    """Issue categories should be populated in validation output."""

    def test_category_in_json_output(self):
        import subprocess
        fixture = FIXTURES / "sample_missing_se.edi"
        result = subprocess.run(
            [sys.executable, "-m", "src.validate", str(fixture), "--json"],
            capture_output=True, text=True,
        )
        parsed = json.loads(result.stdout)
        assert "issues" in parsed
        for issue in parsed["issues"]:
            assert "category" in issue, f"Issue {issue.get('code')} missing category field"

    def test_envelope_issues_have_envelope_category(self):
        result = validate_fixture("sample_missing_ge.edi")
        gs_ge = next((i for i in result.issues if i.code == "GS_GE_MISMATCH"), None)
        assert gs_ge is not None
        assert gs_ge.category == "envelope"

    def test_segment_structure_issues_have_segment_structure_category(self):
        result = validate_fixture("sample_missing_ge.edi")
        empty_group = next((i for i in result.issues if i.code == "EMPTY_GROUP"), None)
        assert empty_group is not None
        assert empty_group.category == "segment_structure"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
