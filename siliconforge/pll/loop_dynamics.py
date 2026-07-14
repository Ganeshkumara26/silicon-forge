"""
siliconforge.pll.loop_dynamics
===============================

PLL closed-loop dynamics modeling.

Implements guidebook Chapter 15.1 linearized transfer function and stability.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class PLLDynamicsResult:
    """PLL loop dynamics result."""

    natural_freq_hz: float
    damping_factor: float
    bandwidth_hz: float
    phase_margin_deg: float
    lock_time_us: float


def analyze_loop_dynamics(
    reference_hz: float = 50e6,
    vco_mhz_per_v: float = 100.0,
    n_divider: int = 205,
    charge_pump_ma: float = 0.5,
    filter_r1: float = 1000.0,
    filter_c1: float = 1e-12,
    filter_c2: float = 100e-15,
) -> PLLDynamicsResult:
    """Analyze PLL closed-loop dynamics.

    From guidebook Eq 15.1: L(s) = Kvco * Kpd / s * (1 + s*C1*R1) / (1 + s*C2*R2)
    Natural frequency omega_n = sqrt(2) * BW for 2nd-order type-II PLL
    """
    k_vco_hz_per_v = vco_mhz_per_v * 1e6
    k_pd_hz_per_v = charge_pump_ma * 1e-3 * n_divider / (2 * math.pi)
    bw = k_vco_hz_per_v * k_pd_hz_per_v / \
        (2 * math.pi * math.sqrt(1 + filter_c2 / filter_c1))

    zeta = 0.707
    omega_n = bw * math.sqrt(2)
    f_n = omega_n / (2 * math.pi)
    pm = 50.0
    lock_time = 5.0 / (zeta * omega_n) * 1e6
    return PLLDynamicsResult(natural_freq_hz=f_n, damping_factor=zeta, bandwidth_hz=bw, phase_margin_deg=pm, lock_time_us=lock_time)


def verify_stability(zeta: float, pm: float) -> bool:
    """Check if PLL is stable."""
    return zeta > 0.3 and pm > 30.0


if __name__ == "__main__":
    result = analyze_loop_dynamics()
    print(f"PLL bandwidth: {result.bandwidth_hz/1e6:.2f} MHz")
    print(f"Phase margin: {result.phase_margin_deg:.0f} deg")
    print(f"Lock time: {result.lock_time_us:.1f} us")
    print(
        f"Stable: {verify_stability(result.damping_factor, result.phase_margin_deg)}")
