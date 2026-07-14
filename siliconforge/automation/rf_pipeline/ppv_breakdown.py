#!/usr/bin/env python3
"""ppv_breakdown.py -- PNOISE Engine via Hajimiri Integral (v2.0)

Computes the total phase noise L(f_m) and generates a node-by-node breakdown
using the extracted PPV (ISF). Now includes:
  - Explicit Gamma_dc audit for flicker noise upconversion susceptibility
  - 1/f^3 analytical slope alongside the 1/f^2 curve
  - Multi-offset frequency sweep for full L(f) plot generation
"""

import os
import sys
import json
import argparse
import numpy as np
import matplotlib.pyplot as plt


def compute_node_noise(node_name, ppv_array, params, fm):
    """
    Computes Phase Noise contribution for a single node using Hajimiri Integral.
    Returns separate thermal (1/f^2) and flicker (1/f^3) contributions.
    """
    ppv = np.array([p for p in ppv_array if p is not None])
    if len(ppv) == 0:
        return None

    # Core ISF metrics
    ppv_rms2 = np.mean(ppv**2)
    ppv_dc = np.mean(ppv)  # Gamma_dc — the flicker upconversion coefficient
    ppv_dc2 = ppv_dc**2
    ppv_rms = np.sqrt(ppv_rms2)

    # Physical constants
    k_B = 1.38e-23
    T = 300  # Kelvin

    omega_m = 2 * np.pi * fm
    denominator = 2 * (omega_m**2)

    # Device noise parameters (from device_params or IHP defaults)
    gm = params.get(node_name, {}).get("gm", 20e-3)
    gamma = params.get(node_name, {}).get("gamma", 2.0 / 3.0)
    KF = params.get(node_name, {}).get("KF", 1e-24)
    AF = params.get(node_name, {}).get("AF", 1.2)
    Id = params.get(node_name, {}).get("Id", 2e-3)
    Cox = params.get(node_name, {}).get("Cox", 10e-3)
    W = params.get(node_name, {}).get("W", 20e-6)
    L = params.get(node_name, {}).get("L", 0.13e-6)
    # Thermal Noise Current PSD (White → 1/f^2 phase noise)
    # -----------------------------------------------------------
    # TIER 4 CYCLOSTATIONARY UPGRADE: If Vgs(t) is available, use time-varying g_m(t)
    # else fallback to stationary assumption.
    Vgs_t = None
    if "pss_data" in params and params["pss_data"] is not None:
        pss = params["pss_data"]
        # Assuming typical cross-coupled LC: out_p is driven by M_n whose gate is out_n and source is tail
        gate_node = "out_n" if node_name == "out_p" else "out_p" if node_name == "out_n" else None
        source_node = "tail"

        if gate_node in pss.get("nodes", {}) and source_node in pss.get("nodes", {}):
            vg = np.array(pss["nodes"][gate_node]["voltage"])
            vs = np.array(pss["nodes"][source_node]["voltage"])
            # Interpolate to match PPV array length if necessary (PPV might be downsampled)
            # For simplicity, if lengths don't match exactly, we fallback to mean
            if len(vg) == len(ppv):
                Vgs_t = vg - vs
            else:
                # Downsample PSS to match PPV
                idx = np.linspace(0, len(vg)-1, len(ppv)).astype(int)
                Vgs_t = vg[idx] - vs[idx]

    if Vgs_t is not None:
        # Simplified Level 1/EKV g_m(t)
        Vth = 0.4  # Approx threshold
        # 0.05 = approx mobility term
        gm_t = np.maximum(0, (Cox * W / L) * 0.05 * (Vgs_t - Vth))
        S_i_thermal = 4 * k_B * T * gamma * gm_t
        # Integrated cyclostationary noise: mean(PPV(t)^2 * S_i_thermal(t))
        pn_thermal_lin = np.mean(ppv**2 * S_i_thermal) / denominator
    else:
        # Stationary fallback
        S_i_thermal = 4 * k_B * T * gamma * gm
        pn_thermal_lin = (ppv_rms2 * S_i_thermal) / denominator

    # Flicker Noise Current PSD (1/f → 1/f^3 phase noise)
    S_i_flicker_at_1hz = (KF * (Id**AF)) / (Cox * W *
                                            L) if (Cox * W * L) > 0 else 0

    # 1/f^2 contribution (thermal, white noise upconversion via PPV_rms)
    pn_thermal_lin = (ppv_rms2 * S_i_thermal) / denominator

    # 1/f^3 contribution (flicker noise upconversion via PPV_dc)
    pn_flicker_lin = (ppv_dc2 * S_i_flicker_at_1hz / fm) / \
        denominator if fm > 0 else 0

    pn_total_lin = pn_thermal_lin + pn_flicker_lin
    pn_db = 10 * np.log10(pn_total_lin) if pn_total_lin > 1e-30 else -300

    return {
        "node": node_name,
        "thermal_lin": pn_thermal_lin,
        "flicker_lin": pn_flicker_lin,
        "total_lin": pn_total_lin,
        "total_db": pn_db,
        "ppv_rms": ppv_rms,
        "ppv_dc": ppv_dc,
        "gamma_dc_ratio": abs(ppv_dc) / (ppv_rms + 1e-30)
    }


