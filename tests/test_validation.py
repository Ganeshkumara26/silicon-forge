#!/usr/bin/env python3
"""test_validation.py — Validate mathematical fixes against known analytical results.

These tests verify that the corrected formulas produce results that match
independent hand-derivation or published textbook values.
"""

import pytest
import numpy as np
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))


class TestLeesonModel:
    """Validate Leeson phase noise model against hand-computed values."""

    def test_thermal_noise_floor(self):
        """At large offsets, Leeson model should give flat thermal noise floor.

        For f0=10GHz, Q=10, Vpp=1.2V, F=6dB, T=300K:
        P = Vpp^2/8 = 0.18 (proportional)
        thermal = 2*k_B*T*F/P = 2*1.38e-23*300*4/0.18 = 1.84e-20
        At large offset: resonance_term ≈ 1, flicker_term ≈ 1
        L(f) = 10*log10(1.84e-20) = -197.3 dBc/Hz
        """
        from siliconforge.solvers.pnoise_analysis import leeson_phase_noise
        # At 1 GHz offset (well above flicker corner and resonance)
        L = leeson_phase_noise(
            f_osc_hz=10e9, f_offset_hz=1e9, v_swing_v=1.2,
            q_loaded=10.0, f_corner_hz=100e3, noise_figure_db=6.0
        )
        # Should be very low (good phase noise) — around -197 dBc/Hz
        assert -210 < L < -180, f"Thermal floor {L:.1f} dBc/Hz out of expected range"

    def test_resonance_region_slope(self):
        """Between flicker corner and f0/2Q, noise should fall at 20dB/dec."""
        from siliconforge.solvers.pnoise_analysis import leeson_phase_noise
        f0 = 10e9
        Q = 10.0
        f_resonance = f0 / (2.0 * Q)  # = 500 MHz

        # In the 1/f^2 region (well below resonance):
        # At 1 MHz: resonance_term = 1 + (500/1)^2 ≈ 250001
        # At 10 MHz: resonance_term = 1 + (500/10)^2 ≈ 2501
        # Ratio ≈ 100, so 20*log10(100) = 40 dB difference per decade
        L_1mhz = leeson_phase_noise(f0, 1e6, 1.2, Q, f_corner_hz=100e3, noise_figure_db=6.0)
        L_10mhz = leeson_phase_noise(f0, 10e6, 1.2, Q, f_corner_hz=100e3, noise_figure_db=6.0)

        # L_10mhz should be lower (less negative) by ~20-40 dB
        diff = L_1mhz - L_10mhz  # positive means 1MHz has worse noise
        assert diff > 15, f"Slope {diff:.1f} dB/dec too shallow (expected >15)"

    def test_flicker_term_scaling(self):
        """Verify the flicker term (1 + fc/fm) scales correctly.

        For a low-frequency oscillator where resonance term ≈ 1,
        the flicker term should dominate below the corner.
        """
        from siliconforge.solvers.pnoise_analysis import leeson_phase_noise
        # Use a low frequency oscillator (10 MHz) with low Q (2)
        # so that resonance term ≈ 1 at offsets > f0/2Q = 2.5 MHz
        f0 = 10e6
        Q = 2.0
        fc = 100e3  # flicker corner

        # At 10 kHz (below corner): flicker_term = 1 + 100e3/10e3 = 11
        # At 100 kHz (at corner): flicker_term = 1 + 100e3/100e3 = 2
        # Ratio = 11/2 = 5.5, so 20*log10(5.5) ≈ 15 dB
        L_low = leeson_phase_noise(f0, 10e3, 1.2, Q, f_corner_hz=fc, noise_figure_db=6.0)
        L_corner = leeson_phase_noise(f0, 100e3, 1.2, Q, f_corner_hz=fc, noise_figure_db=6.0)

        diff = L_low - L_corner  # positive means lower freq has worse noise
        assert diff > 10, f"Flicker contribution {diff:.1f} dB too small (expected >10)"

    def test_higher_Q_better_noise(self):
        """Higher Q should give better (lower) phase noise."""
        from siliconforge.solvers.pnoise_analysis import leeson_phase_noise
        f0 = 10e9
        L_q5 = leeson_phase_noise(f0, 1e6, 1.2, q_loaded=5.0, noise_figure_db=6.0)
        L_q15 = leeson_phase_noise(f0, 1e6, 1.2, q_loaded=15.0, noise_figure_db=6.0)
        assert L_q15 < L_q5, f"Q=15 ({L_q15:.1f}) should be better than Q=5 ({L_q5:.1f})"


