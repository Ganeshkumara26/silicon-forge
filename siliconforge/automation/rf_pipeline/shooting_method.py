#!/usr/bin/env python3
"""shooting_method.py -- Time-Domain Poincaré Map PSS Engine

Implements an observable-node shooting-Newton method to find the periodic
steady-state (PSS) of an autonomous oscillator.

This robust version uses a Poincaré Map (Zero-Crossing Phase Condition) 
to decouple the period T0 from the Newton-Raphson Jacobian, preventing
singularities and divergence.
"""

import os
import sys
import subprocess
import numpy as np
import json
import argparse
import shutil
from scipy.linalg import solve

WORK_DIR = "_pss_work"


def _wsl(p):
    p = os.path.abspath(p)
    p = p.replace("\\", "/")
    if p.startswith("/mnt/"):
        return p
    d = p[0].lower()
    return f"/mnt/{d}{p[2:]}"


def run_xyce(netlist_text, name="_tmp.cir", plugin=None, timeout=300):
    path = os.path.join(WORK_DIR, name)
    with open(path, "w") as f:
        f.write(netlist_text)

    prn = path.replace(".cir", ".cir.prn")
    if os.path.exists(prn):
        os.remove(prn)

    cmd_args = ["Xyce"]
    if plugin and os.path.exists(plugin):
        plugin_basename = os.path.basename(plugin)
        plugin_dest = os.path.join(WORK_DIR, plugin_basename)
        if not os.path.exists(plugin_dest):
            shutil.copy2(plugin, plugin_dest)
        cmd_args.extend(["-plugin", f"./{plugin_basename}"])
    cmd_args.append(name)

    in_wsl = 'linux' in sys.platform.lower()
    try:
        if in_wsl:
            proc = subprocess.run(
                cmd_args, cwd=WORK_DIR, capture_output=True, text=True, timeout=timeout)
        else:
            quoted_args = [
                f"'{arg}'" if " " in arg else arg for arg in cmd_args]
            script = f"cd '{_wsl(WORK_DIR)}' && " + " ".join(quoted_args)
            proc = subprocess.run(
                ["wsl", "bash", "-c", script], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(
            f"  [ERROR] Xyce simulation timed out after {timeout}s for {name}")
        return None

    if proc.returncode != 0:
        print(f"  [ERROR] Xyce failed for {name}:\nSTDERR:\n{proc.stderr}")
        return None

    return prn


def parse_prn(prn_file):
    with open(prn_file, "r") as f:
        lines = f.readlines()
    header = None
    data = []
    started = False
    for line in lines:
        if line.startswith("Index"):
            header = [x.lower() for x in line.split()]
            started = True
        elif started and not line.startswith("End") and line.strip():
            try:
                row = [float(x) for x in line.split()]
                if len(row) >= len(header):
                    data.append(row[:len(header)])
            except ValueError:
                pass
    if not data:
        return None
    a = np.array(data)
    return {h: a[:, i] for i, h in enumerate(header)}


def get_zero_crossings(time, voltage, target_v=0.0):
    """Finds exact times where voltage crosses target_v with positive slope"""
    crossings = []
    for i in range(len(voltage)-1):
        if voltage[i] <= target_v and voltage[i+1] > target_v:
            # Linear interpolation
            slope = (voltage[i+1] - voltage[i]) / (time[i+1] - time[i])
            t = time[i] + (target_v - voltage[i]) / slope
            crossings.append(t)
    return np.array(crossings)


def build_netlist(base_lines, nodes, x0, tstop, print_nodes):
    netlist = "".join(base_lines)

    # Inject Initial Conditions
    ic_str = " ".join([f"V({n})={v:.6f}" for n, v in zip(nodes, x0)])
    netlist += f"\n.IC {ic_str}\n"

    # Run transient for exactly tstop
    netlist += f"\n.TRAN 1p {tstop*1e9}n 0 0.1p UIC\n"
    netlist += f".PRINT TRAN {print_nodes}\n.END\n"
    return netlist


def evaluate_poincare_map(base_lines, nodes, x0, T_guess, print_nodes, plugin, iter_name):
    """
    Runs a transient simulation past T_guess, finds the exact physical T0 via 
    a zero-crossing detector, and returns the state at exactly T0.
    """
    # Simulate 20% past the expected period to ensure we capture the crossing
    tstop = T_guess * 1.2
    nl = build_netlist(base_lines, nodes, x0, tstop, print_nodes)
    prn = run_xyce(nl, f"pss_{iter_name}.cir", plugin=plugin)

    data = parse_prn(prn)
    if not data:
        return None, None

    t = data["time"]
    ref_node = f"v({nodes[0].lower()})"
    ref_voltage = data[ref_node]
    target_v = x0[0]

    # Find all crossings of the initial phase condition
    zcs = get_zero_crossings(t, ref_voltage, target_v)

    # We ignore crossings that happen immediately at t=0
    valid_zcs = [zc for zc in zcs if zc > T_guess * 0.5]

    if not valid_zcs:
        print(f"  [WARNING] Poincaré Map missed zero-crossing. Expanding T_guess.")
        return None, None

    # The first valid crossing is our exact T0
    T0_exact = valid_zcs[0]

    # Extract the state at T0_exact via linear interpolation for all nodes
    x_T0 = []
    for node in nodes:
        k = f"v({node.lower()})"
        v_interp = np.interp(T0_exact, t, data[k])
        x_T0.append(v_interp)

    return np.array(x_T0), T0_exact


def main():
    parser = argparse.ArgumentParser(
        description="Shooting-Newton PSS Engine (Poincaré Map)")
    parser.add_argument("--netlist", type=str, required=True,
                        help="Path to the SPICE netlist")
    parser.add_argument("--nodes", nargs="+", required=True,
                        help="Observable state variables (e.g. out_p out_n tail)")
    parser.add_argument("--plugin", type=str, default=None,
                        help="Path to Xyce ADMS plugin")
    parser.add_argument("--tol", type=float, default=1e-5,
                        help="Convergence tolerance (V)")
    parser.add_argument("--maxiter", type=int, default=30,
                        help="Maximum Newton iterations")
    args = parser.parse_args()

    os.makedirs(WORK_DIR, exist_ok=True)

    print(f"[PSS] Starting Poincaré-Map Shooting-Newton Engine")
    print(f"[PSS] Netlist: {args.netlist}")
    print(f"[PSS] State Nodes: {args.nodes}")

    with open(args.netlist, "r") as f:
        base_lines = f.readlines()

    base_lines = [l for l in base_lines if not l.strip().upper().startswith(".TRAN")
                  and not l.strip().upper().startswith(".PRINT")
                  and not l.strip().upper().startswith(".IC")
                  and l.strip().upper() != ".END"]

    print_nodes = " ".join([f"v({n})" for n in args.nodes])

    # 1. Initial Guess (Simulate to settle, grab period and state)
    print("[PSS] Phase 1: Initializing State (Settling Run)...")
    init_netlist = "".join(base_lines)
    init_netlist += f"\n.IC v({args.nodes[0]})=1.2"
    init_netlist += f"\n.TRAN 1p 20n 0 0.1p UIC\n.PRINT TRAN {print_nodes}\n.END\n"

    prn = run_xyce(init_netlist, "pss_init.cir", plugin=args.plugin)
    if not prn:
        print("[ERROR] Initial run failed.")
        return 1

    data = parse_prn(prn)
    t = data["time"]

    ref_node = f"v({args.nodes[0].lower()})"
    mean_v = np.mean(data[ref_node])

    # SAFETY CHECK: Verify amplitude is > 0.1V at the end of simulation
    v_end = data[ref_node][int(0.9 * len(data[ref_node])):]
    vpp = np.max(v_end) - np.min(v_end)
    if vpp < 0.1:
        print(
            f"[ERROR] Oscillator failed to start. Vpp = {vpp:.3f}V. Aborting PSS extraction.")
        sys.exit(1)

    zcs = get_zero_crossings(t, data[ref_node], target_v=mean_v)

    if len(zcs) < 3:
        print("[ERROR] Failed to detect oscillations in init run.")
        return 1

    zcs_steady = zcs[-3:]
    T0_guess = np.mean(np.diff(zcs_steady))

    zc_idx = np.argmin(np.abs(t - zcs_steady[-1]))
    x0_guess = []
    for node in args.nodes:
        k = f"v({node.lower()})"
        x0_guess.append(data[k][zc_idx])
    x0_guess = np.array(x0_guess)

    print(f"[PSS] Initial Guess:")
    print(f"      f0 = {1/T0_guess/1e9:.4f} GHz (T0 = {T0_guess*1e12:.2f} ps)")
    for n, v in zip(args.nodes, x0_guess):
        print(f"      V({n}) = {v:.4f} V")

    # 2. Poincaré Shooting-Newton Loop
    print("\n[PSS] Phase 2: Poincaré Shooting Iterations...")

    N = len(args.nodes)
    x0 = x0_guess.copy()
    T0 = T0_guess

    # x0[0] is strictly fixed as the phase constraint!
    # Unknowns: U = x0[1...N-1] (Length N-1)

    for iteration in range(args.maxiter):
        x_T0, T0_exact = evaluate_poincare_map(
            base_lines, args.nodes, x0, T0, print_nodes, args.plugin, f"iter{iteration}_base")

        if x_T0 is None:
            print("[ERROR] Failed to extract Poincaré map base state.")
            return 1

        T0 = T0_exact  # Update to the physical period

        # Error array for the N-1 unknowns
        E = x_T0[1:] - x0[1:]
        err_norm = np.max(np.abs(E))

        print(
            f"  Iter {iteration+1:2d} | Error: {err_norm:.3e} V | T0: {T0*1e12:.4f} ps")

        if err_norm < args.tol:
            print(f"\n[PSS] Converged perfectly in {iteration+1} iterations!")
                    print(
                        f"  [WARNING] Oscillator has weak amplitude stability (multiplier near 1.0)")
            break

        # Compute Jacobian J ((N-1) x (N-1))
        J = np.zeros((N-1, N-1))

        delta_x = 1e-4
        for i in range(1, N):
            x0_pert = x0.copy()
            x0_pert[i] += delta_x

            x_T0_pert, T0_exact_pert = evaluate_poincare_map(
                base_lines, args.nodes, x0_pert, T0, print_nodes, args.plugin, f"iter{iteration}_pert_x{i}")

            if x_T0_pert is None:
                print(
                    f"[ERROR] Failed to extract perturbed state for node {i}.")
                return 1

            E_pert = x_T0_pert[1:] - x0_pert[1:]
            J[:, i-1] = (E_pert - E) / delta_x

        # Solve J * dU = -E
        try:
            dU = solve(J, -E)
        except np.linalg.LinAlgError:
            print(
                "[ERROR] Jacobian is singular! The proxy model might be strictly symmetrical causing zero gradients.")
            # Fallback: basic damped gradient descent if singular
            dU = -E * 0.1

        # Damping: limit voltage steps to 0.1V max

        max_dv = np.max(np.abs(dU))
        if max_dv > 0.1:
            dU = dU * (0.1 / max_dv)

        # Update Unknowns (only indices 1...N-1)
        x0[1:] += dU

    else:
        print(
            f"\n[WARNING] PSS did not converge within {args.maxiter} iterations.")

    # 3. Final Export
    print("\n[PSS] Phase 3: Exporting Steady-State Solution...")
    nl_final = build_netlist(base_lines, args.nodes, x0, T0, print_nodes)
    prn_final = run_xyce(nl_final, f"pss_final.cir", plugin=args.plugin)
    data_final = parse_prn(prn_final)

    out_dict = {
        "T0": T0,
        "f0": 1.0 / T0,
        "nodes": {},
        "convergence": {
            "iterations": iteration + 1,
            "final_error": err_norm,
            "floquet_multipliers": floquet_multipliers if 'floquet_multipliers' in locals() else []
        }
    }

    for n in args.nodes:
        k = f"v({n.lower()})"
        if k in data_final:
            out_dict["nodes"][n] = {
                "time": data_final["time"].tolist(),
                "voltage": data_final[k].tolist()
            }

    with open("pss_solution.json", "w") as f:
        json.dump(out_dict, f, indent=4)

    print(
        f"[PSS] Saved PSS solution to pss_solution.json (f0 = {out_dict['f0']/1e9:.4f} GHz)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
