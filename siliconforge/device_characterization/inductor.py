"""
siliconforge.device_characterization.inductor
===========================================

On-chip inductor characterization for LC VCO tanks.

Implements TODO requirements for:
- Inductance
- Q factor
- Rp, Rs (parallel/serial resistance)
- Self resonance
- Substrate loss
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "InductorCharacteristics",
    "size_inductor_sg13g2",
    "calculate_inductance_rect",
    "calculate_q_factor",
    "calculate_self_resonance",
]


@dataclass
class InductorCharacteristics:
    """On-chip inductor characterization."""

    inductance_h: float  # Inductance value
    q_min: float  # Minimum Q across frequency range
    q_at_freq: float  # Q at target frequency
    r_p_ohm: float  # Parallel resistance (loss)
    r_s_ohm: float  # Serial resistance (conductor)
    f_res_hz: float  # Self-resonance frequency
    substrate_loss_db: float  # Substrate coupling loss at 10GHz


def calculate_inductance_rect(
    n_turns: int,
    w_um: float,
    l_um: float,
    gap_um: float,
    permeability: float = 1.0,
) -> float:
    """Calculate rectangular spiral inductor inductance.

    Based on Wheeler's formula and IHP SG13G2 geometry.
    L = 2 * mu0 * N^2 * average_d * ln(2.45 * average_d / w) / (1 + 2.5 * w / average_d)
    """
    if w_um <= 0:
        raise ValueError(f"w_um must be > 0; got {w_um}")
    if n_turns < 1:
        raise ValueError(f"n_turns must be >= 1; got {n_turns}")
    outer_d = l_um + 2 * gap_um
    inner_d = l_um - 2 * gap_um if l_um > 2 * gap_um else 1.0
    average_d = (outer_d + inner_d) / 2.0

    mu0 = 4.0 * np.pi * 1e-7

    if average_d > 0 and w_um > 0:
        l = 2.0 * mu0 * n_turns ** 2 * average_d * \
            np.log(2.45 * average_d / w_um) / (1.0 + 2.5 * w_um / average_d)
        return l * permeability
    return 0.0


def calculate_q_factor(
    frequency_hz: float,
    l_h: float,
    r_s_ohm: float,
    substrate_k: float = 0.02,
) -> float:
    """Calculate Q factor including conductor and substrate losses.

    Q = omega * L / R_s + omega * L * R_p (parallel path through substrate)
    """
    omega = 2.0 * np.pi * frequency_hz
    q_conductor = omega * l_h / r_s_ohm if r_s_ohm > 0 else float("inf")
    q_substrate = omega * l_h * substrate_k
    return max(q_conductor, q_substrate)


def calculate_self_resonance(
    l_h: float,
    c_pad_f: float,
    c_wind_f: float,
    c_substrate_f: float,
) -> float:
    """Calculate self-resonance frequency.

    f_res = 1 / (2*pi * sqrt(L * (C_pad + C_wind + C_substrate)))
    """
    total_c = c_pad_f + c_wind_f + c_substrate_f
    if total_c > 0:
        return 1.0 / (2.0 * np.pi * np.sqrt(l_h * total_c))
    return float('inf')


def size_inductor_sg13g2(
    target_l_nh: float = 200.0,
    frequency_hz: float = 10.25e9,
    n_turns: int = 4,
) -> InductorCharacteristics:
    """Size inductor for IHP SG13G2 process.

    Parameters
    ----------
    target_l_nh : float
        Target inductance in nH
    frequency_hz : float
        Operating frequency
    n_turns : int
        Number of turns (typically 3-5 for 10GHz)

    Returns
    -------
    InductorCharacteristics
    """
    # SG13G2 metal parameters
    metal_thickness = 0.4e-6  # 400nm copper
    metal_conductivity = 5.96e7  # S/m

    # Estimate geometry for target inductance
    # For 200nH spiral: ~50um outer diameter, 4um trace width, 4 turns
    l_um = target_l_nh * 0.1 * n_turns  # Estimate
    w_um = 4.0
    gap_um = 2.0

    l_h = calculate_inductance_rect(n_turns, w_um, l_um, gap_um)

    # Serial resistance (conductor loss)
    r_s_ohm = target_l_nh / (1e9 * metal_conductivity *
                             metal_thickness * w_um * 1e-6)

    # Parallel resistance (from Q)
    q_target = 15.0  # Typical for SG13G2 at 10GHz
    r_p_ohm = q_target * 2.0 * np.pi * frequency_hz * l_h

    # Self-resonance
    c_pad = 5e-15  # Fringe to substrate
    c_wind = 1e-15  # Turn-to-turn
    c_substrate = 2e-15  # Substrate coupling
    f_res = calculate_self_resonance(l_h, c_pad, c_wind, c_substrate)

    q_at_freq = calculate_q_factor(frequency_hz, l_h, r_s_ohm)

    return InductorCharacteristics(
        inductance_h=l_h,
        q_min=q_at_freq,
        q_at_freq=q_at_freq,
        r_p_ohm=r_p_ohm,
        r_s_ohm=r_s_ohm,
        f_res_hz=f_res,
        substrate_loss_db=10 * np.log10(1 + frequency_hz / 10e9),
    )


if __name__ == "__main__":
    l = calculate_inductance_rect(4, 4.0, 50.0, 2.0)
    print(f"L(4turns, 50um) = {l*1e9:.2f} nH")
    q = calculate_q_factor(10e9, l, 2.0)
    print(f"Q(10GHz) = {q:.1f}")
    f_res = calculate_self_resonance(l, 5e-15, 1e-15, 2e-15)
    print(f"f_res = {f_res/1e9:.2f} GHz")
