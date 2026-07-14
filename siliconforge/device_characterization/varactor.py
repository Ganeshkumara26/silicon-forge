"""
siliconforge.device_characterization.varactor
==========================================

Varactor diode characterization for VCO tuning.

Implements TODO requirements for:
- C-V characteristics
- Tuning range
- Q factor
- Nonlinearity
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "VaractorCharacteristics",
    "characterize_varactor_sg13g2",
    "varactor_c_v",
    "varactor_tuning_range",
    "varactor_q_factor",
    "varactor_nonlinearity",
]


@dataclass
class VaractorCharacteristics:
    """Varactor diode characterization."""

    # A, B, C, D for C(V) = A/(B+V)^2 + C/(D+V)^2
    c_v_coefficients: tuple[float, float, float, float]
    c_min_pf: float  # Minimum capacitance at max reverse bias
    c_max_pf: float  # Maximum capacitance at min reverse bias
    tuning_range_percent: float  # (Cmax - Cmin) / Cmean
    q_factor_mhz: float  # Q at 10 GHz
    nonlinearity_pf_per_v: float  # d²C/dV² normalized


def varactor_c_v(
    v_ctrl_v: float,
    a: float = 1.0,
    b: float = 0.3,
    c: float = 0.5,
    d: float = 1.0,
    area_um2: float = 1.0,
) -> float:
    """Calculate varactor capacitance vs control voltage.

    C(V) = A/(B+V)^2 + C/(D+V)^2

    Notes:
    - This two-term rational model is an approximation. Replace A/B/C/D
      with IHP PDK-fitted coefficients for accurate SG13G2 data.
    - Area scaling is not purely linear in this model; the coefficients
      should be re-fitted per area or replaced with a proper C(V,A) model.
    """
    if area_um2 <= 0:
        raise ValueError(f"area_um2 must be > 0; got {area_um2}")
    if v_ctrl_v + b <= 0 or v_ctrl_v + d <= 0:
        return 0.1e-15 * area_um2
    return area_um2 * (a / (v_ctrl_v + b) ** 2 + c / (v_ctrl_v + d) ** 2)


def varactor_tuning_range(
    v_min_v: float,
    v_max_v: float,
    area_um2: float = 1.0,
    **cv_params,
) -> tuple[float, float, float]:
    """Calculate tuning range for given control voltage span.

    Returns (Cmin, Cmax, tuning_range_percent)
    """
    c_min = varactor_c_v(v_max_v, area_um2=area_um2, **
                         cv_params)  # Min C at max V (reverse bias)
    c_max = varactor_c_v(v_min_v, area_um2=area_um2, **
                         cv_params)  # Max C at min V

    c_mean = (c_min + c_max) / 2.0
    tuning_range = (c_max - c_min) / c_mean * 100.0

    return c_min, c_max, tuning_range


def varactor_q_factor(
    frequency_hz: float,
    c_f: float,
    series_r_ohm: float = 1.0,
) -> float:
    """Calculate Q factor at given frequency.

    Q = 1/R * sqrt(L/C) = 1/(R*omega*C)
    """
    if c_f > 0:
        return 1.0 / (series_r_ohm * 2.0 * np.pi * frequency_hz * c_f)
    return 0.0


def varactor_nonlinearity(
    v_ctrl_v: float,
    **cv_params,
) -> float:
    """Calculate nonlinearity coefficient d²C/dV².

    For linear tuning, want d²C/dV² = 0.
    This guides C_LSB sizing.
    """
    epsilon = 1e-3
    c_plus = varactor_c_v(v_ctrl_v + epsilon, **cv_params)
    c_minus = varactor_c_v(v_ctrl_v - epsilon, **cv_params)
    c_center = varactor_c_v(v_ctrl_v, **cv_params)

    second_deriv = (c_plus - 2 * c_center + c_minus) / epsilon ** 2
    return -second_deriv  # Negative for reverse-biased varactor


def characterize_varactor_sg13g2(
    area_um2: float = 100.0,
    v_min_v: float = 0.0,
    v_max_v: float = 1.2,
    frequency_hz: float = 10e9,
) -> VaractorCharacteristics:
    """Characterize SG13G2 varactor structure.

    Uses MIM capacitor with diffusion overlap for tuning.

    Parameters
    ----------
    area_um2 : float
        Varactor area in square microns
    v_min_v, v_max_v : float
        Control voltage range
    frequency_hz : float
        Operating frequency for Q calculation

    Returns
    -------
    VaractorCharacteristics
    """
    c_ox_sg13 = 0.2e-15  # F/um^2 for MIM cap (tapeout: use PDK characterization data)

    # Fit parameters for voltage dependence
    a = c_ox_sg13 * area_um2 * 0.7
    b = 0.3
    c = c_ox_sg13 * area_um2 * 0.3
    d = 1.0

    c_min_pf = varactor_c_v(v_max_v, a, b, c, d, area_um2=area_um2) * 1e15
    c_max_pf = varactor_c_v(v_min_v, a, b, c, d, area_um2=area_um2) * 1e15

    _, _, tuning_range = varactor_tuning_range(
        v_min_v, v_max_v, a=a, b=b, c=c, d=d)

    c_mean = (c_min_pf + c_max_pf) / 2.0
    q_mhz = varactor_q_factor(frequency_hz, c_mean * 1e-15, series_r_ohm=2.0)

    # Nonlinearity at center voltage
    v_center = (v_min_v + v_max_v) / 2.0
    nonlinearity = varactor_nonlinearity(v_center, a=a, b=b, c=c, d=d)

    return VaractorCharacteristics(
        c_v_coefficients=(a, b, c, d),
        c_min_pf=c_min_pf,
        c_max_pf=c_max_pf,
        tuning_range_percent=tuning_range,
        q_factor_mhz=q_mhz,
        nonlinearity_pf_per_v=nonlinearity,
    )


if __name__ == "__main__":
    c = varactor_c_v(0.5, area_um2=100.0)
    print(f"C(0.5V) = {c*1e15:.2f} fF")
    c_min, c_max, tr = varactor_tuning_range(0.0, 1.2, area_um2=100.0)
    print(
        f"tuning range = {tr:.1f}% ({c_min*1e15:.1f}fF .. {c_max*1e15:.1f}fF)")
