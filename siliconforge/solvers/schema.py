#!/usr/bin/env python3
"""schema.py — Canonical Machine-Readable Result Schema for SiliconForge.

Every SiliconForge run produces a JSON result conforming to this schema.
This enables automated regression comparison, reporting, and traceability.

Schema version: 1.0.0
"""

import json
from datetime import datetime, timezone


RESULT_SCHEMA_VERSION = "1.0.0"


def create_result(design_name, pdk, simulator, metadata=None):
    """Create a new canonical result object with required fields."""
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "design": {
            "name": design_name,
            "pdk": pdk,
            "simulator": simulator,
        },
        "metadata": metadata or {},
        "pss": {
            "converged": False,
            "frequency_hz": None,
            "period_s": None,
            "iterations": None,
            "residual": None,
            "transient_crosscheck": {
                "performed": False,
                "frequency_hz": None,
                "relative_error": None,
            },
        },
        "ppv": {
            "method": None,
            "validated": False,
            "direct_vs_adjoint": {
                "performed": False,
                "max_discrepancy": None,
            },
        },
        "phase_noise": {
            "total_dbc_per_hz": None,
            "offset_hz": None,
            "breakdown": [],
            "reference_crosscheck": {
                "performed": False,
                "reference_method": None,
                "max_discrepancy_db": None,
            },
        },
        "jitter": {
            "rms_tie_s": None,
            "rms_tie_fs": None,
            "f0_hz": None,
            "fmin_hz": None,
            "fmax_hz": None,
            "integration_method": None,
            "convention": None,
        },
        "formal": {
            "solver": None,
            "status": None,
            "properties_checked": 0,
            "properties_passed": 0,
            "counterexamples": 0,
        },
        "overall_status": "NOT_RUN",
    }


def set_pss_result(result, frequency_hz, converged, iterations=None,
                   residual=None, transient_freq=None):
    """Fill PSS results. Optionally include transient cross-check."""
    result["pss"]["converged"] = converged
    result["pss"]["frequency_hz"] = frequency_hz
    result["pss"]["period_s"] = 1.0 / frequency_hz if frequency_hz > 0 else None
    result["pss"]["iterations"] = iterations
    result["pss"]["residual"] = residual

    if transient_freq is not None:
        rel_err = abs(frequency_hz - transient_freq) / frequency_hz
        result["pss"]["transient_crosscheck"] = {
            "performed": True,
            "frequency_hz": transient_freq,
            "relative_error": rel_err,
        }


def set_ppv_result(result, method, direct_freq=None, adjoint_freq=None):
    """Fill PPV results. Optionally include direct vs adjoint cross-check."""
    result["ppv"]["method"] = method

    if direct_freq is not None and adjoint_freq is not None:
        max_ppv = max(abs(direct_freq), abs(adjoint_freq), 1e-30)
        discrepancy = abs(direct_freq - adjoint_freq) / max_ppv
        result["ppv"]["direct_vs_adjoint"] = {
            "performed": True,
            "max_discrepancy": discrepancy,
        }
        result["ppv"]["validated"] = discrepancy < 0.05


def set_phase_noise_result(result, pn_db, offset_hz, breakdown=None,
                           reference_pn_db=None):
    """Fill phase noise results. Optionally include independent reference cross-check."""
    result["phase_noise"]["total_dbc_per_hz"] = pn_db
    result["phase_noise"]["offset_hz"] = offset_hz
    result["phase_noise"]["breakdown"] = breakdown or []

    if reference_pn_db is not None:
        disc = abs(pn_db - reference_pn_db)
        result["phase_noise"]["reference_crosscheck"] = {
            "performed": True,
            "reference_method": "transient_noise",
            "max_discrepancy_db": disc,
        }


def set_jitter_result(result, tie_rms_s, f0, fmin, fmax, method, convention):
    """Fill jitter results with canonical definition metadata."""
    result["jitter"].update({
        "rms_tie_s": tie_rms_s,
        "rms_tie_fs": tie_rms_s * 1e15,
        "f0_hz": f0,
        "fmin_hz": fmin,
        "fmax_hz": fmax,
        "integration_method": method,
        "convention": convention,
    })


def set_formal_result(result, solver, status, checked=0, passed=0, ce=0):
    """Fill formal verification results."""
    result["formal"].update({
        "solver": solver,
        "status": status,
        "properties_checked": checked,
        "properties_passed": passed,
        "counterexamples": ce,
    })


def compute_overall_status(result):
    """Compute overall PASS/FAIL/INCOMPLETE status from component results."""
    # Preserve EXPECTED_FAIL for negative tests
    if result.get("overall_status") == "EXPECTED_FAIL":
        return "EXPECTED_FAIL"

    failures = []
    incomplete = []

    # Check PSS convergence (default: require it; skip only for non-oscillatory categories)
    category = result.get("metadata", {}).get("category", "oscillator")
    skip_pss_check = category in ["analog", "mixed_signal", "negative_test"]

    if not skip_pss_check and not result["pss"]["converged"]:
        failures.append("PSS did not converge")

    tc = result["pss"]["transient_crosscheck"]
    if tc["performed"] and tc["relative_error"] > 1e-3:
        err_val = tc["relative_error"]
        failures.append(f"PSS-transient mismatch: {err_val:.2e}")

    pn = result["phase_noise"]["reference_crosscheck"]
    if pn["performed"] and pn["max_discrepancy_db"] > 3.0:
        failures.append(f"Phase noise reference mismatch: {pn['max_discrepancy_db']:.1f} dB")

    if result["formal"]["status"] == "FAIL":
        failures.append("Formal verification failed")

    has_sim = (result["pss"]["frequency_hz"] is not None) or (result["formal"]["status"] is not None)
    if not has_sim:
        incomplete.append("No simulation results recorded")

    if failures:
        result["overall_status"] = "FAIL"
        result["failure_reasons"] = failures
    elif incomplete:
        result["overall_status"] = "INCOMPLETE"
    else:
        result["overall_status"] = "PASS"

    return result["overall_status"]


def save_result(result, filepath):
    """Save canonical result to JSON file."""
    compute_overall_status(result)
    with open(filepath, "w") as f:
        json.dump(result, f, indent=2)
    return result["overall_status"]


if __name__ == "__main__":
    r = create_result(
        design_name="vco_01",
        pdk="ihp_sg13g2",
        simulator="ngspice",
        metadata={"test": "schema_validation"},
    )
    set_pss_result(r, frequency_hz=10.21448e9, converged=True, iterations=8)
    set_jitter_result(
        r, tie_rms_s=45.15e-15, f0=10.21448e9,
        fmin=10e3, fmax=1e9,
        method="analytical_1/f2",
        convention="one-sided L(f) -> double-sideband S_phi(f)",
    )
    set_formal_result(r, solver="z3", status="PASS", checked=20, passed=20)
    compute_overall_status(r)
    print(json.dumps(r, indent=2))
