"""
siliconforge.analog
===================

Analog design automation module.
"""

from __future__ import annotations

from siliconforge.analog.tank_synthesis import (
    TankSynthesisResult,
    synthesize_tank,
    calculate_tank_capacitance,
    calculate_tank_q,
    calculate_startup_margin,
    synthesize_cross_coupled_pair,
)

__all__ = [
    "TankSynthesisResult",
    "synthesize_tank",
    "calculate_tank_capacitance",
    "calculate_tank_q",
    "calculate_startup_margin",
    "synthesize_cross_coupled_pair",
]