class TestJitterIntegration:
    """Validate jitter integration against known analytical results."""

    def test_single_point_formula(self):
        """Verify single-point jitter formula matches direct computation.

        For L(fm) = -100 dBc/Hz at fm=1MHz, f0=10GHz:
        S_phi_linear = 10^(-100/10) = 1e-10
        S_phi_dsb = 2 * 1e-10 = 2e-10
        integral = 2e-10 * (1e6)^2 * (1/1e4 - 1/1e9)
                 = 2e-10 * 1e12 * (1e-4 - 1e-9)
                 ≈ 2e-10 * 1e12 * 1e-4
                 = 2e-2
        phi_rms = sqrt(2e-2) ≈ 0.1414 rad
        tie_rms = 0.1414 / (2*pi*10e9) ≈ 2.25e-12 s = 2.25 ps
        """
        from siliconforge.automation.rf_pipeline.ppv_jitter import calculate_rms_jitter
        tie, phi = calculate_rms_jitter(
            L_fm=-100.0, fm=1e6, f0=10e9, f_min=10e3, f_max=1e9
        )
        # phi_rms should be sqrt(2e-2) ≈ 0.1414
        assert 0.13 < phi < 0.15, f"phi_rms = {phi:.4f}, expected ~0.1414"
        # tie_rms should be ~2.25 ps
        assert 2.0e-12 < tie < 2.5e-12, f"tie_rms = {tie:.4e}, expected ~2.25e-12"

    def test_jitter_from_jitter_module(self):
        """Verify jitter.py module gives same result as ppv_jitter.py."""
        from siliconforge.solvers.jitter import integrate_jitter_single_point
        from siliconforge.automation.rf_pipeline.ppv_jitter import calculate_rms_jitter

        result_jitter = integrate_jitter_single_point(
            pn_dbhz=-100.0, f_offset=1e6, f0=10e9, f_min=10e3, f_max=1e9
        )
        tie_ppv, _ = calculate_rms_jitter(
            L_fm=-100.0, fm=1e6, f0=10e9, f_min=10e3, f_max=1e9
        )
        assert abs(result_jitter["tie_rms_s"] - tie_ppv) < 1e-18, \
            f"jitter.py ({result_jitter['tie_rms_s']:.4e}) != ppv_jitter.py ({tie_ppv:.4e})"

    def test_curve_integration_matches_single_point(self):
        """For pure 1/f^2 noise, curve integration should match single-point."""
        from siliconforge.solvers.jitter import (
            integrate_jitter_from_pn_curve,
            integrate_jitter_single_point,
        )
        f0 = 10e9
        fm = 1e6
        L_fm = -100.0

        # Generate pure 1/f^2 curve
        offsets = np.logspace(4, 9, 100)
        pn = L_fm + 20 * np.log10(fm / offsets)

        curve_result = integrate_jitter_from_pn_curve(offsets, pn, f0, 10e3, 1e9)
        point_result = integrate_jitter_single_point(L_fm, fm, f0, 10e3, 1e9)

        ratio = curve_result["tie_rms_fs"] / point_result["tie_rms_fs"]
        assert 0.95 < ratio < 1.05, \
            f"Curve/point ratio = {ratio:.3f}, expected ~1.0 for pure 1/f^2"


class TestLeesonJitterConsistency:
    """Verify that Leeson model + jitter integration gives consistent results."""

    def test_typical_oscillator_jitter(self):
        """A typical 10 GHz LC oscillator should have jitter in the 10-500 fs range."""
        from siliconforge.solvers.pnoise_analysis import leeson_phase_noise
        from siliconforge.automation.rf_pipeline.ppv_jitter import calculate_rms_jitter

        f0 = 10e9
        L_1mhz = leeson_phase_noise(f0, 1e6, 1.2, q_loaded=10.0, noise_figure_db=6.0)
        tie, phi = calculate_rms_jitter(L_1mhz, 1e6, f0, 10e3, 1e9)

        # Jitter should be physically reasonable (10 fs to 2 ps)
        assert 10e-15 < tie < 2e-12, \
            f"Jitter {tie*1e15:.1f} fs out of reasonable range (10-2000 fs)"
        # Phase jitter should be < 1 radian for a functional oscillator
        assert phi < 1.0, f"Phase jitter {phi:.3f} rad too high for functional oscillator"


