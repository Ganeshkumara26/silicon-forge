#!/usr/bin/env python3
"""jitter.py — Canonical Jitter Calculation Engine

Single authoritative definition for all SiliconForge jitter results.

RMS Time Interval Error (TIE) is defined as:

    sigma_t = sqrt( integral_{f_L}^{f_H} S_phi(f) * df ) / (2*pi*f_0)

where:
    S_phi(f) = 2 * 10^(L(f)/10)   [one-sided phase noise PSD, rad^2/Hz]
    L(f)     = single-sideband phase noise [dBc/Hz]
    f_0      = carrier frequency [Hz]
    f_L      = lower integration bound [Hz]
    f_H      = upper integration bound [Hz]

The factor of 2 converts single-sideband L(f) to double-sideband S_phi(f).

Every jitter result produced by SiliconForge MUST include:
    - f_0, f_L, f_H
    - one-sided vs two-sided convention
    - units (seconds and femtoseconds)
    - which noise contributions are included (thermal, flicker, total)

This prevents the same design from producing multiple apparently
contradictory "jitter" numbers.
"""

import json
import numpy as np


def integrate_jitter_from_pn_curve(offsets_hz, pn_dbhz, f0, f_min, f_max):
    """Integrate phase noise L(f) curve to produce RMS TIE jitter.

    Parameters
    ----------
    offsets_hz : array-like
        Offset frequencies where phase noise is known [Hz]
    pn_dbhz : array-like
        Phase noise L(f) at each offset [dBc/Hz]
    f0 : float
        Carrier frequency [Hz]
    f_min : float
        Lower integration bound [Hz]
    f_max : float
        Upper integration bound [Hz]

    Returns
    -------
    dict with keys:
        tie_rms_s : float — RMS TIE in seconds
        tie_rms_fs : float — RMS TIE in femtoseconds
        phi_rms_rad : float — RMS phase jitter in radians
        phi_rms_deg : float — RMS phase jitter in degrees
        f0_hz : float — carrier frequency
        fmin_hz : float — lower integration bound
        fmax_hz : float — upper integration bound
        convention : str — "one-sided L(f) -> double-sideband S_phi(f)"
        period_pct : float — jitter as percentage of carrier period
    """
    offsets = np.asarray(offsets_hz, dtype=float)
    pn = np.asarray(pn_dbhz, dtype=float)

    mask = (offsets >= f_min) & (offsets <= f_max)
    f_band = offsets[mask]
    pn_band = pn[mask]

    if len(f_band) < 2:
        raise ValueError(
            f"Integration band [{f_min}, {f_max}] Hz contains fewer than "
            f"2 data points from the provided curve (offsets range: "
            f"{offsets.min():.1e} to {offsets.max():.1e} Hz)."
        )

    s_phi = 2.0 * 10.0 ** (pn_band / 10.0)

    integral = np.trapezoid(s_phi, f_band)

    phi_rms = np.sqrt(integral)
    tie_rms = phi_rms / (2.0 * np.pi * f0)

    T0 = 1.0 / f0

    return {
        "tie_rms_s": float(tie_rms),
        "tie_rms_fs": float(tie_rms * 1e15),
        "phi_rms_rad": float(phi_rms),
        "phi_rms_deg": float(phi_rms * 180.0 / np.pi),
        "f0_hz": float(f0),
        "fmin_hz": float(f_min),
        "fmax_hz": float(f_max),
        "convention": "one-sided L(f) -> double-sideband S_phi(f), factor 2",
        "period_pct": float(tie_rms / T0 * 100.0),
        "num_offset_points": int(len(f_band)),
    }


def integrate_jitter_single_point(pn_dbhz, f_offset, f0, f_min, f_max):
    """Single-point analytical jitter assuming pure 1/f^2 (thermal) slope.

    This is the legacy method used by ppv_jitter.py. It assumes:
        S_phi(f) = S_phi(f_offset) * (f_offset / f)^2

    Included for backward compatibility and cross-checking.
    """
    s_phi_fm = 10.0 ** (pn_dbhz / 10.0)
    integral = 2.0 * s_phi_fm * (f_offset ** 2) * (1.0 / f_min - 1.0 / f_max)
    phi_rms = np.sqrt(integral)
    tie_rms = phi_rms / (2.0 * np.pi * f0)
    T0 = 1.0 / f0

    return {
        "tie_rms_s": float(tie_rms),
        "tie_rms_fs": float(tie_rms * 1e15),
        "phi_rms_rad": float(phi_rms),
        "phi_rms_deg": float(phi_rms * 180.0 / np.pi),
        "f0_hz": float(f0),
        "fmin_hz": float(f_min),
        "fmax_hz": float(f_max),
        "convention": "one-sided L(f), pure 1/f^2 analytical integration",
        "period_pct": float(tie_rms / T0 * 100.0),
        "reference_offset_hz": float(f_offset),
    }


def reconcile_jitter_metrics(curve_result, point_result):
    """Compare curve-based and single-point jitter for diagnostic output."""
    ratio = curve_result["tie_rms_fs"] / point_result["tie_rms_fs"]
    return {
        "curve_integration_tie_fs": curve_result["tie_rms_fs"],
        "single_point_1overf2_tie_fs": point_result["tie_rms_fs"],
        "ratio_curve_to_point": float(ratio),
        "interpretation": (
            "Ratio > 1 means flicker/low-offset noise contributes significantly. "
            "Ratio ~= 1 means pure 1/f^2 thermal noise dominates."
            if ratio > 1.5 else
            "Ratio ~= 1 confirms thermal noise dominance; single-point method is adequate."
        ),
    }


