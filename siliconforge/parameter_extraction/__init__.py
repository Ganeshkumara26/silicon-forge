"""
siliconforge.parameter_extraction
=================================

Automated parameter extraction pipeline.

Every digital constant must be mathematically derived from analog physics.
This module implements the guidebook's Chapter 11 extraction procedures.
"""

from __future__ import annotations

from siliconforge.parameter_extraction.vco_core import (
    VCOComponentSizing,
    calculate_rp_from_q,
    calculate_transconductance,
    calculate_voltage_swing,
    calculate_pss_harmonics,
    calculate_stabilization_time,
    size_vco_core,
)
from siliconforge.parameter_extraction.calibration import (
    AACParameters,
    AFCParameters,
    ChargePumpParameters,
    extract_aac_parameters,
    extract_afc_parameters,
    extract_charge_pump_parameters,
)

__all__ = [
    # VCO core sizing
    "VCOComponentSizing",
    "calculate_rp_from_q",
    "calculate_transconductance",
    "calculate_voltage_swing",
    "calculate_pss_harmonics",
    "calculate_stabilization_time",
    "size_vco_core",
    # Calibration extraction
    "AACParameters",
    "AFCParameters",
    "ChargePumpParameters",
    "extract_aac_parameters",
    "extract_afc_parameters",
    "extract_charge_pump_parameters",
]
