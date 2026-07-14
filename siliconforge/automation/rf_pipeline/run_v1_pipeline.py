#!/usr/bin/env python3
"""
run_v1_pipeline.py -- Top-level V1 PPV pipeline orchestrator.

Runs the full 9-stage extraction and analysis flow:
1. PSS via shooting method (shooting_method.py)
2. PPV/ISF extraction (ppv_direct_injection.py)
3. PPV suite extraction (ppv_suite.py)
4. Phase noise breakdown (ppv_breakdown.py)
5. Multi-part phase noise analysis
6. Jitter integration (ppv_jitter.py)
7. Verilog-A model generation (gen_verilog_a.py)
8. Adjoint PPV validation (ppv_adjoint.py)
9. PVT corner sweep (pvt_sweep.py)
"""

from siliconforge.config.paths import (
    NETLISTS_DIR, RESULTS_DIR, RF_PIPELINE_DIR, to_wsl_path, ensure_dirs,
    VCO_NETLIST, TB_V1_VCO_XYCE, XYCE_PSP_PLUGIN_WSL
)
import sys
import subprocess
from pathlib import Path

# Add project root to path for config import
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run command with proper error handling."""
    work_dir = cwd or RF_PIPELINE_DIR
    print(f"\n[RUNNING] {' '.join(cmd)}")
    print(f"[CWD] {work_dir}")
    result = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(f"[STDERR] {result.stderr}", file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}")
    return result


def main() -> int:
    ensure_dirs()

    print("=" * 60)
    print(" STARTING V1 10.25GHz PPV PIPELINE")
    print("=" * 60)

    netlist = NETLISTS_DIR / TB_V1_VCO_XYCE
    nodes = ["out_p", "out_n", "vtune"]
    plugin = XYCE_PSP_PLUGIN_WSL

    if not netlist.exists():
        print(f"[ERROR] Netlist not found: {netlist}")
        return 1

    try:
        # Stage 1: PSS via Shooting Method
        print("\n[STAGE 1/9] PSS Shooting-Newton Extraction")
        run([
            sys.executable, "shooting_method.py",
            "--netlist", str(netlist),
            "--nodes", *nodes,
            "--plugin", plugin
        ])

        # Stage 2: PPV Direct Injection
        print("\n[STAGE 2/9] PPV/ISF Direct Injection Sweep")
        run([
            sys.executable, "ppv_direct_injection.py",
            "--netlist", str(netlist),
            "--mode", "accurate",
            "--nodes", *nodes,
            "--plugin", plugin
        ])

        # Stage 3: PPV Suite Extraction (full PSS->PPV)
        print("\n[STAGE 3/9] PPV Suite Extraction")
        run([
            sys.executable, "ppv_suite.py", "extract",
            "--netlist", str(netlist),
            "--nodes", *nodes,
            "--plugin", plugin,
            "--mode", "accurate"
        ])

        # Stage 4: Phase Noise Breakdown
        print("\n[STAGE 4/9] Phase Noise Breakdown")
        run([sys.executable, "ppv_breakdown.py"])

        # Stage 5: Multi-part Phase Noise (uses ppv_breakdown.py output)
        print("\n[STAGE 5/9] Multi-Part Phase Noise Analysis")
        # This is embedded in ppv_breakdown.py via MultiPartPhaseNoiseAnalyzer

        # Stage 6: Jitter Integration
        print("\n[STAGE 6/9] Time-Domain Jitter Integration")
        run([sys.executable, "ppv_jitter.py"])

        # Stage 7: Verilog-A Model Generation
        print("\n[STAGE 7/9] Verilog-A Macro-Model Generation")
        run([sys.executable, "gen_verilog_a.py"])

        # Stage 8: Adjoint PPV Validation
        print("\n[STAGE 8/9] Adjoint PPV Validation")
        run([
            sys.executable, "ppv_adjoint.py",
            "--netlist", str(netlist),
            "--nodes", *nodes,
            "--plugin", plugin
        ])

        # Stage 9: PVT Corner Sweep
        print("\n[STAGE 9/9] PVT Corner Sweep")
        run([
            sys.executable, "pvt_sweep.py",
            "--netlist", str(netlist),
            "--plugin", plugin,
            "--nodes", *nodes
        ])

        print("\n" + "=" * 60)
        print(" PIPELINE COMPLETED SUCCESSFULLY")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAILED] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
