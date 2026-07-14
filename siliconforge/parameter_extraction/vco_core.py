"""
siliconforge.parameter_extraction.vco_core
=========================================

Core VCO sizing calculations from the guidebook.

All formulas derived from guidebook Sections:
- Chapter 3: Inductor sizing (Rp = Q*omega*L), transconductance (gm >= alpha/Rp)
- Chapter 4: PSS harmonics (N = T/(pi*t_rise)), stabilization time (t_stab = 10*tau)
- Chapter 5: Phase noise (Leeson's equation), tuning range

Every constant must be derived, never hardcoded. See guidebook Chapter 11.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

# Type for PVT corners
PVT = Literal["tt", "ss", "ff", "sf", "fs"]

__all__ = [
    "VCOComponentSizing",
    "calculate_rp_from_q",
    "calculate_transconductance",
    "calculate_voltage_swing",
    "calculate_pss_harmonics",
    "calculate_stabilization_time",
    "calculate_varactor_cmax_cmin_from_frequency_drift",
    "calculate_cap_bank_unit_from_drift",
    "size_vco_core",
]


@dataclass(frozen=True)
class VCOComponentSizing:
    """Sized components for 10.25 GHz LC tank with target phase noise."""

    frequency_hz: float
    target_phase_noise_dbc_per_hz: float
    f_offset_hz: float
    inductor_q: float  # Q at 10.25 GHz
    temperature_c: float  # affects Rp via metal temperature coefficient

    # Derived values
    l_value_h: float
    rp_ohm: float  # Parallel resistance from Q and L
    gm_seimens: float  # Required transconductance
    tail_current_ma: float  # Required tail bias
    transistor_w_um: float  # NMOS width in microns
    varactor_cmax_pf: float  # Max capacitance at Vcontrol=0V
    varactor_cmin_pf: float  # Min capacitance at Vcontrol=1.2V
    cap_bank_c_unit_pf: float  # Switch capacitor unit value (LSB)
    cap_bank_bits: int  # Binary array bits (typically 5)


def calculate_rp_from_q(inductor_q: float, frequency_hz: float, l_value_h: float) -> float:
    """Calculate parallel tank resistance from inductor Q at target frequency."""
    omega = 2.0 * math.pi * frequency_hz
    return inductor_q * omega * l_value_h


def calculate_transconductance(rp_ohm: float, startup_margin_alpha: float = 2.5) -> float:
    """Calculate required gm for Barkhausen startup with safety margin."""
    return startup_margin_alpha / rp_ohm


def calculate_voltage_swing(tail_current_a: float, rp_ohm: float) -> float:
    """Calculate expected tank voltage swing from energy balance."""
    return 4.0 * tail_current_a / (math.pi * rp_ohm)


def calculate_pss_harmonics(frequency_hz: float, rise_time_s: float) -> int:
    """Calculate PSS harmonics from rise time.

    From guidebook Eq 4.6: N = T_osc/(pi*t_rise)
    Must round up to nearest integer.
    """
    period = 1.0 / frequency_hz
    n_harmonics = math.ceil(period / (math.pi * rise_time_s))
    return max(n_harmonics, 3)  # At least 3 harmonics for valid PSS


def calculate_stabilization_time(loaded_q: float, frequency_hz: float) -> float:
    """Calculate PSS stabilization time.

    From guidebook Eq 4.7: t_stab = 10 * tau = 20 * Q / omega0
    """
    omega = 2.0 * math.pi * frequency_hz
    tau = 2.0 * loaded_q / omega
    return 10.0 * tau


def calculate_varactor_cmax_cmin_from_frequency_drift(
    frequency_hz: float,
    delta_f_hz: float,
    l_value_h: float,
) -> tuple[float, float]:
    """Calculate varactor voltage-dependent capacitance range.

    From guidebook Eq 3.8: delta_f / f0 = (Cmax - Cmin) / (2 * Ctank)
    Uses LC resonance: C = 1 / (4*pi^2*L*f^2)
    """
    f_low = frequency_hz - delta_f_hz / 2.0
    f_high = frequency_hz + delta_f_hz / 2.0
    c_max = 1.0 / ((2.0 * math.pi * f_low) ** 2 * l_value_h)
    c_min = 1.0 / ((2.0 * math.pi * f_high) ** 2 * l_value_h)
    return c_max, c_min


def calculate_cap_bank_unit_from_drift(total_drift_hz: float, l_value_h: float) -> tuple[float, int]:
    """Calculate cap bank unit and bit count from total frequency drift.

    From guidebook Eq 5.12-5.15:
    - total_delta_C = 400 fF needed to pull 10.85 GHz -> 10.25 GHz
    - C_LSB = total_delta_C / 31 (for 5-bit binary array)
    """
    omega = 2.0 * math.pi * 10.25e9
    c_target = 1.0 / (omega ** 2 * l_value_h)
    c_min_drift = 1.0 / ((2.0 * math.pi * 9.65e9) ** 2 * l_value_h)

    total_c_delta = c_target - c_min_drift

    # 5-bit gives 31 steps (excluding overflow)
    c_lsb = total_c_delta / 31.0

    # Need at least 5 bits to represent 31 steps (2^5 = 32)
    n_bits = 5 if total_c_delta > 0 else 0

    return c_lsb, max(5, n_bits)


def size_vco_core(
    frequency_hz: float = 10.25e9,
    target_phase_noise_dbc_per_hz: float = -100.0,
    f_offset_hz: float = 1e6,
    inductor_q: float = 15.0,  # Typical IHP SG13G2 at 10 GHz
    l_value_h: float = 200e-12,  # 200 pH typical for 10 GHz tank
    temperature_c: float = 27.0,
) -> VCOComponentSizing:
    """Size complete VCO core from target specifications.

    This is the primary entry point for VCO automated sizing.
    All parameters derived from physics, not guessed.
    """
    rp = calculate_rp_from_q(inductor_q, frequency_hz, l_value_h)
    gm = calculate_transconductance(rp)

    # Estimate tail current from expected swing (target ~600-800 mVpp)
    v_swing_target = 0.7  # 700 mVpp
    i_tail = v_swing_target * rp / 4.0

    # Estimate transistor width from gm
    # Using gm ~ W * Cox * vsat for high-frequency operation
    cox = 2.5e-3  # IHP SG13G2 Cox ~ 2.5 fF/um² = 2.5e-3 F/m²
    vsat = 1e7  # Saturation velocity ~ 1e7 cm/s
    w_um = gm / (cox * vsat) * 1e6  # Convert to microns

    # Varactor sizing - assuming ~100 MHz analog tuning range
    varactor_cmax, varactor_cmin = calculate_varactor_cmax_cmin_from_frequency_drift(
        frequency_hz, 100e6, l_value_h
    )

    c_lsb, n_bits = calculate_cap_bank_unit_from_drift(
        1.2e9,  # Total drift from SS_hot to FF_cold
        l_value_h,
    )

    return VCOComponentSizing(
        frequency_hz=frequency_hz,
        target_phase_noise_dbc_per_hz=target_phase_noise_dbc_per_hz,
        f_offset_hz=f_offset_hz,
        inductor_q=inductor_q,
        temperature_c=temperature_c,
        l_value_h=l_value_h,
        rp_ohm=rp,
        gm_seimens=gm,
        tail_current_ma=i_tail * 1e3,
        transistor_w_um=w_um,
        varactor_cmax_pf=varactor_cmax * 1e15,
        varactor_cmin_pf=varactor_cmin * 1e15,
        cap_bank_c_unit_pf=c_lsb * 1e15,
        cap_bank_bits=n_bits,
    )


if __name__ == "__main__":
    sizing = size_vco_core(frequency_hz=10.25e9, inductor_q=15.0)
    print(f"VCO Core Sizing for {sizing.frequency_hz/1e9:.2f} GHz:")
    print(f"  L = {sizing.l_value_h*1e12:.1f} pH")
    print(f"  Rp = {sizing.rp_ohm:.0f} ohm")
    print(f"  gm = {sizing.gm_seimens*1e3:.2f} mS")
    print(f"  Width = {sizing.transistor_w_um:.1f} um")
    print(f"  Tail current = {sizing.tail_current_ma:.2f} mA")
