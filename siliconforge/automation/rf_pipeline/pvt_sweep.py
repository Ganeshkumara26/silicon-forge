#!/usr/bin/env python3
"""pvt_sweep.py -- PVT Corner Sweep Automation Engine

Automates the execution of the entire PSS -> PPV -> PNOISE pipeline across
specified Process, Voltage, and Temperature (PVT) corners.
"""

import os
import sys
import json
import argparse
import subprocess
import matplotlib.pyplot as plt


def mutate_netlist(base_lines, corner, temp, vdd, out_path):
    """
    Mutates the baseline SPICE netlist to target a specific PVT corner.
    """
    mutated = []
    for line in base_lines:
        u_line = line.strip().upper()

        # 1. Process Corner (Swap TT/FF/SS in the IHP lib call)
        if u_line.startswith(".LIB") and "CORNERMOSLV.LIB" in u_line:
            # e.g., .lib '/path/to/cornerMOSlv.lib' mos_tt
            parts = line.split()
            new_line = " ".join(parts[:-1]) + f" mos_{corner.lower()}\n"
            mutated.append(new_line)
            continue

        # 2. Voltage Supply (V_SUPPLY VDD 0 DC 1.2)
        if u_line.startswith("V_SUPPLY"):
            parts = line.split()
            # Find the DC value and replace it
            for i, p in enumerate(parts):
                if p.upper() == "DC":
                    parts[i+1] = str(vdd)
                    break
            mutated.append(" ".join(parts) + "\n")
            continue

        mutated.append(line)

    # 3. Temperature Injection
    mutated.append(f"\n.OPTIONS TEMP={temp}\n")

    with open(out_path, "w") as f:
        f.writelines(mutated)


def run_pipeline(netlist, plugin, nodes):
    """
    Runs the PSS, PPV, and PNOISE engines on a specific netlist.
    Note: Bypassing PSS here for the PPV run because PSS diverges 
    frequently on this proxy VCO model without damping. We use standard 
    PPV extraction which uses a transient baseline internally.
    """
    print(f"    -> Running PPV Engine...")
    nodes_str = " ".join(nodes)

    # 1. Run PPV
    cmd_ppv = [sys.executable, "ppv_direct_injection.py",
               "--netlist", netlist, "--mode", "fast", "--plugin", plugin]
    proc_ppv = subprocess.run(cmd_ppv, capture_output=True, text=True)
    if proc_ppv.returncode != 0:
        print(f"      [ERROR] PPV Failed:\n{proc_ppv.stderr}")
        return None

    # 2. Run PNOISE
    print(f"    -> Running PNOISE Engine...")
    cmd_pn = [sys.executable, "ppv_breakdown.py",
              "--input", "ppv_data.json", "--offset", "1e6"]
    proc_pn = subprocess.run(cmd_pn, capture_output=True, text=True)

    if not os.path.exists("phase_noise_breakdown.json"):
        return None

    with open("phase_noise_breakdown.json", "r") as f:
        pnoise = json.load(f)

    with open("ppv_data.json", "r") as f:
        ppv = json.load(f)

    return {
        "f0": 1.0 / ppv["T0"],
        "phase_noise_1mhz": pnoise["total_phase_noise_dbc_hz"]
    }


def main():
    parser = argparse.ArgumentParser(description="PVT Sweep Automation Engine")
    parser.add_argument("--netlist", type=str,
                        required=True, help="Baseline netlist")
    parser.add_argument("--plugin", type=str, required=True,
                        help="Path to Xyce plugin")
    parser.add_argument("--nodes", nargs="+",
                        required=True, help="Nodes to track")
    parser.add_argument("--corners", nargs="+",
                        default=["TT", "FF", "SS"], help="Process corners (e.g. TT FF SS)")
    parser.add_argument("--temps", nargs="+", type=float,
                        default=[-40, 27, 125], help="Temperatures in Celsius")
    parser.add_argument("--vdds", nargs="+", type=float,
                        default=[1.08, 1.2, 1.32], help="Supply voltages (VDD)")
    args = parser.parse_args()

    with open(args.netlist, "r") as f:
        base_lines = f.readlines()

    results = []

    total_runs = len(args.corners) * len(args.temps) * len(args.vdds)
    current_run = 1

    print(f"[PVT] Starting Sweep Grid ({total_runs} combinations)")

    for corner in args.corners:
        for vdd in args.vdds:
            for temp in args.temps:
                print(
                    f"[{current_run}/{total_runs}] Testing PVT: {corner}, {vdd}V, {temp}C")

                # Create unique netlist
                tmp_netlist = f"pvt_{corner}_{vdd}V_{temp}C.cir"
                mutate_netlist(base_lines, corner, temp, vdd, tmp_netlist)

                # Execute
                data = run_pipeline(tmp_netlist, args.plugin, args.nodes)

                if data:
                    res = {
                        "corner": corner,
                        "vdd": vdd,
                        "temp": temp,
                        "f0": data["f0"],
                        "pn_1mhz": data["phase_noise_1mhz"]
                    }
                    results.append(res)
                    print(
                        f"    -> Success: f0 = {data['f0']/1e9:.3f} GHz, PN = {data['phase_noise_1mhz']:.2f} dBc/Hz")
                else:
                    print(f"    -> [FAILED] Skipping data point.")

                current_run += 1

    # Save JSON
    with open("pvt_results.json", "w") as f:
        json.dump(results, f, indent=4)

    print(f"[PVT] Completed sweep. Data saved to pvt_results.json")

    # Generate Summary Plot
    if results:
        plt.figure(figsize=(10, 5))

        # Subplot 1: Frequency Variation
        plt.subplot(1, 2, 1)
        for corner in args.corners:
            temps = [r["temp"]
                     for r in results if r["corner"] == corner and r["vdd"] == 1.2]
            freqs = [r["f0"]/1e9 for r in results if r["corner"]
                     == corner and r["vdd"] == 1.2]
            if temps:
                plt.plot(temps, freqs, 'o-', label=f"{corner} (1.2V)")
        plt.title("Frequency vs Temperature")
        plt.xlabel("Temperature (C)")
        plt.ylabel("Frequency (GHz)")
        plt.legend()
        plt.grid(True)

        # Subplot 2: Phase Noise Variation
        plt.subplot(1, 2, 2)
        for corner in args.corners:
            temps = [r["temp"]
                     for r in results if r["corner"] == corner and r["vdd"] == 1.2]
            pns = [r["pn_1mhz"]
                   for r in results if r["corner"] == corner and r["vdd"] == 1.2]
            if temps:
                plt.plot(temps, pns, 's--', label=f"{corner} (1.2V)")
        plt.title("Phase Noise vs Temperature")
        plt.xlabel("Temperature (C)")
        plt.ylabel("Phase Noise (dBc/Hz)")
        plt.legend()
        plt.grid(True)

        plt.tight_layout()
        plt.savefig(os.path.join(os.environ.get("USERPROFILE", "C:\\"), ".gemini",
                    "antigravity-ide", "brain", "90300897-07a5-4b42-a22c-168f7155fd30", "pvt_summary.png"))
        plt.close()
        print(f"[PVT] Generated pvt_summary.png")


if __name__ == "__main__":
    main()
