"""
siliconforge.parameter_extraction.calibration
============================================

Digital calibration parameter extraction.

From guidebook Chapter 11:
- AAC_WAIT_CYCLES derived from tank settling time (tau_env = 2Q/omega0)
- CAP_WIDTH determined from LSB step and monotonicity (3-sigma DNL check)
- I_CP determined from AMOS leakage at 125C (must be >> I_leak)

Every digital constant must have physical derivation. See guidebook Section 14.3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "AACParameters",
    "AFCParameters",
    "ChargePumpParameters",
    "extract_aac_parameters",
    "extract_afc_parameters",
    "extract_charge_pump_parameters",
]


@dataclass(frozen=True)
class AACParameters:
    """Automated Amplitude Control parameters."""

    tank_q: float
    frequency_hz: float
    reference_period_s: float
    settling_time_constant_s: float
    min_wait_cycles: int
    dac_resolution_bits: int  # Typically 4
    v_amp_low_mv: float  # Lower threshold (typically 600 mVpp)
    v_amp_high_mv: float  # Upper threshold (typically 800 mVpp)


@dataclass(frozen=True)
class AFCParameters:
    """Automated Frequency Control parameters."""

    total_drift_hz: float
    oscillator_frequency_hz: float
    c_lsb_f: float
    n_bits: int
    search_mode: str  # "binary" or "thermometer"
    monotonicity_sigma_cf_over_c: float  # Mismatch std dev


@dataclass(frozen=True)
class ChargePumpParameters:
    """Charge pump parameters derived from varactor leakage."""

    varactor_leakage_a: float  # At SS_hot 125C
    phase_offset_target: float  # Target phase offset (e.g. 0.01 rad)
    i_cp_a: float
    i_cp_over_leakage_ratio: float


def extract_aac_parameters(
    tank_q: float,
    frequency_hz: float,
    reference_hz: float = 50e6,
    settling_time_constant_calculated_s: float | None = None,
    dac_resolution_bits: int = 4,
    v_amp_low_mv: float = 600.0,
    v_amp_high_mv: float = 800.0,
) -> AACParameters:
    """Extract AAC wait timer and thresholds from tank physics.

    From guidebook Eq 15.1: tau_env = 2*Q/omega0
    From guidebook Eq 15.2: Wait_cycles = ceil(t_settle / T_ref)

    If settling_time_constant_calculated_s is provided, it overrides
    the calculated value (for cases where it was measured from simulation).
    """
    if tank_q <= 0:
        raise ValueError(f"tank_q must be > 0; got {tank_q}")
    if frequency_hz <= 0:
        raise ValueError(f"frequency_hz must be > 0; got {frequency_hz}")
    if reference_hz <= 0:
        raise ValueError(f"reference_hz must be > 0; got {reference_hz}")
    if dac_resolution_bits < 1:
        raise ValueError(
            f"dac_resolution_bits must be >= 1; got {dac_resolution_bits}")
    omega = 2.0 * math.pi * frequency_hz
    tau_env = settling_time_constant_calculated_s or (2.0 * tank_q / omega)
    t_ref = 1.0 / reference_hz

    t_settle = 3.0 * tau_env
    wait_cycles = math.ceil(t_settle / t_ref)
    wait_cycles_with_margin = wait_cycles * 2

    return AACParameters(
        tank_q=tank_q,
        frequency_hz=frequency_hz,
        reference_period_s=t_ref,
        settling_time_constant_s=tau_env,
        min_wait_cycles=wait_cycles_with_margin,
        dac_resolution_bits=dac_resolution_bits,
        v_amp_low_mv=v_amp_low_mv,
        v_amp_high_mv=v_amp_high_mv,
    )


def extract_afc_parameters(
    total_freq_drift_hz: float,
    oscillator_frequency_hz: float,
    l_value_h: float,
    c_lsb_f: float | None = None,
    physical_area_density_f_per_um2: float = 2.0,  # IHP SG13G2
) -> AFCParameters:
    """Extract AFC cap bank parameters from drift requirements.

    From guidebook Eq 5.12-5.15:
    - Total drift requires discrete capacitance change
    - Binary search mandates monotonicity (sigma(C) * 3 < C_LSB)
    """
    if oscillator_frequency_hz <= 0:
        raise ValueError(
            f"oscillator_frequency_hz must be > 0; got {oscillator_frequency_hz}")
    if l_value_h <= 0:
        raise ValueError(f"l_value_h must be > 0; got {l_value_h}")
    if physical_area_density_f_per_um2 <= 0:
        raise ValueError(
            f"physical_area_density_f_per_um2 must be > 0; got {physical_area_density_f_per_um2}")

    f_max = oscillator_frequency_hz + total_freq_drift_hz / 2.0
    f_min = oscillator_frequency_hz - total_freq_drift_hz / 2.0
    c_at_f_max = 1.0 / ((2.0 * math.pi * f_max) ** 2 * l_value_h)
    c_at_f_min = 1.0 / ((2.0 * math.pi * f_min) ** 2 * l_value_h)
    total_c_delta = c_at_f_min - c_at_f_max

    if c_lsb_f is None:
        c_lsb = total_c_delta / 31.0
    else:
        c_lsb = c_lsb_f

    area_needed = 3.0 * c_lsb / physical_area_density_f_per_um2
    thermometer_area = 31.0 * c_lsb / physical_area_density_f_per_um2
    binary_area = c_lsb / physical_area_density_f_per_um2

    if area_needed > binary_area * 10:
        search_mode = "thermometer"
    else:
        search_mode = "binary"

    return AFCParameters(
        total_drift_hz=total_freq_drift_hz,
        oscillator_frequency_hz=oscillator_frequency_hz,
        c_lsb_f=c_lsb,
        n_bits=5,
        search_mode=search_mode,
        monotonicity_sigma_cf_over_c=physical_area_density_f_per_um2 *
        math.sqrt(area_needed),
    )


def extract_charge_pump_parameters(
    varactor_leakage_a: float,
    phase_offset_target: float = 0.01,
) -> ChargePumpParameters:
    """Extract charge pump current from varactor leakage.

    From guidebook Eq 15.5: delta_phi = 2*pi * I_leak / I_CP
    Must have I_CP >> I_leak for negligible phase offset.
    """
    if varactor_leakage_a <= 0:
        raise ValueError(
            f"varactor_leakage_a must be > 0; got {varactor_leakage_a}")
    if phase_offset_target <= 0:
        raise ValueError(
            f"phase_offset_target must be > 0; got {phase_offset_target}")

    i_cp = varactor_leakage_a / (phase_offset_target / (2.0 * math.pi))

    return ChargePumpParameters(
        varactor_leakage_a=varactor_leakage_a,
        phase_offset_target=phase_offset_target,
        i_cp_a=i_cp,
        i_cp_over_leakage_ratio=i_cp / varactor_leakage_a,
    )
