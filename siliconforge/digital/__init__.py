"""
siliconforge.digital
====================

Digital design automation module.
"""

from __future__ import annotations

from siliconforge.digital.rtl_flow import (
    LintResult,
    SynthesisResult,
    FormalCheckResult,
    lint_rtl,
    synthesize_rtl,
    run_formal_checks,
    analyze_timing,
)

__all__ = [
    "LintResult",
    "SynthesisResult",
    "FormalCheckResult",
    "lint_rtl",
    "synthesize_rtl",
    "run_formal_checks",
    "analyze_timing",
]
