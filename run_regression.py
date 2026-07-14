import os
import sys
import re
import time
import glob
import subprocess


def print_header(title):
    print("\n" + "=" * 80)
    print(f"[{time.strftime('%H:%M:%S')}] {title}")
    print("=" * 80)


def run_script(script_path):
    print(f"Executing: python {script_path}")
    try:
        subprocess.run([sys.executable, script_path], check=True)
        print("[SUCCESS] Generator executed perfectly.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to execute {script_path}. Exit code: {e.returncode}")
        sys.exit(1)


def run_module(module_name, extra_args=None):
    cmd = [sys.executable, "-m", module_name]
    if extra_args:
        cmd.extend(extra_args)
    print(f"Executing: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        print("[SUCCESS] Module executed perfectly.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to execute {module_name}. Exit code: {e.returncode}")
        sys.exit(1)


VIVADO_BIN = r"D:\softwares\AMD\2026.1\Vivado\bin"

# Stale log files that must be cleaned before each run
STALE_FILES = ["xsim.log", "xelab.log", "xvlog.log", "xsim_run.tcl"]


def clean_stale_logs():
    """Remove stale simulation logs from previous runs."""
    for f in STALE_FILES:
        if os.path.exists(f):
            os.remove(f)
            print(f"  Cleaned stale: {f}")


def simulate_compilation():
    print_header("PHASE 2: UVM Compilation")
    print("Invoking Vivado xvlog to compile the UVM environment...")

    sv_files = glob.glob("uvm_verification/*.sv") + glob.glob("uvm_verification/*.svh")
    if not sv_files:
        print("[ERROR] No .sv/.svh files found in uvm_verification/")
        sys.exit(1)
    sv_files_str = " ".join(sv_files)

    cmd = rf'{VIVADO_BIN}\xvlog.bat -sv -L uvm {sv_files_str}'
    print(f"\n$ {cmd}\n")
    try:
        subprocess.run(cmd, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] xvlog compilation failed. Exit code: {e.returncode}")
        sys.exit(1)

    print("\nInvoking Vivado xelab to elaborate the snapshot...")
    cmd = rf'{VIVADO_BIN}\xelab.bat -debug typical -top tb_vco_top -snapshot vco_sim -L uvm'
    print(f"\n$ {cmd}\n")
    try:
        subprocess.run(cmd, check=True, shell=True)
        print("[SUCCESS] Compilation and Elaboration completed cleanly.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] xelab elaboration failed. Exit code: {e.returncode}")
        sys.exit(1)


def simulate_execution():
    print_header("PHASE 3: Digital UVM Simulation")

    # Write a TCL batch file for xsim to avoid positional arg parsing issues
    tcl_path = "xsim_run.tcl"
    with open(tcl_path, "w") as f:
        f.write("run all\n")
        f.write("quit\n")

    cmd = rf'{VIVADO_BIN}\xsim.bat vco_sim --tclbatch {tcl_path}'
    print(f"\n$ {cmd}\n")
    result = subprocess.run(cmd, shell=True)

    if not os.path.exists("xsim.log"):
        print("[ERROR] xsim.log not found. XSIM failed to produce output.")
        sys.exit(1)

    print("[SUCCESS] UVM Simulation Finished.")


def parse_coverage():
    print_header("PHASE 4: Coverage Extraction")

    print("Parsing generated simulation logs (xsim.log)...")

    sva_violations = 0
    uvm_errors = 0
    uvm_fatals = 0
    sim_completed = False

    if os.path.exists("xsim.log"):
        with open("xsim.log", "r") as f:
            log_content = f.read()

        # Count SVA violations
        sva_violations = log_content.count("VCO Amplitude Violation")

        # Parse UVM report summary
        err_match = re.search(r"UVM_ERROR\s*:\s*(\d+)", log_content)
        if err_match:
            uvm_errors = int(err_match.group(1))

        fatal_match = re.search(r"UVM_FATAL\s*:\s*(\d+)", log_content)
        if fatal_match:
            uvm_fatals = int(fatal_match.group(1))

        # Check simulation completed
        sim_completed = "$finish" in log_content or "Exiting xsim" in log_content
    else:
        print("[WARNING] xsim.log not found.")

    print("\n---------------------------------------------------------")
    print("               VERIFICATION CLOSURE REPORT                 ")
    print("---------------------------------------------------------")
    print(f"DUT: vco_rnm_dut")
    print(f"Simulation Completed:             {'YES' if sim_completed else 'NO'}")
    print(f"Physical SVA Bounds Violations:   {sva_violations}")
    print(f"UVM_ERROR count:                  {uvm_errors}")
    print(f"UVM_FATAL count:                  {uvm_fatals}")
    print("---------------------------------------------------------")

    total_failures = sva_violations + uvm_errors + uvm_fatals

    if not sim_completed:
        print("\n[FAILED] Simulation did not complete.")
        sys.exit(1)

    if total_failures > 0:
        reasons = []
        if sva_violations > 0:
            reasons.append(f"{sva_violations} SVA violation(s)")
        if uvm_errors > 0:
            reasons.append(f"{uvm_errors} UVM_ERROR(s)")
        if uvm_fatals > 0:
            reasons.append(f"{uvm_fatals} UVM_FATAL(s)")
        print(f"\n[FAILED] Verification failed: {', '.join(reasons)}")
        sys.exit(1)

    print("\n[PASSED] All assertions clean. 0 UVM errors. Silicon Sign-Off Approved.")


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    generator_dir = os.path.join(base_dir, "siliconforge", "asset_generator")

    # Clean stale logs from previous runs
    clean_stale_logs()

    # Check for --case-study flag
    extra_pipeline_args = []
    if "--case-study" in sys.argv:
        cs_idx = sys.argv.index("--case-study")
        cs_path = os.path.join(base_dir, "tests", "case_study")
        if cs_idx + 1 < len(sys.argv) and not sys.argv[cs_idx + 1].startswith("--"):
            cs_path = sys.argv[cs_idx + 1]
        extra_pipeline_args = ["--case-study", cs_path]

    # PHASE 1: GENERATION
    print_header("PHASE 1: Verification Asset Generation (via Physical End-to-End Flow)")

    print("Running Core Mathematical Pipeline...")
    run_module("siliconforge.core.pipeline", extra_pipeline_args)

    print("\nGenerating SystemVerilog Assets from Characterization Data...")
    assets_script = os.path.join(generator_dir, "generate_assets.py")
    coverage_script = os.path.join(generator_dir, "generate_coverage.py")

    run_script(assets_script)
    run_script(coverage_script)

    # PHASE 2: COMPILATION
    simulate_compilation()

    # PHASE 3: SIMULATION
    simulate_execution()

    # PHASE 4: COVERAGE PARSING
    parse_coverage()


if __name__ == "__main__":
    main()
