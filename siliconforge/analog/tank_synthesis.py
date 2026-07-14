"""
siliconforge.analog.tank_synthesis
==================================

LC tank synthesis for VCO design.

Implements TODO requirements for:
- Tank synthesis
- Resonance calculation
- Q estimation
- Startup verification
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from siliconforge.device_characterization.inductor import (
    InductorCharacteristics,
    size_inductor_sg13g2,
)

__all__ = [
    "TankSynthesisResult",
    "synthesize_tank",
    "calculate_tank_capacitance",
    "calculate_tank_q",
    "calculate_startup_margin",
    "synthesize_cross_coupled_pair",
]


@dataclass
class TankSynthesisResult:
    """Result of LC tank synthesis."""

    frequency_hz: float
    inductance_h: float
    capacitance_f: float
    inductor_q: float
    tank_q: float
    startup_margin_db: float
    gm_required_siemens: float


def calculate_tank_capacitance(
    frequency_hz: float,
    inductance_h: float,
) -> float:
    """Calculate tank capacitance from resonance.

    f = 1 / (2*pi*sqrt(L*C))
    C = 1 / (omega^2 * L)
    """
    omega = 2.0 * np.pi * frequency_hz
    return 1.0 / (omega ** 2 * inductance_h)


def calculate_tank_q(
    l_char: InductorCharacteristics,
    frequency_hz: float,
) -> float:
    """Calculate loaded tank Q.

    Q_tank = 1 / (1/Q_L + 1/Q_C + 1/Q_R)
    For MOS varactor: Q_C ~ 10-20 at 10GHz
    """
    q_c = 15.0  # Varactor Q at 10GHz
    return 1.0 / (1.0 / l_char.q_at_freq + 1.0 / q_c)


def calculate_startup_margin(
    gm_siemens: float,
    r_p_ohm: float,
) -> float:
    """Calculate startup margin in dB.

    Barkhausen requires |gm * Rp| >= 1
    Margin = 20*log10(gm * Rp)
    """
    if r_p_ohm <= 0:
        return float("-inf")
    return 20.0 * np.log10(gm_siemens * r_p_ohm)


if __name__ == "__main__":
    c = calculate_tank_capacitance(10.25e9, 200e-12)
    print(f"C_tank = {c*1e15:.2f} fF")
    inductor = size_inductor_sg13g2(target_l_nh=200.0, frequency_hz=10.25e9)
    q = calculate_tank_q(inductor)
    print(f"Tank Q = {q:.1f}")
    margin = calculate_startup_margin(0.01, inductor.r_p_ohm)
    print(f"Startup margin = {margin:.1f} dB")


def synthesize_tank(
    target_frequency_hz: float = 10.25e9,
    min_q: float = 10.0,
    gm_available_siemens: float = 0.01,
    varactor_q: float = 15.0,
) -> TankSynthesisResult:
    """Synthesize LC tank for VCO.

    Parameters
    ----------
    target_frequency_hz : float
        Target oscillation frequency
    min_q : float
        Minimum Q requirement
    gm_available : float
        Available transconductance
    varactor_q : float
        Varactor Q at target frequency (default 15 for SG13G2)

    Returns
    -------
    TankSynthesisResult
    """
    if target_frequency_hz <= 0:
        raise ValueError(
            f"target_frequency_hz must be > 0; got {target_frequency_hz}")
    if min_q <= 0:
        raise ValueError(f"min_q must be > 0; got {min_q}")
    if gm_available_siemens <= 0:
        raise ValueError(
            f"gm_available_siemens must be > 0; got {gm_available_siemens}")
    inductor = size_inductor_sg13g2(
        target_l_nh=200.0,
        frequency_hz=target_frequency_hz,
    )

    c_tank = calculate_tank_capacitance(
        target_frequency_hz, inductor.inductance_h)
    tank_q = calculate_tank_q(
        inductor, target_frequency_hz, varactor_q=varactor_q)
    gm_required = 1.0 / inductor.r_p_ohm
    margin = calculate_startup_margin(gm_available_siemens, inductor.r_p_ohm)

    return TankSynthesisResult(
        frequency_hz=target_frequency_hz,
        inductance_h=inductor.inductance_h,
        capacitance_f=c_tank,
        inductor_q=inductor.q_at_freq,
        tank_q=tank_q,
        startup_margin_db=margin,
        gm_required_siemens=gm_required,
    )


def calculate_tank_q(
    l_char: InductorCharacteristics,
    frequency_hz: float,
    varactor_q: float = 15.0,
) -> float:
    """Calculate loaded tank Q.

    Q_tank = 1 / (1/Q_L + 1/Q_C + 1/Q_R)
    For MOS varactor: Q_C ~ 10-20 at 10GHz
    """
    return 1.0 / (1.0 / l_char.q_at_freq + 1.0 / varactor_q)


def synthesize_cross_coupled_pair(
    gm_required_s: float,
    v_swing_v: float = 0.4,
    temp_c: float = 27.0,
) -> dict:
    """Size cross-coupled pair for negative gm oscillator.

    Returns width/length for NMOS and PMOS.
    """
    if gm_required_s <= 0:
        raise ValueError(f"gm_required_s must be > 0; got {gm_required_s}")
    w_nm = gm_required_s * 0.1 * 1e-6
    w_pm = gm_required_s * 0.15 * 1e-6
    return {
        "nmos_w_um": w_nm,
        "nmos_l_um": 0.13,
        "pmos_w_um": w_pm,
        "pmos_l_um": 0.13,
        "v_swing_v": v_swing_v,
    }
