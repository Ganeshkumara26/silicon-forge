import os
import math
import random
from jinja2 import Environment, FileSystemLoader


def ingest_monte_carlo_data(target_mean=10e9, target_sigma=50e6, num_samples=1000):
    """
    Generates synthetic Monte Carlo data analytically for demonstration purposes.
    (In a real physical flow, this would parse Xyce .prn simulation results).
    """
    print(f"Synthesizing Mock Monte Carlo Simulation Data (N={num_samples})...")
    # Simulate the raw extracted frequency points
    raw_data = [random.gauss(target_mean, target_sigma)
                for _ in range(num_samples)]
    return raw_data


def calculate_statistics(data):
    """Calculates mean (mu) and standard deviation (sigma) of the dataset."""
    n = len(data)
    mean = sum(data) / n
    variance = sum((x - mean) ** 2 for x in data) / (n - 1)
    sigma = math.sqrt(variance)
    return mean, sigma


def generate_3sigma_bins(mean, sigma):
    """Generates the discrete floating-point boundaries for +/- 3 sigma bins."""
    bins = [
        {"name": "minus_3_sigma", "lower_bound": mean -
            (3 * sigma), "upper_bound": mean - (2 * sigma)},
        {"name": "minus_2_sigma", "lower_bound": mean -
            (2 * sigma), "upper_bound": mean - (1 * sigma)},
        {"name": "minus_1_sigma", "lower_bound": mean -
            (1 * sigma), "upper_bound": mean},
        {"name": "plus_1_sigma",  "lower_bound": mean,
            "upper_bound": mean + (1 * sigma)},
        {"name": "plus_2_sigma",  "lower_bound": mean +
            (1 * sigma), "upper_bound": mean + (2 * sigma)},
        {"name": "plus_3_sigma",  "lower_bound": mean +
            (2 * sigma), "upper_bound": mean + (3 * sigma)},
    ]

    # Format the floats to integers (in kHz) for SystemVerilog coverpoint compatibility
    for b in bins:
        b["lower_bound"] = f"{int(b['lower_bound'] / 1000.0)}"
        b["upper_bound"] = f"{int(b['upper_bound'] / 1000.0)}"

    return bins


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(base_dir, 'templates')
    out_dir = os.path.join(os.path.dirname(base_dir), '..', 'uvm_verification')

    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # 1. Ingest Data
    raw_f0_data = ingest_monte_carlo_data(
        target_mean=10e9, target_sigma=25e6, num_samples=1000)

    # 2. Calculate Statistics
    mu, sigma = calculate_statistics(raw_f0_data)
    print(
        f"Calculated Statistical Variance: Mean(mu) = {mu:.3e} Hz, Sigma = {sigma:.3e} Hz")

    # 3. Binning Algorithm
    sigma_bins = generate_3sigma_bins(mu, sigma)

    # 4. Jinja2 Templating
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template('uvm_mc_coverage.svh.j2')

    output_sv = template.render(
        source_dataset="Synthesized Analytical Dataset (MOCK)",
        num_samples=len(raw_f0_data),
        mean=f"{mu:.3e}",
        sigma=f"{sigma:.3e}",
        sigma_bins=sigma_bins
    )

    out_path = os.path.join(out_dir, 'vco_coverage.svh')
    with open(out_path, 'w') as f:
        f.write(output_sv)

    print(
        f"Successfully generated SystemVerilog UVM Coverage Model: {os.path.abspath(out_path)}")


if __name__ == '__main__':
    main()