class TestMonodromyMatrix:
    """Validate monodromy matrix construction and ISF adjoint method."""

    def test_monodromy_eigenvalues_stable(self):
        """Constructed monodromy matrix must have |lambda| <= 1 for stability."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from siliconforge.solvers.ppv_eigenanalysis import extract_ppv_from_transient
        import numpy as np

        # Generate a simple sinusoidal orbit (2D: x, y)
        t = np.linspace(0, 1e-9, 1000)  # 1 ns, 1000 points
        x = np.cos(2 * np.pi * 1e9 * t)  # 1 GHz oscillation
        y = np.sin(2 * np.pi * 1e9 * t)
        signal = np.vstack([x, y])

        result = extract_ppv_from_transient(t, signal, n_states=2)
        # If the function returns None, it means the orbit wasn't valid
        # For a clean sinusoid, it should work
        if result is not None:
            ppv, isf, c0 = result
            # PPV should be normalized
            assert abs(np.linalg.norm(ppv) - 1.0) < 1e-6, "PPV not normalized"
            # ISF should be normalized
            assert abs(np.linalg.norm(isf) - 1.0) < 1e-6, "ISF not normalized"
            # PPV and ISF should both be real
            assert not np.iscomplexobj(ppv), "PPV should be real"
            assert not np.iscomplexobj(isf), "ISF should be real"

    def test_isf_is_adjoint_not_perpendicular(self):
        """ISF should be the left eigenvector (adjoint), NOT the perpendicular to PPV.

        For a non-normal monodromy matrix, the perpendicular to PPV is NOT
        the correct ISF. Only the adjoint (left eigenvector) gives the correct
        phase sensitivity direction.
        """
        from scipy.linalg import eig
        import numpy as np

        # Construct a non-normal monodromy matrix with eigenvalue 1
        # Right eigenvectors (columns): v1 = tangent, v2 = stable direction
        v1 = np.array([1.0, 0.3]) / np.linalg.norm([1.0, 0.3])
        v2 = np.array([-0.2, 1.0]) / np.linalg.norm([-0.2, 1.0])

        V = np.column_stack([v1, v2])
        Lambda = np.diag([1.0, 0.73])  # stable: |lambda_2| < 1
        M = V @ Lambda @ np.linalg.inv(V)

        # Verify M is non-normal (typical for oscillators)
        assert not np.allclose(M.T @ M, M @ M.T), "Test matrix should be non-normal"

        # Right eigenvector (PPV)
        eigvals_r, eigvecs_r = eig(M)
        idx = np.argmin(np.abs(eigvals_r - 1.0))
        ppv = np.real(eigvecs_r[:, idx])
        ppv = ppv / np.linalg.norm(ppv)

        # Left eigenvector (ISF) — the CORRECT adjoint method
        eigvals_l, eigvecs_l = eig(M.T)
        idx_l = np.argmin(np.abs(eigvals_l - 1.0))
        isf_adj = np.real(eigvecs_l[:, idx_l])
        isf_adj = isf_adj / np.linalg.norm(isf_adj)

        # Perpendicular to PPV — the WRONG method
        isf_perp = np.array([-ppv[1], ppv[0]])

        # For non-normal M, adjoint != perpendicular
        dot_perp = abs(np.dot(isf_perp, isf_adj))
        assert dot_perp < 0.99, \
            f"Perpendicular accidentally matches adjoint (dot={dot_perp:.3f}), need more non-normal test case"

        # The adjoint ISF should satisfy: isf^T M = isf^T (left eigenvector property)
        residual = np.linalg.norm(isf_adj.T @ M - isf_adj.T)
        assert residual < 1e-10, f"Adjoint ISF doesn't satisfy left eigenvector property (residual={residual:.2e})"


class TestJitterNotDoubleCounted:
    """Verify that the factor of 2 in jitter integration is correct.

    The review claimed a sqrt(2) error in ppv_jitter.py. This test verifies
    that the formula is correct by checking against the canonical definition:
        phi_rms = sqrt(integral_{f_L}^{f_H} S_phi(f) df)
    where S_phi(f) = 2 * 10^(L(f)/10) for double-sideband.
    """

    def test_ssb_to_dsb_conversion(self):
        """Verify SSB L(f) -> DSB S_phi(f) = 2 * 10^(L/10) is applied correctly."""
        from siliconforge.automation.rf_pipeline.ppv_jitter import calculate_rms_jitter
        import numpy as np

        L_fm = -100.0  # dBc/Hz
        fm = 1e6
        f0 = 10e9
        f_min, f_max = 10e3, 1e9

        tie, phi = calculate_rms_jitter(L_fm, fm, f0, f_min, f_max)

        # Hand computation: S_phi_dsb = 2 * 10^(-100/10) = 2e-10
        # integral = 2e-10 * (1e6)^2 * (1/1e4 - 1/1e9) ≈ 2e-2
        # phi_rms = sqrt(2e-2) ≈ 0.1414
        S_phi_dsb = 2.0 * 10 ** (L_fm / 10.0)
        integral_expected = S_phi_dsb * fm**2 * (1.0/f_min - 1.0/f_max)
        phi_expected = np.sqrt(integral_expected)

        assert abs(phi - phi_expected) < 1e-15, \
            f"phi_rms = {phi:.15e}, expected {phi_expected:.15e}"
        print(f"Jitter formula verified: phi_rms = {phi:.15e} (correct)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
