#!/usr/bin/env python3
"""
siliconforge.cli
================

Command-line interface for SiliconForge platform.
"""

from __future__ import annotations
from siliconforge.solvers.pss_shooting import shoot_newton

import argparse
import sys
from pathlib import Path

# Add project root to sys.path if run directly
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SiliconForge Oscillator Toolkit")
    parser.add_argument("netlist", type=str, help="Path to SPICE netlist")
    parser.add_argument("--f0", type=float, default=10.0e9,
                        help="Estimated frequency (Hz)")

    args = parser.parse_args()
    netlist_path = Path(args.netlist)
    if not netlist_path.exists():
        print(f"Error: {netlist_path} not found.")
        return 1

    lines = netlist_path.read_text().splitlines()

    sim = ReferenceOdeBackend()
    try:
        sim.load(lines)
    except Exception as e:
        print(f"Failed to load netlist: {e}")
        return 1

    print(
        f"Loaded netlist with {len(sim.reactive_elements)} reactive elements.")
    print(
        f"Running PSS Shooting-Newton with guess f0 = {args.f0 / 1e9:.3f} GHz...")

    period = 1.0 / args.f0
    try:
        pss_result = shoot_newton(sim, period)
    except Exception as e:
        print(f"Simulation failed: {e}")
        return 1

    if pss_result.converged:
        print(f"PSS Converged in {pss_result.n_iterations} iterations.")
        print(f"Final period: {pss_result.period_s:.4e} s")
        print(f"Actual frequency: {1.0 / pss_result.period_s / 1e9:.4f} GHz")
    else:
        print("PSS failed to converge.")

    return 0 if pss_result.converged else 1


if __name__ == "__main__":
    sys.exit(main())
