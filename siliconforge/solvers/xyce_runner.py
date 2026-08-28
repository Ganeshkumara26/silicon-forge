#!/usr/bin/env python3
"""xyce_runner.py — Xyce interface for HBT circuit simulation.

Xyce works for HBT models (npn13G2) but NOT for MOSFETs (sg13_lv_nmos).
Use this for HBT-based circuits (VCOs, dividers, etc.).

Xyce differences from ngspice:
- No .control blocks
- Use .print for output
- Output goes to .cir.prn file (not stdout)
- .measure for scalar extraction
- Different transistor syntax (X device for subcircuits)

Environment:
  WSL (Ubuntu 22.04) + Xyce + IHP SG13G2 PDK at /tmp/ihp_sg13g2
"""

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple


def _wsl_path(windows_path):
    """Convert Windows path to WSL path."""
    p = str(Path(windows_path).absolute())
    p = p.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        return f"/mnt/{drive}{p[2:]}"
    return p


def run_xyce(netlist_path: str, workdir: str = None,
             timeout: int = 120) -> Tuple[str, str, str]:
    """Run Xyce simulation.

    Parameters
    ----------
    netlist_path : str
        Path to SPICE netlist (Windows or WSL format)
    workdir : str
        Working directory (default: netlist parent)
    timeout : int
        Maximum simulation time in seconds

    Returns
    -------
    (stdout, stderr, prn_output) from Xyce
    """
    netlist_abs = Path(netlist_path).absolute()
    netlist_wsl = _wsl_path(netlist_abs)

    if workdir is None:
        workdir = str(netlist_abs.parent)
    workdir_wsl = _wsl_path(workdir)

    # Xyce outputs to <netlist_name>.cir.prn
    prn_file = netlist_abs.stem + ".cir.prn"
    prn_wsl = str(Path(workdir) / prn_file)

    cmd = (
        f"cd '{workdir_wsl}' && Xyce '{netlist_wsl}' 2>&1"
    )

    try:
        result = subprocess.run(
            ["wsl", "bash", "-c", cmd],
            capture_output=True, text=True, timeout=timeout
        )

        # Read .prn output file
        prn_output = ""
        prn_path = Path(workdir) / prn_file
        if prn_path.exists():
            with open(prn_path, "r") as f:
                prn_output = f.read()

        return result.stdout, result.stderr, prn_output
    except subprocess.TimeoutExpired:
        return "", f"Xyce simulation timed out after {timeout}s", ""
    except FileNotFoundError:
        return "", "WSL not found — Xyce must run through WSL on this system", ""


def extract_frequency_from_prn(prn_output: str) -> Optional[float]:
    """Extract frequency from Xyce .prn output file.

    Xyce .prn format has columns with variable names in header.
    """
    if not prn_output:
        return None

    lines = prn_output.strip().split("\n")
    if len(lines) < 3:
        return None

    # Find the time column and voltage column indices
    header = lines[0]
    # Xyce .prn format: "Index\tTIME\tV(...)\t..."
    cols = header.lower().split("\t")

    # Look for frequency-related output or compute from time series
    # For now, look for a "freq" line in the output
    for line in lines:
        if "freq" in line.lower():
            match = re.search(r'([eE\d.+-]+)', line)
            if match:
                try:
                    val = float(match.group(1))
                    if 1e6 < val < 1e13:
                        return val
                except ValueError:
                    continue

    return None


def extract_xyce_measure(prn_output: str, measure_name: str) -> Optional[float]:
    """Extract a .measure value from Xyce output."""
    if not prn_output:
        return None

    # Xyce outputs measure results in a table format
    for line in prn_output.split("\n"):
        if measure_name.lower() in line.lower():
            parts = line.split()
            for p in parts:
                try:
                    return float(p)
                except ValueError:
                    continue
    return None


def run_hbt_vco_simulation(netlist_path: str, workdir: str = None) -> dict:
    """Run an HBT-based VCO simulation in Xyce.

    Parameters
    ----------
    netlist_path : str
        Path to HBT VCO netlist (Xyce format)
    workdir : str
        Working directory

    Returns
    -------
    dict with 'converged', 'frequency_hz', 'vpp', 'raw_output'
    """
    result = {
        "converged": False,
        "frequency_hz": None,
        "vpp": None,
        "raw_output": "",
        "elapsed_s": 0.0,
    }

    t0 = time.time()
    stdout, stderr, prn = run_xyce(netlist_path, workdir=workdir)
    result["elapsed_s"] = time.time() - t0
    result["raw_output"] = prn

    if stderr and "error" in stderr.lower():
        return result

    # Extract frequency from .measure output
    freq = extract_xyce_measure(prn, "freq")
    if freq and 1e6 < freq < 1e13:
        result["frequency_hz"] = freq
        result["converged"] = True

    # Extract VPP
    vpp = extract_xyce_measure(prn, "vpp_pp")
    if vpp and 0 < vpp < 5:
        result["vpp"] = vpp

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Xyce HBT Circuit Runner")
    parser.add_argument("netlist", help="Path to SPICE netlist (Xyce format)")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    r = run_hbt_vco_simulation(args.netlist)
    print(f"Converged: {r['converged']}")
    print(f"Frequency: {r['frequency_hz']}")
    print(f"VPP: {r['vpp']}")
    print(f"Time: {r['elapsed_s']:.1f}s")
