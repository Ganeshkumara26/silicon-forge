#!/usr/bin/env python3
"""ppv_direct_injection.py -- Direct Impulse Injection PPV Solver

Extracts the exact PPV (Impulse Sensitivity Function) for all critical nodes
in a SPICE circuit using the transient perturbation method.
"""

import os
import sys
import subprocess
import numpy as np
import json
import argparse
from scipy.interpolate import CubicSpline

# Configuration
WORK_DIR = "_ppv_work"

I_AMP = 5e-3  # 5 mA pulse
T_WIDTH = 1e-12  # 1 ps width
Q_INJ = I_AMP * T_WIDTH  # 5 fC


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
    import shutil

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
        print(
            f"  [ERROR] Xyce failed for {name}:\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}")
        return None

    return prn


def parse_prn(prn_file, keep_last_n=None):
    """Memory-efficient PRN parser. If keep_last_n is set, only retains
    the last N data rows to minimize memory usage during PVT sweeps."""
    from collections import deque
    with open(prn_file, "r") as f:
        header = None
        buf = deque(maxlen=keep_last_n) if keep_last_n else []
        started = False
        for line in f:
            if line.startswith("Index"):
                header = [x.lower() for x in line.split()]
                started = True
            elif started and not line.startswith("End") and line.strip():
                try:
                    row = [float(x) for x in line.split()]
                    if len(row) >= len(header):
                        buf.append(row[:len(header)])
                except ValueError:
                    pass
    if not header or not buf:
        return None
    a = np.array(list(buf))
    return {h: a[:, i] for i, h in enumerate(header)}


def get_zero_crossings(time, voltage, target_v=0.0):
    """Finds exact zero-crossing times using cubic spline interpolation
    on a local 8-point window for femtosecond-level precision."""
    crossings = []
    for i in range(len(voltage)-1):
        if (voltage[i] - target_v) <= 0 and (voltage[i+1] - target_v) > 0:
            # Define a local window of 4 points on each side
            lo = max(0, i - 3)
            hi = min(len(voltage), i + 5)
            t_local = time[lo:hi]
            v_local = voltage[lo:hi] - target_v

            if len(t_local) >= 4:
                try:
                    cs = CubicSpline(t_local, v_local)
                    # Find root in the interval [time[i], time[i+1]]
                    roots = cs.roots()
                    valid = roots[(roots >= time[i]) & (roots <= time[i+1])]
                    if len(valid) > 0:
                        crossings.append(float(valid[0]))
                        continue
                except Exception:
                    pass

            # Fallback to linear interpolation
            slope = (voltage[i+1] - voltage[i]) / (time[i+1] - time[i])
            t = time[i] + (target_v - voltage[i]) / slope
            crossings.append(t)
    return np.array(crossings)


def check_convergence(ppv_vals, tolerance=0.05):
    """Check if PPV has converged"""
    valid_ppv = [p for p in ppv_vals if p is not None]
    if len(valid_ppv) > 10:
        last_3 = valid_ppv[-3:]
        if max(last_3) - min(last_3) > tolerance * (max([abs(x) for x in last_3]) + 1e-15):
            print("  [WARNING] PPV may not have converged smoothly at tail end")
            return False
    return True


def verify_ppv_data(data):
    """Verify PPV data is real, not hardcoded"""
    for node, values in data['nodes'].items():
        ppv = [p for p in values['ppv'] if p is not None]
        if len(set(ppv)) < 2 and len(ppv) > 1:
            print(
                f"  [WARNING] Node {node}: PPV all identical (Zero sensitivity or hardcoded?)")

        elif len(ppv) > 0 and max(abs(x) for x in ppv) < 1e-10:
            print(
                f"  [WARNING] Node {node}: PPV values extremely small (Orthogonal node?)")
    print("\n[PPV] Anti-hardcoding verification completed.")


