#!/usr/bin/env python3
"""ppv_jitter.py -- JITTER Engine

Converts Phase Noise L(f_m) from the PNOISE engine into Time-Domain Jitter 
metrics (RMS Jitter, Time Interval Error) via analytical bandwidth integration.
"""

import os
import sys
import json
import argparse
import numpy as np


def calculate_rms_jitter(L_fm, fm, f0, f_min, f_max):
    """
    Analytically integrates the 20dB/dec phase noise slope across a bandwidth.
    L_fm : Phase noise at offset fm (in dBc/Hz)
    fm   : Offset frequency (Hz)
    f0   : Carrier frequency (Hz)
    f_min, f_max : Integration bandwidth (Hz)

    Returns:
    TIE_rms : RMS Time Interval Error Jitter (in seconds)
    phi_rms : RMS Phase Jitter (in radians)
    """
    # Linear one-sided phase noise at offset fm: L(fm)_linear = 10^(L_fm/10)
    s_phi_linear = 10 ** (L_fm / 10.0)

    # Convert single-sideband L(f) to double-sideband S_phi(f) = 2 * L(f)_linear
    s_phi_dsb = 2.0 * s_phi_linear

    # Assume 1/f^2 slope: S_phi(f) = S_phi(fm) * (fm/f)^2
    # Integral of S_phi(f) df from f_min to f_max:
    # = S_phi_dsb * fm^2 * (1/f_min - 1/f_max)
    integral = s_phi_dsb * (fm ** 2) * (1.0 / f_min - 1.0 / f_max)

    # RMS phase jitter
    phi_rms = np.sqrt(integral)

    # Convert phase jitter to time jitter
    tie_rms = phi_rms / (2 * np.pi * f0)

    return tie_rms, phi_rms


def main():
    parser = argparse.ArgumentParser(
        description="Jitter Engine via Analytical Integration")
    parser.add_argument("--pnoise", type=str, required=True,
                        help="Input phase noise JSON file (e.g. phase_noise_breakdown.json)")
    parser.add_argument("--ppv", type=str, required=True,
                        help="Input PPV JSON file for f0 reference")
    parser.add_argument("--fmin", type=float, default=10e3,
                        help="Integration bandwidth lower bound (Hz)")
    parser.add_argument("--fmax", type=float, default=1e9,
                        help="Integration bandwidth upper bound (Hz)")
    args = parser.parse_args()

    if not os.path.exists(args.pnoise) or not os.path.exists(args.ppv):
        print(f"[ERROR] Required input files not found.")
        sys.exit(1)

    with open(args.ppv, "r") as f:
        ppv_data = json.load(f)

    with open(args.pnoise, "r") as f:
        pnoise_data = json.load(f)

    T0 = ppv_data.get("T0")
    if not T0:
        print("[ERROR] T0 not found in PPV data.")
        sys.exit(1)

    f0 = 1.0 / T0
    fm = pnoise_data.get("f_offset", 1e6)
    L_fm = pnoise_data.get("total_phase_noise_dbc_hz")

    if L_fm is None:
        print("[ERROR] total_phase_noise_dbc_hz not found in PNOISE data.")
        sys.exit(1)

    print(f"[JITTER] Processing Phase Noise Profile:")
    print(f"         f0 = {f0/1e9:.4f} GHz")
    print(f"         L({fm/1e6:.1f}MHz) = {L_fm:.2f} dBc/Hz")
    print(
        f"[JITTER] Integrating from {args.fmin/1e3:.1f} kHz to {args.fmax/1e9:.2f} GHz")

    tie_rms, phi_rms = calculate_rms_jitter(L_fm, fm, f0, args.fmin, args.fmax)

    tie_fs = tie_rms * 1e15
    phi_deg = phi_rms * (180.0 / np.pi)

    print("\n" + "="*50)
    print(f" JITTER METRICS SUMMARY")
    print("="*50)
    print(f" RMS Time Interval Error (TIE) : {tie_fs:.2f} fs")
    print(f" RMS Phase Jitter              : {phi_deg:.4f} degrees")
    print(f" Jitter as % of Period         : {(tie_rms / T0)*100:.4f} %")
    print("="*50 + "\n")

    out_json = {
        "f0_hz": f0,
        "integration_fmin": args.fmin,
        "integration_fmax": args.fmax,
        "tie_rms_fs": tie_fs,
        "phi_rms_deg": phi_deg,
        "period_pct": (tie_rms / T0)*100
    }

    with open("jitter_metrics.json", "w") as f:
        json.dump(out_json, f, indent=4)

    print(f"[JITTER] Saved metrics to jitter_metrics.json")


if __name__ == "__main__":
    main()
