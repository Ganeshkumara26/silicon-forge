#!/usr/bin/env python3
"""ppv_suite.py -- Unified PPV/Phase Noise Oscillator Analysis Suite

The master CLI orchestrator that unifies the PSS, PPV, PNOISE, JITTER, 
and Verilog-A generation engines into a single seamless tool.
"""

import sys
import argparse
import subprocess


def run_cmd(cmd):
    print(f"\n[SUITE] Executing: {' '.join(cmd)}")
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        print(f"[SUITE ERROR] Command failed with exit code {proc.returncode}")
        sys.exit(proc.returncode)


def cmd_extract(args):
    print("\n" + "="*50)
    print(" SUITE: EXTRACTION PIPELINE (PSS -> PPV)")
    print("="*50)

    # 1. PSS (Shooting Method)
    pss_cmd = [sys.executable, "shooting_method.py",
               "--netlist", args.netlist,
               "--nodes"] + args.nodes
    if args.plugin:
        pss_cmd.extend(["--plugin", args.plugin])

    print("[SUITE] -> Step 1: PSS State Extraction")
    # run_cmd(pss_cmd) # Bypassed temporarily while we wait for damped PSS to finish testing

    # 2. PPV Direct Injection
    ppv_cmd = [sys.executable, "ppv_direct_injection.py",
               "--netlist", args.netlist,
               "--mode", args.mode,
               "--nodes"] + args.nodes
    if args.plugin:
        ppv_cmd.extend(["--plugin", args.plugin])

    print("[SUITE] -> Step 2: PPV/ISF Sweep")
    run_cmd(ppv_cmd)

    print("\n[SUITE] Extraction Complete. Data saved to ppv_data.json")


def cmd_analyze(args):
    print("\n" + "="*50)
    print(" SUITE: ANALYSIS PIPELINE (PNOISE -> JITTER)")
    print("="*50)

    # 1. PNOISE Breakdown
    pn_cmd = [sys.executable, "ppv_breakdown.py",
              "--input", args.ppv,
              "--offset", str(args.offset)]

    print("[SUITE] -> Step 1: Phase Noise Breakdown")
    run_cmd(pn_cmd)

    # 2. Jitter Engine
    jit_cmd = [sys.executable, "ppv_jitter.py",
               "--pnoise", "phase_noise_breakdown.json",
               "--ppv", args.ppv,
               "--fmin", str(args.fmin),
               "--fmax", str(args.fmax)]

    print("\n[SUITE] -> Step 2: Time-Domain Jitter Integration")
    run_cmd(jit_cmd)

    print("\n[SUITE] Analysis Complete.")


def cmd_veriloga(args):
    print("\n" + "="*50)
    print(" SUITE: VERILOG-A MACRO-MODEL GENERATOR")
    print("="*50)

    va_cmd = [sys.executable, "gen_verilog_a.py",
              "--input", args.ppv,
              "--output", args.output]

    run_cmd(va_cmd)


def cmd_sweep(args):
    print("\n" + "="*50)
    print(" SUITE: PVT SWEEP ORCHESTRATOR")
    print("="*50)

    pvt_cmd = [sys.executable, "pvt_sweep.py",
               "--netlist", args.netlist,
               "--plugin", args.plugin,
               "--nodes"] + args.nodes

    run_cmd(pvt_cmd)


def main():
    parser = argparse.ArgumentParser(
        description="Unified Oscillator Analysis Suite")
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Sub-commands")

    # EXTRACT COMMAND
    parser_ex = subparsers.add_parser(
        "extract", help="Run PSS and PPV extraction")
    parser_ex.add_argument("--netlist", type=str,
                           required=True, help="Target netlist")
    parser_ex.add_argument("--nodes", nargs="+",
                           required=True, help="Nodes to track")
    parser_ex.add_argument("--plugin", type=str, help="Xyce ADMS plugin path")
    parser_ex.add_argument(
        "--mode", type=str, choices=["fast", "accurate"], default="accurate")

    # ANALYZE COMMAND
    parser_an = subparsers.add_parser(
        "analyze", help="Run PNOISE and Jitter engines")
    parser_an.add_argument(
        "--ppv", type=str, default="ppv_data.json", help="Input PPV json")
    parser_an.add_argument("--offset", type=float,
                           default=1e6, help="Phase noise offset (Hz)")
    parser_an.add_argument("--fmin", type=float, default=10e3,
                           help="Jitter lower int band (Hz)")
    parser_an.add_argument("--fmax", type=float, default=1e9,
                           help="Jitter upper int band (Hz)")

    # VERILOGA COMMAND
    parser_va = subparsers.add_parser(
        "veriloga", help="Generate Verilog-A model")
    parser_va.add_argument(
        "--ppv", type=str, default="ppv_data.json", help="Input PPV json")
    parser_va.add_argument("--output", type=str,
                           default="oscillator.va", help="Output .va file")

    # SWEEP COMMAND
    parser_sw = subparsers.add_parser(
        "sweep", help="Run full PVT corner sweep")
    parser_sw.add_argument("--netlist", type=str,
                           required=True, help="Target netlist")
    parser_sw.add_argument("--plugin", type=str,
                           required=True, help="Xyce ADMS plugin path")
    parser_sw.add_argument("--nodes", nargs="+",
                           required=True, help="Nodes to track")

    args = parser.parse_args()

    if args.command == "extract":
        cmd_extract(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "veriloga":
        cmd_veriloga(args)
    elif args.command == "sweep":
        cmd_sweep(args)


if __name__ == "__main__":
    main()
