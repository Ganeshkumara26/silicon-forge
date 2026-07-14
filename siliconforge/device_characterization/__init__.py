"""
siliconforge.device_characterization
===================================

Device characterization for analog/RF circuits.

Implements TODO requirements for:
- MOS transistors (gm, gds, ft, fmax, Vth, capacitances, leakage, noise)
- HBT transistors (beta, ft, gain, breakdown, capacitances)
- Varactors (C-V, tuning range, Q, nonlinearity)
- Inductors (L, Q, Rp, Rs, self-resonance, substrate loss)
"""

from __future__ import annotations

from siliconforge.device_characterization.mos import (
    MOSCharacteristics,
    characterize_mos_sg13g2,
    calculate_gm_mos,
    calculate_ft,
    calculate_fmax,
)
from siliconforge.device_characterization.hbt import (
    HBTCharacteristics,
    characterize_hbt_sg13g2,
    calculate_transit_frequency,
)
from siliconforge.device_characterization.varactor import (
    VaractorCharacteristics,
    characterize_varactor_sg13g2,
    varactor_c_v,
)
from siliconforge.device_characterization.inductor import (
    InductorCharacteristics,
    size_inductor_sg13g2,
    calculate_inductance_rect,
    calculate_q_factor,
    calculate_self_resonance,
)
from siliconforge.device_characterization.inductor_field import (
    InductorGeometry2D,
    InductorFieldResult,
    extract_inductor_fields,
    fasthenry_style_inductance,
    fasthenry_style_resistance,
)
from siliconforge.device_characterization.inductor_openems import (
    OpenEMSGeometry,
    OpenEMSResult,
    simulate_inductor_3d,
    check_openems_available,
    generate_openems_script,
)

__all__ = [
    # MOS
    "MOSCharacteristics",
    "characterize_mos_sg13g2",
    "calculate_gm_mos",
    "calculate_ft",
    "calculate_fmax",
    # HBT
    "HBTCharacteristics",
    "characterize_hbt_sg13g2",
    "calculate_transit_frequency",
    # Varactor
    "VaractorCharacteristics",
    "characterize_varactor_sg13g2",
    "varactor_c_v",
    # Inductor
    "InductorCharacteristics",
    "size_inductor_sg13g2",
    "calculate_inductance_rect",
    "calculate_q_factor",
    "calculate_self_resonance",
    "InductorGeometry2D",
    "InductorFieldResult",
    "extract_inductor_fields",
    "fasthenry_style_inductance",
    "fasthenry_style_resistance",
    "OpenEMSGeometry",
    "OpenEMSResult",
    "simulate_inductor_3d",
    "check_openems_available",
]
