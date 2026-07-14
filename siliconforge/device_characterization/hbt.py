"""
siliconforge.device_characterization.hbt
======================================

HBT transistor characterization for IHP SG13G2 process.

Implements TODO requirements for:
- beta, transit frequency, gain
- Early voltage, breakdown
- Capacitances
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "HBTCharacteristics",
    "characterize_hbt_sg13g2",
    "calculate_beta",
    "calculate_transit_frequency",
    "calculate_early_voltage",
    "calculate_hbt_gain",
    "calculate_hbt_voltage_gain",
    "calculate_capacitances",
]


@dataclass
class HBTCharacteristics:
    """Complete HBT transistor characterization."""

    beta: float  # Current gain
    ft_hz: float  # Transit frequency
    early_voltage: float  # Early voltage (V_A)
    veb_v: float  # Emitter-base voltage
    vcb_v: float  # Collector-base voltage
    ic_ma: float  # Collector current
    gm_siemens: float  # Transconductance
    ro_ohm: float  # Output resistance
    breakdown_v: float  # BV_CEO breakdown voltage
    cbc_f: float  # Collector-base capacitance
    cbe_f: float  # Collector-emitter (base) capacitance


def calculate_beta(
    ic_a: float,
    ib_a: float,
) -> float:
    """Calculate current gain beta = Ic/Ib."""
    return ic_a / ib_a if ib_a > 0 else 0.0


def calculate_transit_frequency(
    gm_siemens: float,
    cbc_f: float,
) -> float:
    """Calculate transit frequency ft = gm / (2*pi*Cbc).

    For HBT, Cbc dominates at high frequency.
    """
    return gm_siemens / (2.0 * np.pi * cbc_f) if cbc_f > 0 else 0.0


def calculate_early_voltage(
    vce_v: float,
    vb_v: float,
) -> float:
    """Calculate Early voltage V_A = Vce - 0.1*Vb (approximation)."""
    return vce_v - 0.1 * vb_v


def calculate_hbt_gain(
    beta: float,
    ro_ohm: float,
) -> float:
    """Return transconductance-related gain proxy beta * Ro (Ohms).

    This is NOT dimensionless common-emitter voltage gain.
    For CE voltage gain use calculate_hbt_voltage_gain(gm, ro_ohm).
    """
    return beta * ro_ohm


def calculate_hbt_voltage_gain(
    beta: float,
    gm_s: float,
    ro_ohm: float,
) -> float:
    """Calculate common-emitter voltage gain Av = gm * Ro (dimensionless)."""
    if ro_ohm <= 0:
        raise ValueError(f"ro_ohm must be > 0; got {ro_ohm}")
    return gm_s * ro_ohm


def calculate_capacitances(
    cbc_f: float = 0.2e-15,  # Base-collector depletion
    cbe_f: float = 0.3e-15,  # Base-emitter depletion
    freq_hz: float = 10e9,
) -> tuple[float, float]:
    """Get capacitances at frequency of interest.

    Capacitances may have junction and quasi-static components
    that vary with bias and frequency.
    """
    return cbc_f, cbe_f


def characterize_hbt_sg13g2(
    ic_ma: float = 1.0,
    veb_v: float = 0.8,
    vcb_v: float = 1.2,
    temp_c: float = 27.0,
) -> HBTCharacteristics:
    """Complete HBT characterization for IHP SG13G2.

    Parameters
    ----------
    ic_ma : float
        Collector current in mA
    veb_v : float
        Emitter-base voltage
    vcb_v : float
        Collector-base voltage
    temp_c : float
        Temperature for characterization

    Returns
    -------
    HBTCharacteristics
        All extracted parameters
    """
    ic_a = ic_ma * 1e-3

    # Temperature-dependent base current
    ib_a = ic_a / 50.0  # Approximate beta = 50 at 10mA for SG13G2

    beta = calculate_beta(ic_a, ib_a)

    # gm for HBT (different from MOS)
    gm = 40e-3 * ic_a  # gm ~ 40 mS/A for SG13G2

    # Output resistance
    ro = 2000.0  # Typical for SG13G2 HBT

    # Transit frequency
    cbc = 0.2e-15 * (1.0 - vcb_v / 3.3)  # Depletion narrows with reverse bias
    ft = calculate_transit_frequency(gm, max(cbc, 0.05e-15))

    # Early voltage
    early_v = calculate_early_voltage(1.2, veb_v)

    # Breakdown voltage
    breakdown = 3.3  # BV_CEO for SG13G2

    return HBTCharacteristics(
        beta=beta,
        ft_hz=ft,
        early_voltage=early_v,
        veb_v=veb_v,
        vcb_v=vcb_v,
        ic_ma=ic_ma,
        gm_siemens=gm,
        ro_ohm=ro,
        breakdown_v=breakdown,
        cbc_f=0.2e-15,
        cbe_f=0.3e-15,
    )


if __name__ == "__main__":
    beta = calculate_beta(0.01, 0.0002)
    print(f"beta = {beta:.1f}")
    ft = calculate_transit_frequency(40e-3, 0.2e-15)
    print(f"ft = {ft/1e9:.2f} GHz")
    va = calculate_early_voltage(1.2, 0.8)
    print(f"Early voltage = {va:.2f} V")
    av = calculate_hbt_voltage_gain(beta=beta, gm_s=40e-3, ro_ohm=2000.0)
    print(f"CE voltage gain = {av:.1f}")
