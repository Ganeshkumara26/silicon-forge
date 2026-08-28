#!/usr/bin/env python3
"""generate_coverage.py — Statistical Coverage Generator

Fixed version (was SF-001: mock data, SF-016: voltage sampled as frequency).

Two modes:
  1. REAL: Ingests actual Monte Carlo SPICE simulation results from JSON files
  2. ANALYTICAL: Uses physics-based estimates (clearly labeled, never claimed as real)

The output covergroup bins frequencies in Hz (not voltage).
"""

import os
import sys
import json
import math
import glob
import numpy as np
from jinja2 import Environment, FileSystemLoader


def ingest_real_monte_carlo_results(results_dir):
    """Ingest real frequency measurements from SPICE simulation results.

    Looks for JSON files in results_dir that contain frequency measurements.
    Expected format per file: {"frequency_hz": <float>, ...} or {"f0_hz": <float>, ...}

    Returns (frequencies, source_description) or (None, error_message).
    """
    if not os.path.isdir(results_dir):
        return None, f"Results directory not found: {results_dir}"

    json_files = sorted(glob.glob(os.path.join(results_dir, "*.json")))
    if not json_files:
        return None, f"No JSON result files found in {results_dir}"

    frequencies = []
    for jf in json_files:
        try:
            with open(jf) as f:
                data = json.load(f)
            freq = None
            for key in ["frequency_hz", "f0_hz", "frequency", "f0", "measured_freq_hz"]:
                if key in data:
                    freq = float(data[key])
                    break
            if freq is not None and freq > 0:
                frequencies.append(freq)
        except (json.JSONDecodeError, ValueError):
            continue

    if not frequencies:
        return None, "No valid frequency measurements found in JSON files"

    source = f"Real Monte Carlo SPICE results: {len(frequencies)} samples from {results_dir}"
    return frequencies, source


def generate_analytical_estimate(f0_nominal, process_sigma_pct=2.5, num_samples=100):
    """Generate analytical frequency spread estimate from process parameters.

    Uses known process variation to estimate frequency spread.
    Clearly labeled as analytical — never presented as measured data.
    """
    sigma = f0_nominal * (process_sigma_pct / 100.0)
    rng = np.random.default_rng(seed=42)
    frequencies = rng.normal(f0_nominal, sigma, num_samples).tolist()
    source = (
        f"ANALYTICAL ESTIMATE (not measured): f0={f0_nominal/1e9:.4f} GHz, "
        f"process sigma={process_sigma_pct}%, N={num_samples}"
    )
    return frequencies, source


def calculate_statistics(data):
    """Calculate mean and sample standard deviation."""
    arr = np.asarray(data, dtype=float)
    return float(arr.mean()), float(arr.std(ddof=1))


def generate_3sigma_bins(mean, sigma):
    """Generate discrete floating-point boundaries for +/- 3 sigma bins."""
    bins = [
        {"name": "sub_3sigma", "lower_bound": mean - 3 * sigma, "upper_bound": mean - 2 * sigma},
        {"name": "sub_2sigma", "lower_bound": mean - 2 * sigma, "upper_bound": mean - 1 * sigma},
        {"name": "sub_1sigma", "lower_bound": mean - 1 * sigma, "upper_bound": mean},
        {"name": "plus_1sigma", "lower_bound": mean, "upper_bound": mean + 1 * sigma},
        {"name": "plus_2sigma", "lower_bound": mean + 1 * sigma, "upper_bound": mean + 2 * sigma},
        {"name": "plus_3sigma", "lower_bound": mean + 2 * sigma, "upper_bound": mean + 3 * sigma},
        {"name": "out_of_spec", "lower_bound": 0, "upper_bound": mean - 3 * sigma},
    ]
    return bins


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Statistical Coverage Generator (fixed)")
    parser.add_argument("--results-dir", type=str, default=None,
                        help="Directory with real SPICE Monte Carlo JSON results")
    parser.add_argument("--f0-nominal", type=float, default=10.25e9,
                        help="Nominal frequency for analytical fallback [Hz]")
    parser.add_argument("--process-sigma", type=float, default=2.5,
                        help="Process variation sigma [%] for analytical fallback")
    parser.add_argument("--require-real", action="store_true",
                        help="Fail if no real SPICE results are available (no analytical fallback)")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(base_dir, 'templates')
    out_dir = os.path.join(os.path.dirname(base_dir), '..', 'uvm_verification')

    os.makedirs(out_dir, exist_ok=True)

    # 1. Try to ingest real data
    raw_f0_data = None
    source_desc = ""

    if args.results_dir:
        raw_f0_data, source_desc = ingest_real_monte_carlo_results(args.results_dir)

    if raw_f0_data is None:
        if args.require_real:
            print(f"[ERROR] --require-real specified but no real SPICE results found.")
            print(f"[ERROR] Reason: {source_desc}")
            print(f"[ERROR] Run SPICE Monte Carlo simulations first, or omit --require-real.")
            sys.exit(1)
        print(f"[COVERAGE] No real simulation data available.")
        print(f"[COVERAGE] Reason: {source_desc}")
        print(f"[COVERAGE] Falling back to analytical estimate (NOT REAL DATA).")
        raw_f0_data, source_desc = generate_analytical_estimate(
            args.f0_nominal, args.process_sigma
        )
        is_real_data = False
    else:
        print(f"[COVERAGE] Ingested {len(raw_f0_data)} real frequency measurements.")
        print(f"[COVERAGE] Source: {source_desc}")
        is_real_data = True

    # 2. Calculate statistics
    mu, sigma = calculate_statistics(raw_f0_data)
    print(f"[COVERAGE] Statistics: mean={mu/1e9:.6f} GHz, sigma={sigma/1e6:.3f} MHz")

    # 3. Generate bins
    sigma_bins = generate_3sigma_bins(mu, sigma)

    # 4. Render template
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template('uvm_mc_coverage.svh.j2')

    output_sv = template.render(
        source_dataset=source_desc,
        num_samples=len(raw_f0_data),
        mean_hz=int(mu),
        sigma_hz=int(sigma),
        sigma_bins=sigma_bins,
        is_real_data=is_real_data,
    )

    out_path = os.path.join(out_dir, 'vco_coverage.svh')
    with open(out_path, 'w') as f:
        f.write(output_sv)

    print(f"[COVERAGE] Generated: {out_path}")
    print(f"[COVERAGE] Data source: {'REAL measurements' if is_real_data else 'ANALYTICAL estimate'}")


if __name__ == '__main__':
    main()
