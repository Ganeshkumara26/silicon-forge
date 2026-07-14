"""
siliconforge.pll
================

PLL (Phase-Locked Loop) design modules.

Implements guidebook Chapter 15 PLL theory and design.
"""

from __future__ import annotations

from siliconforge.pll.loop_dynamics import (
    PLLDynamicsResult,
    analyze_loop_dynamics,
    verify_stability,
)

__all__ = [
    "PLLDynamicsResult",
    "analyze_loop_dynamics",
    "verify_stability",
]
