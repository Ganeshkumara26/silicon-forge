"""test_schema.py — Tests for canonical result schema."""

import pytest
import json
from siliconforge.solvers.schema import (
    create_result, set_pss_result, set_jitter_result,
    set_phase_noise_result, set_formal_result,
    compute_overall_status, save_result, RESULT_SCHEMA_VERSION,
)


class TestSchema:
    """Test the canonical result schema."""

    def test_create_has_required_fields(self):
        r = create_result("test_vco", "ihp_sg13g2", "ngspice")
        assert r["schema_version"] == RESULT_SCHEMA_VERSION
        assert r["design"]["name"] == "test_vco"
        assert r["design"]["pdk"] == "ihp_sg13g2"
        assert "timestamp" in r

    def test_pss_result_fields(self):
        r = create_result("test", "ihp_sg13g2", "ngspice")
        set_pss_result(r, frequency_hz=10e9, converged=True, iterations=8)
        assert r["pss"]["converged"] is True
        assert r["pss"]["frequency_hz"] == 10e9
        assert r["pss"]["period_s"] == 1e-10

    def test_pss_transient_crosscheck(self):
        r = create_result("test", "ihp_sg13g2", "ngspice")
        set_pss_result(r, frequency_hz=10e9, converged=True, transient_freq=10.001e9)
        tc = r["pss"]["transient_crosscheck"]
        assert tc["performed"] is True
        assert tc["relative_error"] is not None

    def test_jitter_fields(self):
        r = create_result("test", "ihp_sg13g2", "ngspice")
        set_jitter_result(r, 45e-15, 10e9, 10e3, 1e9, "curve", "one-sided")
        assert r["jitter"]["rms_tie_fs"] == pytest.approx(45.0)
        assert r["jitter"]["f0_hz"] == 10e9
        assert r["jitter"]["fmin_hz"] == 10e3
        assert r["jitter"]["fmax_hz"] == 1e9

    def test_overall_pass(self):
        r = create_result("test", "ihp_sg13g2", "ngspice")
        set_pss_result(r, 10e9, True)
        set_formal_result(r, "z3", "PASS", 20, 20)
        status = compute_overall_status(r)
        assert status == "PASS"

    def test_overall_fail_no_convergence(self):
        r = create_result("test", "ihp_sg13g2", "ngspice")
        set_pss_result(r, 0, False)
        status = compute_overall_status(r)
        assert status == "FAIL"

    def test_overall_fail_formal(self):
        r = create_result("test", "ihp_sg13g2", "ngspice")
        set_pss_result(r, 10e9, True)
        set_formal_result(r, "z3", "FAIL")
        status = compute_overall_status(r)
        assert status == "FAIL"

    def test_save_result(self, tmp_path):
        r = create_result("test", "ihp_sg13g2", "ngspice")
        set_pss_result(r, 10e9, True)
        path = str(tmp_path / "result.json")
        status = save_result(r, path)
        assert status == "PASS"
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["design"]["name"] == "test"