def estimate_phase_noise_leeson(f0, offset_hz, Q=10.0, P_mW=5.0,
                                 F=6.0, flicker_corner_hz=100e3):
    """Estimate phase noise using the Leeson model.

    Parameters
    ----------
    f0 : float
        Carrier frequency [Hz]
    offset_hz : float or array-like
        Offset frequency(s) [Hz]
    Q : float
        Tank quality factor (typical 5-15 for LC, 1-3 for ring)
    P_mW : float
        Oscillator core power [mW]
    F : float
        Device noise figure [dB] (typical 3-8 dB)
    flicker_corner_hz : float
        1/f noise corner frequency [Hz]

    Returns
    -------
    offsets : ndarray
        Offset frequencies [Hz]
    pn_dbhz : ndarray
        Estimated phase noise L(f) [dBc/Hz]
    """
    offsets = np.asarray(offset_hz, dtype=float)
    k_B = 1.38e-23
    T = 300.0
    P_W = P_mW * 1e-3
    F_lin = 10.0 ** (F / 10.0)

    # Leeson formula: L(fm) = 10*log1[ (2*k*T*F / P) * (1 + (f0/(2*Q*fm))^2) * (1 + fc/fm) ]
    fm = offsets
    thermal_term = (2.0 * k_B * T * F_lin / P_W)
    resonance_term = 1.0 + (f0 / (2.0 * Q * fm)) ** 2
    flicker_term = 1.0 + flicker_corner_hz / fm

    pn_linear = thermal_term * resonance_term * flicker_term
    pn_dbhz = 10.0 * np.log10(np.maximum(pn_linear, 1e-30))

    return offsets, pn_dbhz


def compute_jitter_from_osc_params(f0, Q=10.0, P_mW=5.0, F=6.0,
                                    flicker_corner_hz=100e3,
                                    fmin=10e3, fmax=None):
    """Compute jitter estimate from oscillator physical parameters.

    Uses the Leeson phase noise model + single-point integration.
    This replaces hardcoded jitter values with physics-based estimates.

    Parameters
    ----------
    f0 : float
        Carrier frequency [Hz]
    Q : float
        Tank quality factor
    P_mW : float
        Core power [mW]
    F : float
        Device noise figure [dB]
    flicker_corner_hz : float
        1/f noise corner [Hz]
    fmin, fmax : float
        Integration bounds [Hz]

    Returns
    -------
    dict with jitter metrics + phase noise metadata
    """
    if fmax is None:
        fmax = f0 / 2.0

    # Estimate phase noise at 1 MHz for single-point integration
    ref_offset = 1e6
    _, pn_at_ref = estimate_phase_noise_leeson(
        f0, np.array([ref_offset]), Q=Q, P_mW=P_mW, F=F,
        flicker_corner_hz=flicker_corner_hz
    )
    pn_1mhz = float(pn_at_ref[0])

    # Compute jitter using single-point method
    result = integrate_jitter_single_point(pn_1mhz, ref_offset, f0, fmin, fmax)
    result["method"] = "leeson_model_estimate"
    result["phase_noise_model"] = {
        "model": "Leeson",
        "Q": Q,
        "P_mW": P_mW,
        "noise_figure_dB": F,
        "flicker_corner_hz": flicker_corner_hz,
        "pn_at_1mhz_dbc_hz": pn_1mhz,
    }
    result["note"] = (
        f"Jitter estimated from Leeson phase noise model "
        f"(Q={Q}, P={P_mW}mW, F={F}dB). "
        f"For accurate value, run 9-stage pipeline with SPICE .noise analysis."
    )
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Canonical Jitter Engine")
    parser.add_argument("--pnoise-curve", type=str, default=None,
                        help="JSON with offsets_hz and pn_dbhz arrays")
    parser.add_argument("--pnoise", type=str, default=None,
                        help="Legacy: single-point phase noise JSON")
    parser.add_argument("--f0", type=float, required=True, help="Carrier frequency [Hz]")
    parser.add_argument("--fmin", type=float, default=10e3, help="Lower bound [Hz]")
    parser.add_argument("--fmax", type=float, default=1e9, help="Upper bound [Hz]")
    args = parser.parse_args()

    result = {}

    if args.pnoise_curve:
        with open(args.pnoise_curve) as f:
            data = json.load(f)
        offsets = data["offsets_hz"]
        pn = data["pn_dbhz"]
        result["curve"] = integrate_jitter_from_pn_curve(
            offsets, pn, args.f0, args.fmin, args.fmax
        )

    if args.pnoise:
        with open(args.pnoise) as f:
            data = json.load(f)
        fm = data.get("f_offset", 1e6)
        L = data.get("total_phase_noise_dbc_hz")
        if L is None:
            print("[ERROR] total_phase_noise_dbc_hz not found")
            return
        result["single_point"] = integrate_jitter_single_point(
            L, fm, args.f0, args.fmin, args.fmax
        )

    if "curve" in result and "single_point" in result:
        result["reconciliation"] = reconcile_jitter_metrics(
            result["curve"], result["single_point"]
        )

    print(json.dumps(result, indent=2))

    with open("jitter_canonical.json", "w") as f:
        json.dump(result, f, indent=2)
    print("\n[jitter] Saved canonical result to jitter_canonical.json")


if __name__ == "__main__":
    main()