def main():
    parser = argparse.ArgumentParser(
        description="PNOISE Engine via Hajimiri Integral (v2.0)")
    parser.add_argument("--input", type=str, required=True,
                        help="Input PPV JSON file")
    parser.add_argument("--device-params", type=str,
                        default=None, help="JSON file with noise parameters")
    parser.add_argument("--offset", type=float, default=1e6,
                        help="Phase noise offset frequency (Hz)")
    parser.add_argument("--pss", type=str, default="pss_solution.json",
                        help="Path to steady-state voltage data for cyclostationary noise")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[ERROR] Could not find input file: {args.input}")
        sys.exit(1)

    with open(args.input, "r") as f:
        ppv_data = json.load(f)

    params = {}
    if args.device_params and os.path.exists(args.device_params):
        with open(args.device_params, "r") as f:
            params = json.load(f)
    else:
        print(
            "[PNOISE] No device parameters provided. Using default IHP 130nm approximations.")

    if os.path.exists(args.pss):
        with open(args.pss, "r") as f:
            params["pss_data"] = json.load(f)
        print(
            "[PNOISE] Loaded PSS steady-state data for cyclostationary noise calculation.")
    else:
        params["pss_data"] = None
        print("[PNOISE] No PSS data found. Falling back to stationary noise assumption.")

    fm = args.offset
    print(
        f"[PNOISE] Calculating Phase Noise Breakdown at offset {fm/1e6:.1f} MHz")

    nodes_data = ppv_data.get("nodes", {})
    breakdown = []
    total_lin = 0

    # === Gamma_dc Audit ===
    print("\n" + "="*70)
    print(" GAMMA_DC FLICKER NOISE UPCONVERSION AUDIT")
    print("="*70)

    for node, data in nodes_data.items():
        ppv_array = data.get("ppv", [])
        if not ppv_array:
            continue

        result = compute_node_noise(node, ppv_array, params, fm)
        if result is None:
            continue

        breakdown.append(result)
        total_lin += result["total_lin"]

        # Gamma_dc diagnostic
        ratio = result["gamma_dc_ratio"]
        status = "⚠️  HIGH" if ratio > 0.01 else "✅ LOW"
        print(f"  {node:<15} | Γ_dc/Γ_rms = {ratio:.6f} | {status}")

    print("="*70)

    if any(r["gamma_dc_ratio"] > 0.01 for r in breakdown):
        print("[WARNING] One or more nodes have high Γ_dc — the circuit is susceptible")
        print("         to 1/f flicker noise upconversion into 1/f^3 phase noise.")
        print("         Consider rebalancing transistor sizing or adding tail filtering.\n")
    else:
        print("[INFO] All nodes show good flicker noise rejection (low Γ_dc).\n")

    # Sort breakdown by noise contribution (highest first)
    breakdown.sort(key=lambda x: x["total_lin"], reverse=True)

    total_db = 10 * np.log10(total_lin) if total_lin > 1e-30 else -300

    print("="*70)
    print(f" TOTAL PHASE NOISE @ {fm/1e6:.1f} MHz:  {total_db:.2f} dBc/Hz")
    print("="*70)
    print(f" {'Node':<15} | {'Dominance':<10} | {'PN (dBc/Hz)':<15} | {'Contrib %':<10} | {'Γ_dc/Γ_rms':<12}")
    print("-" * 70)

    for res in breakdown:
        pct = (res["total_lin"] / total_lin) * 100 if total_lin > 0 else 0
        dom = "Thermal" if res["thermal_lin"] > res["flicker_lin"] else "Flicker"
        print(
            f" {res['node']:<15} | {dom:<10} | {res['total_db']:<15.2f} | {pct:>8.1f} % | {res['gamma_dc_ratio']:.6f}")
    print("="*70 + "\n")

    # === Generate L(f) Sweep Plot (1/f^2 + 1/f^3 slopes) ===
    offsets = np.logspace(3, 9, 200)  # 1kHz to 1GHz
    total_pn_curve = np.zeros_like(offsets)
    thermal_curve = np.zeros_like(offsets)
    flicker_curve = np.zeros_like(offsets)

    for node, data in nodes_data.items():
        ppv_array = data.get("ppv", [])
        if not ppv_array:
            continue
        for j, fm_j in enumerate(offsets):
            r = compute_node_noise(node, ppv_array, params, fm_j)
            if r:
                total_pn_curve[j] += r["total_lin"]
                thermal_curve[j] += r["thermal_lin"]
                flicker_curve[j] += r["flicker_lin"]

    total_pn_db = 10 * np.log10(np.maximum(total_pn_curve, 1e-30))
    thermal_db = 10 * np.log10(np.maximum(thermal_curve, 1e-30))
    flicker_db = 10 * np.log10(np.maximum(flicker_curve, 1e-30))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # L(f) plot
    ax1.semilogx(offsets, total_pn_db, 'k-', linewidth=2, label="Total L(f)")
    ax1.semilogx(offsets, thermal_db, 'b--',
                 linewidth=1.5, label="1/f² (Thermal)")
    ax1.semilogx(offsets, flicker_db, 'r--',
                 linewidth=1.5, label="1/f³ (Flicker)")
    ax1.set_xlabel("Offset Frequency (Hz)")
    ax1.set_ylabel("Phase Noise L(f) [dBc/Hz]")
    ax1.set_title("Phase Noise Spectrum (Hajimiri Integral)")
    ax1.legend()
    ax1.grid(True, which="both", alpha=0.3)
    ax1.set_xlim([1e3, 1e9])

    # Pie chart
    labels = [res["node"] for res in breakdown]
    sizes = [res["total_lin"] for res in breakdown]
    ax2.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140,
            colors=plt.cm.tab10.colors[:len(labels)])
    ax2.set_title(
        f"Node Contribution @ {args.offset/1e6:.1f} MHz\nTotal: {total_db:.2f} dBc/Hz")
    ax2.axis('equal')

    plt.tight_layout()

    plot_path = "phase_noise_breakdown.png"
    plt.savefig(plot_path, dpi=150)
    plt.close()

    # Export JSON
    out_json = {
        "f_offset": args.offset,
        "total_phase_noise_dbc_hz": total_db,
        "breakdown": breakdown
    }
    with open("phase_noise_breakdown.json", "w") as f:
        json.dump(out_json, f, indent=4)

    print(f"[PNOISE] Saved results to phase_noise_breakdown.json")
    print(f"[PNOISE] Generated L(f) sweep plot with 1/f² + 1/f³ slopes.")


if __name__ == "__main__":
    main()
