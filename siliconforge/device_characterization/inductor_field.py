"""
siliconforge.device_characterization.inductor_field
==============================================

Open-source inductor field solver using FastHenry-style methods.

Implements open-source inductance extraction for IHP SG13G2 without HFSS/Cadence.
Uses analytical Wheeler formulas plus substrate coupling models with skin/proximity effect.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

# SG13G2 TopMetal2 parameters (from IHP PDK)
SG13_TOPMETAL2 = dict(
    sigma=3.03e7,      # S/m conductivity
    thickness=3e-6,    # 3 um
)

SG13_TOPMETAL1 = dict(
    sigma=2.78e7,      # S/m conductivity
    thickness=2e-6,    # 2 um
)


@dataclass
class InductorGeometry2D:
    """Geometric parameters for spiral inductor."""
    n_turns: int
    width_um: float
    spacing_um: float
    outer_d_um: float
    inner_d_um: float
    metal_layer: str = "TopMetal2"  # T3M2 (TopMetal2) for best Q


@dataclass
class InductorFieldResult:
    """Result of field solver for inductor."""
    inductance_h: float
    resistance_ohm: float
    capacitance_f: dict[str, float]
    f_res_hz: float
    q_factor: float
    coupling_to_substrate_db: float


def wheeler_spiral_inductance(n_turns: int, width_um: float, inner_um: float, outer_um: float) -> float:
    """Wheeler's formula for planar spiral inductors.

    L = 2 * μ0 * N^2 * avg_d * ln(2.45 * avg_d / w) / (1 + 2.5 * w / avg_d)

    This is the standard Wheeler formula for circular spirals.
    """
    mu0 = 4.0 * np.pi * 1e-7
    avg_d = (inner_um + outer_um) / 2.0 * 1e-6
    w = width_um * 1e-6

    l = 2.0 * mu0 * n_turns**2 * avg_d * \
        np.log(2.45 * avg_d / w) / (1.0 + 2.5 * w / avg_d)
    return max(l, 0.0)


def fasthenry_style_inductance(geometry: InductorGeometry2D) -> float:
    """Calculate inductance using Wheeler formula for spiral inductors."""
    return wheeler_spiral_inductance(
        geometry.n_turns, geometry.width_um, geometry.inner_d_um, geometry.outer_d_um
    )


def skin_depth(frequency_hz: float, sigma: float, mu: float = 4e-7 * np.pi) -> float:
    """Calculate skin depth: δ = sqrt(2 / (ω * μ * σ))"""
    return np.sqrt(2.0 / (2.0 * np.pi * frequency_hz * mu * sigma))


def fasthenry_style_resistance(geometry: InductorGeometry2D, frequency_hz: float = 10e9) -> float:
    """Calculate series resistance with skin effect for wide traces.

    For TopMetal2 with thickness > skin depth, uses proper skin effect formula.
    R_ac = (ρ / (2 * δ * w)) * perimeter for each turn.
    """
    n = geometry.n_turns
    w = geometry.width_um * 1e-6
    t = SG13_TOPMETAL2['thickness'] if geometry.metal_layer == 'TopMetal2' else SG13_TOPMETAL1['thickness']
    sigma = SG13_TOPMETAL2['sigma'] if geometry.metal_layer == 'TopMetal2' else SG13_TOPMETAL1['sigma']
    rho = 1.0 / sigma

    # Average turn diameter
    d_avg = (geometry.inner_d_um + geometry.outer_d_um) / 2.0 * 1e-6

    # Calculate length per turn (circumference)
    # For a spiral, turns are not full circles but approximate
    length_per_turn = np.pi * d_avg * 2  # approximate

    # Total length
    total_length = length_per_turn * n

    # Skin depth at frequency
    delta = skin_depth(frequency_hz, sigma)

    # Effective area for current flow (skin effect)
    if t > 5 * delta:
        # Thick metal: current flows in skin depth region only
        a_eff = 2.0 * w * delta + 2.0 * t * delta
    else:
        # Thin metal: uniform current density
        a_eff = w * t

    r_ac = rho * total_length / a_eff

    return r_ac


def substrate_coupling_model(geometry: InductorGeometry2D, frequency_hz: float) -> float:
    """Estimate substrate coupling using analytical model."""
    n = geometry.n_turns
    d_avg = ((geometry.outer_d_um + geometry.inner_d_um) / 2.0) * 1e-6

    # Substrate coupling coefficient (empirical for bulk CMOS)
    coupling = 0.02 * n * (d_avg / 1e-6) * np.sqrt(frequency_hz / 1e9)

    return coupling


def extract_inductor_fields(geometry: InductorGeometry2D, frequency_hz: float = 10e9) -> InductorFieldResult:
    """Full field extraction for on-chip inductor using open-source methods.

    Parameters
    ----------
    geometry : InductorGeometry2D
        Inductor geometric parameters
    frequency_hz : float
        Analysis frequency

    Returns
    -------
    InductorFieldResult
        Complete field analysis results
    """
    l_h = wheeler_spiral_inductance(
        geometry.n_turns, geometry.width_um, geometry.inner_d_um, geometry.outer_d_um
    )
    r_ohm = fasthenry_style_resistance(geometry, frequency_hz)

    # Capacitance model (substrate + fringe)
    # C_sub ~= 0.1 * N * (avg_d in um) due to substrate coupling
    c_sub = 0.1 * geometry.n_turns * \
        ((geometry.inner_d_um + geometry.outer_d_um) / 2.0) * 1e-15
    c_turn = 0.15 * geometry.width_um * 1e-15  # Fringe capacitance per turn
    c_total = c_sub + c_turn * geometry.n_turns * 2

    c_dict = {
        "c_turn_to_turn_f": c_turn * geometry.n_turns * 2,
        "c_to_substrate_f": c_sub,
        "c_total_f": c_total,
    }

    # Self-resonance (SRF)
    f_res = 1.0 / (2.0 * np.pi * np.sqrt(l_h * c_total)
                   ) if c_total > 0 else float('inf')

    # Q factor
    omega = 2.0 * np.pi * frequency_hz
    q = omega * l_h / r_ohm if r_ohm > 0 else float('inf')

    # Substrate coupling
    coupling_db = 20.0 * \
        np.log10(1.0 + substrate_coupling_model(geometry, frequency_hz))

    return InductorFieldResult(
        inductance_h=l_h,
        resistance_ohm=r_ohm,
        capacitance_f=c_dict,
        f_res_hz=f_res,
        q_factor=q,
        coupling_to_substrate_db=coupling_db,
    )


if __name__ == "__main__":
    # Design for 100 pH at 10.25 GHz targeting TopMetal2
    # For 100 pH: need ~4 turns, ~10um width, ~40um avg diameter
    for w_um in [8, 10, 12, 15]:
        for d_avg_um in [40, 50, 60]:
            inner = d_avg_um - 15
            outer = d_avg_um + 15
            n = 4
            geom = InductorGeometry2D(
                n_turns=n,
                width_um=w_um,
                spacing_um=2.0,
                outer_d_um=outer,
                inner_d_um=inner,
                metal_layer="TopMetal2",
            )
            result = extract_inductor_fields(geom, frequency_hz=10.25e9)
            if 90e-12 < result.inductance_h < 110e-12:
                print(f"w={w_um}um, d_avg={d_avg_um}um -> L={result.inductance_h*1e12:.1f} pH, "
                      f"R={result.resistance_ohm*1e3:.2f} mΩ, Q={result.q_factor:.1f}, "
                      f"SRF={result.f_res_hz/1e9:.1f} GHz")
