"""
Case Study Runner: Adaptive Multi-Domain Clock Management Subsystem
===================================================================

End-to-end validation using the V1 Varactor VCO characterization data.

Usage:
    python tests/case_study/run_case_study.py
"""

import os
import re
import sys
import glob
import json
import subprocess
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
VIVADO_BIN = r"D:\softwares\AMD\2026.1\Vivado\bin"

RTL_DIR = os.path.join(SCRIPT_DIR, "rtl")
TB_DIR = os.path.join(SCRIPT_DIR, "tb")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")


def print_header(title):
    print("\n" + "=" * 80)
    print(f"[{time.strftime('%H:%M:%S')}] {title}")
    print("=" * 80)


def phase1_load_characterization():
    """Load pre-computed physical data from the case study."""
    print_header("PHASE 1: Load Case Study Characterization Data")

    jitter_path = os.path.join(RESULTS_DIR, "jitter_metrics.json")
    pn_path = os.path.join(RESULTS_DIR, "phase_noise_breakdown.json")
    ppv_path = os.path.join(RESULTS_DIR, "ppv_data.json")

    with open(jitter_path) as f:
        jitter = json.load(f)
    with open(pn_path) as f:
        pn = json.load(f)
    with open(ppv_path) as f:
        ppv = json.load(f)

    f0 = jitter["f0_hz"]
    tie = jitter["tie_rms_fs"]
    phase_noise = pn["total_phase_noise_dbc_hz"]

    print(f"  VCO Frequency:    {f0/1e9:.4f} GHz")
    print(f"  TIE RMS:          {tie:.2f} fs")
    print(f"  Phase Noise:      {phase_noise:.2f} dBc/Hz @ 1 MHz")
    print(f"  Source:           IHP SG13G2 PDK / Xyce simulation")

    return {"f0": f0, "tie_rms_fs": tie, "phase_noise_dbc": phase_noise}


def phase2_compile():
    """Compile all RTL + testbench with Vivado xvlog."""
    print_header("PHASE 2: Compile RTL + Testbench")

    rtl_files = glob.glob(os.path.join(RTL_DIR, "*.sv"))
    tb_files = glob.glob(os.path.join(TB_DIR, "*.sv"))
    all_files = rtl_files + tb_files

    if not all_files:
        print("[ERROR] No .sv files found!")
        sys.exit(1)

    files_str = " ".join(f'"{f}"' for f in all_files)
    cmd = rf'{VIVADO_BIN}\xvlog.bat -sv {files_str}'
    print(f"\n$ {cmd}\n")

    try:
        subprocess.run(cmd, check=True, shell=True, cwd=PROJECT_ROOT)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] xvlog compilation failed. Exit code: {e.returncode}")
        sys.exit(1)

    print("[SUCCESS] All RTL files compiled.")


def phase3_elaborate():
    """Elaborate the simulation snapshot."""
    print_header("PHASE 3: Elaborate Simulation Snapshot")

    cmd = rf'{VIVADO_BIN}\xelab.bat -debug typical -top tb_clock_mgmt -snapshot clk_mgmt_sim'
    print(f"\n$ {cmd}\n")

    try:
        subprocess.run(cmd, check=True, shell=True, cwd=PROJECT_ROOT)
        print("[SUCCESS] Elaboration completed.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] xelab elaboration failed. Exit code: {e.returncode}")
        sys.exit(1)


def phase4_simulate():
    """Run the simulation."""
    print_header("PHASE 4: Run Simulation")

    # Write TCL batch file
    tcl_path = os.path.join(PROJECT_ROOT, "case_study_run.tcl")
    with open(tcl_path, "w") as f:
        f.write("run all\n")
        f.write("quit\n")

    cmd = rf'{VIVADO_BIN}\xsim.bat clk_mgmt_sim --tclbatch case_study_run.tcl --log case_study_xsim.log'
    print(f"\n$ {cmd}\n")

    subprocess.run(cmd, shell=True, cwd=PROJECT_ROOT)

    log_path = os.path.join(PROJECT_ROOT, "case_study_xsim.log")
    if not os.path.exists(log_path):
        # Fallback to xsim.log
        log_path = os.path.join(PROJECT_ROOT, "xsim.log")

    if not os.path.exists(log_path):
        print("[ERROR] No simulation log found!")
        sys.exit(1)

    print(f"[SUCCESS] Simulation completed. Log: {log_path}")
    return log_path


def phase5_parse_results(log_path):
    """Parse the simulation log for pass/fail."""
    print_header("PHASE 5: Parse Results")

    with open(log_path) as f:
        log = f.read()

    # Extract key results
    afc_locked = "AFC LOCKED" in log
    aac_settled = "AAC SETTLED" in log
    all_passed = "ALL TESTS PASSED" in log
    errors_match = re.search(r"(\d+) TEST\(S\) FAILED", log)
    sim_errors = int(errors_match.group(1)) if errors_match else 0
    timeout = "Simulation timeout" in log

    # Print final report
    print("\n---------------------------------------------------------")
    print("     CASE STUDY VERIFICATION CLOSURE REPORT              ")
    print("---------------------------------------------------------")
    print(f"DUT: clock_mgmt_top (Adaptive Clock Management)")
    print(f"AFC Locked:         {'YES' if afc_locked else 'NO'}")
    print(f"AAC Settled:        {'YES' if aac_settled else 'NO'}")
    print(f"Simulation Timeout: {'YES' if timeout else 'NO'}")
    print(f"Test Errors:        {sim_errors}")
    print("---------------------------------------------------------")

    if all_passed and not timeout:
        print("\n[PASSED] Case Study Validation Complete. All subsystems operational.")
        return True
    else:
        reasons = []
        if not afc_locked:
            reasons.append("AFC failed to lock")
        if not aac_settled:
            reasons.append("AAC failed to settle")
        if timeout:
            reasons.append("Simulation timed out")
        if sim_errors > 0:
            reasons.append(f"{sim_errors} test error(s)")
        print(f"\n[FAILED] {'; '.join(reasons)}")
        return False


def main():
    print("=" * 80)
    print("  SiliconForge Case Study: Adaptive Multi-Domain Clock Management")
    print("  VCO: V1 Varactor LC VCO @ 10.25 GHz (IHP SG13G2)")
    print("=" * 80)

    char_data = phase1_load_characterization()
    phase2_compile()
    phase3_elaborate()
    log_path = phase4_simulate()
    success = phase5_parse_results(log_path)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