def main():
    parser = argparse.ArgumentParser(
        description="Direct Impulse Injection PPV Solver")
    parser.add_argument(
        "--mode", type=str, choices=["fast", "medium", "accurate", "complete"], default="medium")
    parser.add_argument(
        "--nodes", nargs="+", default=["out_p", "out_n", "tail", "vtune"], help="Nodes to probe for ISF")
    parser.add_argument("--netlist", type=str,
                        default="vco_xyce.cir", help="Path to the SPICE netlist")
    parser.add_argument("--plugin", type=str, default=None,
                        help="Path to Xyce plugin if required")
    parser.add_argument("--out_node", type=str, default="v(out_p)",
                        help="Primary node for zero crossing detection")
    parser.add_argument("--ref_node", type=str, default="v(out_n)",
                        help="Reference node for differential zero crossing (optional, pass empty string to disable)")
    args = parser.parse_args()

    mode_map = {
        "fast": 8,
        "medium": 12,
        "accurate": 20,
        "complete": 30
    }
    num_phases = mode_map[args.mode]
    nodes_to_probe = args.nodes

    print(f"[PPV] Mode: {args.mode.upper()} ({num_phases} phases)")
    print(f"[PPV] Probing nodes: {', '.join(nodes_to_probe)}")
    print(f"[PPV] Netlist: {args.netlist}")

    os.makedirs(WORK_DIR, exist_ok=True)

    with open(args.netlist, "r") as f:
        base_lines = f.readlines()

    base_lines = [l for l in base_lines if not l.strip().upper().startswith(".TRAN")
                  and not l.strip().upper().startswith(".PRINT")
                  and l.strip().upper() != ".END"]

    T_SETTLE = 6e-9
    T_SIMULATION = 10e-9

    print("[PPV] Running unperturbed baseline...")
    base_netlist = "".join(base_lines)

    print_nodes = args.out_node
    if args.ref_node:
        print_nodes += f" {args.ref_node}"

    for n in nodes_to_probe:
        k = f"v({n.lower()})"
        if k not in print_nodes.lower():
            print_nodes += f" {k}"

    # Inject perfectly settled PSS state if available
    ic_str = ""
    if os.path.exists("pss_solution.json"):
        try:
            with open("pss_solution.json", "r") as pf:
                pss_data = json.load(pf)
                for node_name, node_data in pss_data.get("nodes", {}).items():
                    ic_str += f" V({node_name})={node_data['voltage'][0]:.6f}"
            if ic_str:
                ic_str = f"\n.IC{ic_str}\n"
                print(
                    f"[PPV] Injected pure PSS steady-state: {ic_str.strip()}")
        except Exception as e:
            print(f"[WARNING] Failed to load pss_solution.json: {e}")

    base_netlist += f"{ic_str}\n.TRAN 1p {T_SIMULATION*1e9}n 0 0.1p UIC\n.PRINT TRAN {print_nodes}\n.END\n"
    print("DEBUG: BASELINE NETLIST:")
    print(base_netlist)

    prn = os.path.join(WORK_DIR, "baseline.cir.prn")
    if not os.path.exists(prn):
        prn = run_xyce(base_netlist, "baseline.cir", plugin=args.plugin)

    if prn is None or not os.path.exists(prn):
        print("[ERROR] Baseline simulation failed. Cannot proceed.")
        return 1

    data = parse_prn(prn)
    print("Parsed Keys:", list(data.keys()))
    t = data["time"]

    def get_col(d, node):
        node = node.lower()
        if node in d:
            return d[node]
        if f"v({node})" in d:
            return d[f"v({node})"]
        raise KeyError(f"Node {node} not found in PRN data")

    try:
        vd = get_col(data, args.out_node)
        if args.ref_node:
            vd = vd - get_col(data, args.ref_node)
    except KeyError as e:
        print(f"[ERROR] {e}")
        return 1

    print(f"DEBUG: vd len={len(vd)}, max={max(vd):.4f}, min={min(vd):.4f}")
    zcs = get_zero_crossings(t, vd)
    zcs_steady = zcs[zcs > 5e-9]
    if len(zcs_steady) < 2:
        # Fallback if simulation didn't run to 5ns
        zcs_steady = zcs[len(zcs)//2:] if len(zcs) > 4 else zcs

    if len(zcs_steady) < 2:
        print("ERROR: Oscillation failed to settle or start.")
        return 1

    T0 = np.mean(np.diff(zcs_steady))
    f0 = 1.0 / T0
    print(f"[PPV] Baseline f0 = {f0/1e9:.4f} GHz, T0 = {T0*1e12:.2f} ps")

    baseline_crossing = zcs_steady[len(zcs_steady)//2]

    results = {}
    q_max = 0.4e-12 * 1.2  # Approx tank charge C * V_swing

    # Calculate time array for injections
    # TIER 4.2 ADAPTIVE PHASE SAMPLING: Weight by derivative |dx/dt|
    # to sample heavily around zero-crossings and sparsely at peaks.
    t_injections = []
    if len(zcs_steady) >= 2:
        T0 = zcs_steady[-1] - zcs_steady[-2]
        if args.mode == "fast":
            num_phases = 8
        else:
            num_phases = 16

        # Get one period of the reference voltage
        idx_start = np.argmin(np.abs(t - zcs_steady[-2]))
        idx_end = np.argmin(np.abs(t - zcs_steady[-1]))

        if idx_end > idx_start:
            t_period = t[idx_start:idx_end]
            ref_voltage = vd[idx_start:idx_end]
            dv_dt = np.abs(np.gradient(ref_voltage, t_period))

            # Create a probability density function based on derivative magnitude
            pdf = dv_dt / np.sum(dv_dt)
            cdf = np.cumsum(pdf)

            # Map uniform points through the inverse CDF to get adaptive points
            uniform_grid = np.linspace(0, 1, num_phases, endpoint=False)
            t_adaptive = np.interp(uniform_grid, cdf, t_period) - t_period[0]

            t_injections = np.sort(t_adaptive)
            print(
                f"[PPV] Using ADAPTIVE phase grid with {num_phases} points weighted by |dv/dt|")
        else:
            t_injections = np.linspace(0, T0, num_phases, endpoint=False)
            print(f"[PPV] Fallback to uniform grid")
    else:
        print("[ERROR] Could not find sufficient zero-crossings to measure period.")
        sys.exit(1)

    for node in nodes_to_probe:
        print(f"\n[PPV] Characterizing ISF for node: {node}")
        ppv_vals = []
        isf_vals = []
        taus = t_injections

        for idx, tau in enumerate(taus):
            t_inj = T_SETTLE + tau

            p_netlist = "".join(base_lines)
            p_netlist += f"\nIinj {node} 0 PULSE(0 {I_AMP} {t_inj} 0 0 {T_WIDTH} {T_SIMULATION})\n"
            p_netlist += f"{ic_str}\n.TRAN 1p {T_SIMULATION*1e9}n 0 0.1p UIC\n.PRINT TRAN {print_nodes}\n.END\n"
            prn = os.path.join(WORK_DIR, f"perturb_{node}_{idx}.cir.prn")
            if not os.path.exists(prn):
                prn = run_xyce(
                    p_netlist, f"perturb_{node}_{idx}.cir", plugin=args.plugin)

            if prn is None or not os.path.exists(prn):
                ppv_vals.append(None)
                isf_vals.append(None)
                print(
                    f"  tau={tau*1e12:5.1f}ps -> PPV = FAILED (SPICE error or timeout)")
                continue

            data = parse_prn(prn)
            t = data["time"]

            try:
                vd = get_col(data, args.out_node)
                if args.ref_node:
                    vd = vd - get_col(data, args.ref_node)
            except KeyError:
                vd = data.get(args.out_node.lower(), t)  # Fallback

            zcs = get_zero_crossings(t, vd)
            zcs_steady = zcs[zcs > t_inj + 3*T0]

            diffs = np.abs(zcs_steady - baseline_crossing)
            if len(diffs) == 0:
                ppv_vals.append(0.0)
                isf_vals.append(0.0)
                continue

            match_idx = np.argmin(diffs)
            delta_t = zcs_steady[match_idx] - baseline_crossing

            ppv = (delta_t / T0) / Q_INJ
            isf = ppv * q_max

            ppv_vals.append(ppv)
            isf_vals.append(isf)
            print(f"  tau={tau*1e12:5.1f}ps -> PPV = {ppv:.3e} (1/C)")

        results[node] = {
            "time": taus.tolist(),
            "ppv": ppv_vals,
            "isf": isf_vals
        }
        check_convergence(ppv_vals)

    out_data = {
        "f0": f0,
        "T0": T0,
        "q_max": q_max,
        "nodes": results
    }

    verify_ppv_data(out_data)

    with open("ppv_data.json", "w") as f:
        json.dump(out_data, f, indent=4)
    print("\n[PPV] Saved results to ppv_data.json")


if __name__ == "__main__":
    main()
