"""test_jitter.py — Tests for canonical jitter calculation."""

import pytest
import numpy as np
from siliconforge.solvers.jitter import (
    integrate_jitter_from_pn_curve,
    integrate_jitter_single_point,
    reconcile_jitter_metrics,
)


class TestJitterIntegration:
    """Test the canonical jitter integration."""

    def test_single_point_matches_legacy(self, sample_pn_curve):
        """Single-point method should match the legacy ppv_jitter.py result."""
        offsets, pn, f0 = sample_pn_curve
        fm = 1e6
        L_fm = -133.74
        result = integrate_jitter_single_point(L_fm, fm, f0, 10e3, 1e9)
        assert result["tie_rms_fs"] > 0
        assert result["tie_rms_fs"] < 1000
        assert result["f0_hz"] == f0
        assert result["fmin_hz"] == 10e3
        assert result["fmax_hz"] == 1e9

    def test_curve_integration_converges(self, sample_pn_curve):
        """Full curve integration should give similar result to single-point for pure 1/f^2."""
        offsets, pn, f0 = sample_pn_curve
        result = integrate_jitter_from_pn_curve(offsets, pn, f0, 10e3, 1e9)
        assert result["tie_rms_fs"] > 0
        assert result["tie_rms_fs"] < 1000
        assert result["num_offset_points"] > 10

    def test_curve_vs_single_point_agreement(self, sample_pn_curve):
        """For pure 1/f^2 noise, both methods should agree within 10%."""
        offsets, pn, f0 = sample_pn_curve
        fm = 1e6
        L_fm = -133.74

        curve_result = integrate_jitter_from_pn_curve(offsets, pn, f0, 10e3, 1e9)
        point_result = integrate_jitter_single_point(L_fm, fm, f0, 10e3, 1e9)

        ratio = curve_result["tie_rms_fs"] / point_result["tie_rms_fs"]
        assert 0.9 < ratio < 1.1, f"Methods disagree: ratio={ratio:.3f}"

    def test_flicker_increases_jitter(self, sample_pn_curve):
        """Adding flicker noise (1/f^3) should increase total jitter."""
        offsets, pn_thermal, f0 = sample_pn_curve
        offsets = np.array(offsets)
        pn_thermal = np.array(pn_thermal)

        # Add flicker: +10 dB/dec below 100 kHz
        flicker_mask = offsets < 100e3
        pn_with_flicker = pn_thermal.copy()
        pn_with_flicker[flicker_mask] += 10 * np.log10(100e3 / offsets[flicker_mask])

        thermal_only = integrate_jitter_from_pn_curve(offsets.tolist(), pn_thermal.tolist(), f0, 10e3, 1e9)
        with_flicker = integrate_jitter_from_pn_curve(offsets.tolist(), pn_with_flicker.tolist(), f0, 10e3, 1e9)

        assert with_flicker["tie_rms_fs"] > thermal_only["tie_rms_fs"]

    def test_integration_bounds_respected(self, sample_pn_curve):
        """Integration should only use data within [fmin, fmax]."""
        offsets, pn, f0 = sample_pn_curve
        result_narrow = integrate_jitter_from_pn_curve(offsets, pn, f0, 100e3, 10e6)
        result_wide = integrate_jitter_from_pn_curve(offsets, pn, f0, 1e3, 1e9)
        assert result_wide["tie_rms_fs"] > result_narrow["tie_rms_fs"]

    def test_empty_band_raises(self, sample_pn_curve):
        """Integration with no data points in band should raise ValueError."""
        offsets, pn, f0 = sample_pn_curve
        with pytest.raises(ValueError):
            integrate_jitter_from_pn_curve(offsets, pn, f0, 1e12, 1e15)

    def test_output_has_required_fields(self, sample_pn_curve):
        """Every jitter result must include metadata for traceability."""
        offsets, pn, f0 = sample_pn_curve
        result = integrate_jitter_from_pn_curve(offsets, pn, f0, 10e3, 1e9)
        required = ["tie_rms_s", "tie_rms_fs", "phi_rms_rad", "phi_rms_deg",
                    "f0_hz", "fmin_hz", "fmax_hz", "convention", "period_pct"]
        for field in required:
            assert field in result, f"Missing required field: {field}"


class TestReconciliation:
    """Test the 45fs vs 389fs reconciliation."""

    def test_pure_thermal_ratio_is_unity(self, sample_pn_curve):
        """For pure 1/f^2 noise, curve/point ratio should be ~1."""
        offsets, pn, f0 = sample_pn_curve
        fm = 1e6
        L_fm = -133.74
        curve = integrate_jitter_from_pn_curve(offsets, pn, f0, 10e3, 1e9)
        point = integrate_jitter_single_point(L_fm, fm, f0, 10e3, 1e9)
        recon = reconcile_jitter_metrics(curve, point)
        assert recon["ratio_curve_to_point"] < 1.2
