#!/usr/bin/env python3
"""spice_runner.py — Practical ngspice/WSL interface for SiliconForge regression.

Runs ngspice through WSL, extracts oscillation frequency from transient
simulations via zero-crossing detection or .meas tran output.

Designed to work in the validated environment:
  WSL (Ubuntu 22.04) + ngspice 46+ + IHP SG13G2 PDK at /tmp/ihp_sg13g2
"""

import os
import re
import subprocess
import tempfile
import shutil
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List


def _wsl_path(windows_path):
    """Convert Windows path to WSL path."""
    p = str(Path(windows_path).absolute())
    p = p.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        return f"/mnt/{drive}{p[2:]}"
    return p


def run_ngspice(netlist_path: str, workdir: str = None,
                pdk_root: str = "/tmp", timeout: int = 300) -> Tuple[str, str]:
    """Run ngspice batch mode through WSL.

    Parameters
    ----------
    netlist_path : str
        Path to the SPICE netlist (Windows or WSL format)
    workdir : str
        Working directory for simulation (default: same as netlist)
    pdk_root : str
        PDK root directory inside WSL (default: /tmp)
    timeout : int
        Maximum simulation time in seconds

    Returns
    -------
    (stdout, stderr) from ngspice
    """
    netlist_abs = Path(netlist_path).absolute()
    netlist_wsl = _wsl_path(netlist_abs)

    if workdir is None:
        workdir = str(netlist_abs.parent)
    workdir_wsl = _wsl_path(workdir)

    cmd = (
        f"cd '{workdir_wsl}' && export PDK_ROOT='{pdk_root}' "
        f"&& ngspice -b '{netlist_wsl}' 2>&1"
    )

    # Detect if already running inside WSL (Unix-only os.uname)
    try:
        in_wsl = os.path.exists("/mnt/WSL") or "microsoft" in os.uname().release.lower()
    except AttributeError:
        in_wsl = False  # Windows — always use wsl subprocess
    
    try:
        if in_wsl:
            result = subprocess.run(
                ["bash", "-c", cmd],
                capture_output=True, text=True, timeout=timeout
            )
        else:
            result = subprocess.run(
                ["wsl", "bash", "-c", cmd],
                capture_output=True, text=True, timeout=timeout
            )
        return result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return "", f"Simulation timed out after {timeout}s"
    except FileNotFoundError:
        return "", "WSL not found — ngspice must run through WSL on this system"


def extract_frequency_from_meas(output: str) -> Optional[float]:
    """Extract frequency from ngspice `meas tran` output.

    Looks for lines like:
        freq = 1.021448e+10
    """
    match = re.search(r'freq\s*=\s*([eE\d.+-]+)', output)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def extract_frequency_from_stdout(output: str) -> Optional[float]:
    """Extract frequency from ngspice stdout (alternative format)."""
    patterns = [
        r'freq\s*=\s*([eE\d.+-]+)',
        r'frequency\s*=\s*([eE\d.+-]+)',
        r'([eE\d.+-]+)\s*[Hh][Zz]',
    ]
    for pat in patterns:
        match = re.search(pat, output)
        if match:
            try:
                val = float(match.group(1))
                if 1e6 < val < 1e13:
                    return val
            except ValueError:
                continue
    return None


def extract_waveform_from_raw(raw_path: str) -> Optional[dict]:
    """Parse ngspice ASCII raw file for waveform data.

    Returns dict with 'time' and voltage node arrays, or None.
    """
    if not os.path.exists(raw_path):
        return None

    try:
        with open(raw_path, "r") as f:
            content = f.read()
    except (IOError, UnicodeDecodeError):
        return None

    # Look for the data section after "Values:"
    sections = content.split("Values:")
    if len(sections) < 2:
        return None

    lines = sections[1].strip().split("\n")
    signals = {}
    current_var = None
    data_values = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("Index") or "://" in line:
            continue
        parts = line.split()
        if len(parts) == 2:
            try:
                idx = int(parts[0])
                val = float(parts[1])
                if idx == 0 and data_values:
                    for k, v in signals.items():
                        signals[k] = np.array(v)
                    return signals
                if current_var:
                    data_values.append(val)
            except ValueError:
                if len(parts) == 2 and not parts[0].replace(".", "").isdigit():
                    current_var = parts[0]
                    signals[current_var] = []
        elif len(parts) >= 2 and current_var:
            try:
                signals.setdefault(current_var, []).append(float(parts[-1]))
            except ValueError:
                continue

    return signals if signals else None


def measure_frequency_zero_crossings(time: np.ndarray, voltage: np.ndarray,
                                     n_periods: int = 10) -> Optional[float]:
    """Measure frequency from zero-crossing analysis.

    Parameters
    ----------
    time : array
        Time points
    voltage : array
        Voltage waveform (single-ended, will be centered)
    n_periods : int
        Number of periods to average over

    Returns
    -------
    Frequency in Hz, or None if not enough crossings found
    """
    v_centered = voltage - np.mean(voltage)
    crossings = []
    for i in range(len(v_centered) - 1):
        if v_centered[i] <= 0 and v_centered[i + 1] > 0:
            slope = (v_centered[i + 1] - v_centered[i]) / (time[i + 1] - time[i])
            t_cross = time[i] + (0 - v_centered[i]) / slope
            crossings.append(t_cross)

    if len(crossings) < 3:
        return None

    periods = np.diff(crossings[1:min(n_periods + 2, len(crossings))])
    if len(periods) == 0:
        return None

    avg_period = np.mean(periods)
    if avg_period <= 0:
        return None

    return 1.0 / avg_period


def create_meas_netlist(netlist_path: str, output_path: str = None,
                        tstop_ns: float = 50.0) -> str:
    """Create a netlist variant with .meas tran frequency extraction.

    Takes an existing netlist, strips .control/.endc blocks, and adds
    a .tran card + .meas tran cards that compute frequency from zero-crossings.
    """
    with open(netlist_path, "r") as f:
        lines = f.readlines()

    # Strip .control/.endc blocks (they conflict with .meas)
    cleaned = []
    in_control = False
    has_tran = False
    for line in lines:
        s = line.strip().lower()
        if s.startswith(".control"):
            in_control = True
            continue
        if s.startswith(".endc"):
            in_control = False
            continue
        if in_control:
            continue
        if s.startswith(".tran"):
            has_tran = True
            continue
        cleaned.append(line)

    # Detect output nodes and crossing condition
    out_node = None
    out_node_n = None
    for line in cleaned:
        ls = line.strip().lower()
        if ls.startswith("*") or ls.startswith("."):
            continue
        # Look for differential output nodes
        if "out_p" in ls:
            out_node = "out_p"
            if "out_n" in ls:
                out_node_n = "out_n"
                break
        # Look for single-ended output nodes
        if out_node is None and "out" in ls and not ls.startswith("m") and not ls.startswith("x"):
            parts = ls.split()
            for p in parts:
                if p.startswith("out") and p not in ("out",):
                    out_node = p
                    break

    # Fallback: use first node in first subckt call or first MOS gate
    if out_node is None:
        for line in cleaned:
            ls = line.strip().lower()
            if ls.startswith("x") and len(ls.split()) >= 4:
                out_node = ls.split()[3]  # 4th token is first output
                break
    if out_node is None:
        out_node = "out1"  # ultimate fallback

    # Build measurement cards
    meas_lines = [f"\n* Added by SiliconForge spice_runner\n"]
    meas_lines.append(f".tran 0.5p {tstop_ns}n\n")

    # Detect VDD from supply declaration for threshold calculation
    vdd = 1.2  # default
    for line in cleaned:
        ls = line.strip().lower()
        if ls.startswith("vdd") or (ls.startswith("v") and "dc" in ls and "vdd" in ls):
            parts = ls.split()
            for i, p in enumerate(parts):
                if p == "dc" and i + 1 < len(parts):
                    try:
                        vdd = float(parts[i + 1])
                    except ValueError:
                        pass
                    break
            if vdd != 1.2:
                break
    threshold = vdd / 2.0

    if out_node_n:
        # Differential: use v(out_p) = v(out_n) crossing, measure single-ended VPP
        meas_lines.extend([
            f".meas tran t1 WHEN v({out_node})=v({out_node_n}) CROSS=3\n",
            f".meas tran t2 WHEN v({out_node})=v({out_node_n}) CROSS=5\n",
            f".meas tran freq PARAM='1/(t2-t1)'\n",
            f".meas tran vpp_p PP v({out_node})\n",
            f".meas tran vpp_n PP v({out_node_n})\n",
        ])
    else:
        # Single-ended: use VDD/2 as crossing threshold
        meas_lines.extend([
            f".meas tran t1 WHEN v({out_node})={threshold:g} RISE=3\n",
            f".meas tran t2 WHEN v({out_node})={threshold:g} RISE=5\n",
            f".meas tran freq PARAM='1/(t2-t1)'\n",
            f".meas tran vpp_pp PP v({out_node})\n",
        ])

    # Insert before .end
    final = []
    for line in cleaned:
        if line.strip().lower() == ".end":
            final.extend(meas_lines)
        final.append(line)

    if output_path is None:
        base = Path(netlist_path).stem
        output_path = str(Path(netlist_path).parent / f"{base}_meas.cir")

    with open(output_path, "w") as f:
        f.writelines(final)

    return output_path


class SpiceResult:
    """Result from a SPICE simulation run."""

    def __init__(self):
        self.frequency_hz: Optional[float] = None
        self.vpp: Optional[float] = None
        self.converged: bool = False
        self.waveforms: Optional[dict] = None
        self.raw_output: str = ""
        self.elapsed_s: float = 0.0


def run_oscillator_frequency(netlist_path: str, workdir: str = None,
                              pdk_root: str = "/tmp",
                              tstop_ns: float = 50.0) -> SpiceResult:
    """Run a VCO netlist and measure its oscillation frequency.

    Tries .meas tran first, falls back to zero-crossing analysis.

    Parameters
    ----------
    netlist_path : str
        Path to SPICE netlist
    workdir : str
        Working directory (default: netlist parent)
    pdk_root : str
        PDK root in WSL
    tstop_ns : float
        Transient simulation time in nanoseconds

    Returns
    -------
    SpiceResult with frequency_hz populated if successful
    """
    import time
    result = SpiceResult()
    t0 = time.time()

    # Create meas netlist
    meas_path = create_meas_netlist(netlist_path, tstop_ns=tstop_ns)

    # Run ngspice
    stdout, stderr = run_ngspice(meas_path, workdir=workdir, pdk_root=pdk_root)
    result.raw_output = stdout + "\n" + stderr
    result.elapsed_s = time.time() - t0

    # Try to extract frequency from .meas output
    freq = extract_frequency_from_meas(stdout)
    if freq is None:
        freq = extract_frequency_from_stdout(stdout)

    if freq and 1e6 < freq < 1e13:
        result.frequency_hz = freq
        result.converged = True

    # Try to extract VPP
    vpp_match = re.search(r'vpp_pp\s*=\s*([eE\d.+-]+)', stdout)
    if vpp_match:
        result.vpp = float(vpp_match.group(1))

    # Cleanup
    for ext in ["", ".raw", ".lis"]:
        try:
            p = Path(meas_path).with_suffix(ext) if ext else Path(meas_path)
            if p.exists() and str(p) != str(Path(netlist_path).absolute()):
                p.unlink(missing_ok=True)
        except OSError:
            pass

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SPICE Frequency Runner")
    parser.add_argument("netlist", help="Path to SPICE netlist")
    parser.add_argument("--pdk-root", default="/tmp")
    parser.add_argument("--tstop-ns", type=float, default=50.0)
    args = parser.parse_args()

    r = run_oscillator_frequency(args.netlist, pdk_root=args.pdk_root,
                                  tstop_ns=args.tstop_ns)
    print(f"Converged: {r.converged}")
    print(f"Frequency: {r.frequency_hz/1e9:.4f} GHz" if r.frequency_hz else "Frequency: N/A")
    print(f"VPP: {r.vpp:.3f} V" if r.vpp else "VPP: N/A")
    print(f"Time: {r.elapsed_s:.1f}s")


# =============================================================================
# Phase Noise via SPICE .noise Analysis
# =============================================================================

def create_noise_netlist(netlist_path: str, output_path: str = None,
                         f_start_hz: float = 100.0, f_stop_hz: float = 1e9,
                         n_points_per_decade: int = 10,
                         tstop_ns: float = 50.0) -> str:
    """Create a netlist variant with .noise analysis for phase noise estimation.

    The .noise analysis computes the output noise spectral density S_v(f) [V^2/Hz].
    Phase noise is then estimated as: L(f) = S_v(f) / (V_rms^2)

    where V_rms is the RMS oscillation amplitude (from transient analysis).

    Parameters
    ----------
    netlist_path : str
        Original SPICE netlist (transient analysis)
    output_path : str
        Output path for the noise netlist
    f_start_hz, f_stop_hz : float
        Frequency sweep range for .noise analysis
    n_points_per_decade : int
        Number of points per decade in .noise sweep
    tstop_ns : float
        Transient simulation time (needed to reach steady-state before .noise)

    Returns
    -------
    str : Path to the generated noise netlist
    """
    with open(netlist_path, "r") as f:
        lines = f.readlines()

    # Strip .control/.endc blocks
    cleaned = []
    in_control = False
    for line in lines:
        s = line.strip().lower()
        if s.startswith(".control"):
            in_control = True
            continue
        if s.startswith(".endc"):
            in_control = False
            continue
        if in_control:
            continue
        # Remove existing .tran lines
        if s.startswith(".tran"):
            continue
        cleaned.append(line)

    # Find the output node
    out_node = "out_p"
    has_complementary = False
    for line in cleaned:
        ls = line.strip().lower()
        if ls.startswith("*") or ls.startswith("."):
            continue
        if "out_n" in ls:
            has_complementary = True
        if "out_p" in ls:
            break

    # Find V supply for small-signal source
    v_supply = "vdd"

    # Build noise analysis cards
    noise_lines = [
        f"\n* Added by SiliconForge spice_runner — noise analysis\n",
        f".tran 0.5p {tstop_ns}n\n",
        f".meas tran freq WHEN v({out_node})={0.6 if not has_complementary else 'v(out_n)'} RISE=3\n",
        f".meas tran t1 WHEN v({out_node})={0.6 if not has_complementary else 'v(out_n)'} RISE=3\n",
        f".meas tran t2 WHEN v({out_node})={0.6 if not has_complementary else 'v(out_n)'} RISE=5\n",
        f".meas tran freq_param PARAM='1/(t2-t1)'\n",
        f".meas tran vout_rms RMS v({out_node})\n",
        f".control\n",
        f"set filetype=ascii\n",
        f"run\n",
        f"noise v({out_node}) {v_supply} dec {n_points_per_decade} {f_start_hz} {f_stop_hz}\n",
        f"setplot noise2\n",
        f"wrdata noise_output.txt onoise_spectrum\n",
        f"quit\n",
        f".endc\n",
    ]

    # Insert before .end
    final = []
    for line in cleaned:
        if line.strip().lower() == ".end":
            final.extend(noise_lines)
        final.append(line)

    if output_path is None:
        base = Path(netlist_path).stem
        output_path = str(Path(netlist_path).parent / f"{base}_noise.cir")

    with open(output_path, "w") as f:
        f.writelines(final)

    return output_path


def parse_noise_output(workdir: str = ".") -> Optional[dict]:
    """Parse ngspice noise analysis output file.

    Parameters
    ----------
    workdir : str
        Directory containing noise_output.txt

    Returns
    -------
    dict with keys 'frequencies_hz', 'noise_v2_per_hz', 'phase_noise_dbch'
    or None if file not found or parse failed
    """
    noise_file = Path(workdir) / "noise_output.txt"
    if not noise_file.exists():
        return None

    try:
        with open(noise_file, "r") as f:
            lines = f.readlines()

        freqs = []
        noise_v2 = []

        for line in lines:
            line = line.strip()
            if not line or line.startswith("*") or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    freq = float(parts[0])
                    noise = float(parts[1])
                    freqs.append(freq)
                    noise_v2.append(noise)
                except ValueError:
                    continue

        if not freqs:
            return None

        return {
            "frequencies_hz": np.array(freqs),
            "noise_v2_per_hz": np.array(noise_v2),
        }
    except (IOError, UnicodeDecodeError):
        return None


def compute_phase_noise_from_noise_data(noise_data: dict,
                                         v_rms_v: float = 0.6,
                                         carrier_freq_hz: float = 10e9) -> dict:
    """Convert output noise spectral density to phase noise L(f).

    For a harmonic oscillator, the relationship between output voltage noise
    and phase noise is:
        L(f_offset) = S_v(f_offset) / (V_rms^2)

    where S_v is the single-sided noise PSD and V_rms is the oscillation
    amplitude. This is valid for small noise (phase noise << 1 radian).

    Parameters
    ----------
    noise_data : dict
        Output from parse_noise_output() with frequencies_hz and noise_v2_per_hz
    v_rms_v : float
        RMS oscillation amplitude [V] (from transient analysis)
    carrier_freq_hz : float
        Carrier frequency [Hz]

    Returns
    -------
    dict with 'offsets_hz', 'phase_noise_dbch', 'thermal_floor_dbch'
    """
    freqs = noise_data["frequencies_hz"]
    s_v = noise_data["noise_v2_per_hz"]

    v_rms_sq = v_rms_v ** 2
    if v_rms_sq <= 0:
        v_rms_sq = 1e-30

    # Phase noise L(f) = S_v(f) / Vrms^2, then convert to dBc/Hz
    pn_linear = s_v / v_rms_sq
    pn_db = 10.0 * np.log10(np.maximum(pn_linear, 1e-30))

    # Estimate thermal floor as the median of the last 20% of points
    n_points = len(pn_db)
    floor_start = int(0.8 * n_points)
    thermal_floor = float(np.median(pn_db[floor_start:])) if n_points > 5 else None

    return {
        "offsets_hz": freqs,
        "phase_noise_dbch": pn_db,
        "thermal_floor_dbch": thermal_floor,
        "carrier_freq_hz": carrier_freq_hz,
        "v_rms_used_v": v_rms_v,
    }


def run_noise_analysis(netlist_path: str, workdir: str = None,
                        pdk_root: str = "/tmp",
                        f_start_hz: float = 100.0,
                        f_stop_hz: float = 1e9,
                        tstop_ns: float = 50.0) -> dict:
    """Run SPICE .noise analysis and return phase noise data.

    Parameters
    ----------
    netlist_path : str
        Path to original SPICE netlist
    workdir : str
        Working directory for simulation
    pdk_root : str
        PDK root in WSL
    f_start_hz, f_stop_hz : float
        Noise analysis frequency range
    tstop_ns : float
        Transient simulation time before .noise

    Returns
    -------
    dict with keys:
        'converged' : bool
        'phase_noise' : dict with offsets_hz, phase_noise_dbch, thermal_floor_dbch
        'frequency_hz' : float (from transient)
        'vpp' : float (from transient)
        'raw_output' : str
        'elapsed_s' : float
    """
    import time
    t0 = time.time()
    result = {
        "converged": False,
        "phase_noise": None,
        "frequency_hz": None,
        "vpp": None,
        "raw_output": "",
        "elapsed_s": 0.0,
    }

    if workdir is None:
        workdir = str(Path(netlist_path).parent)

    # Create noise netlist
    noise_path = create_noise_netlist(
        netlist_path, f_start_hz=f_start_hz, f_stop_hz=f_stop_hz,
        tstop_ns=tstop_ns
    )

    # Run ngspice
    stdout, stderr = run_ngspice(noise_path, workdir=workdir, pdk_root=pdk_root)
    result["raw_output"] = stdout + "\n" + stderr
    result["elapsed_s"] = time.time() - t0

    # Extract frequency from transient
    freq = extract_frequency_from_meas(stdout)
    if freq is None:
        freq = extract_frequency_from_stdout(stdout)
    if freq:
        result["frequency_hz"] = freq

    # Extract VPP
    vpp_match = re.search(r'vpp_pp\s*=\s*([eE\d.+-]+)', stdout)
    if vpp_match:
        result["vpp"] = float(vpp_match.group(1))

    # Extract V RMS
    vrms_match = re.search(r'vout_rms\s*=\s*([eE\d.+-]+)', stdout)
    vrms = float(vrms_match.group(1)) if vrms_match else None

    # Parse noise output
    noise_data = parse_noise_output(workdir)

    if noise_data is not None:
        v_rms = vrms if vrms and vrms > 0 else (result["vpp"] / (2 * np.sqrt(2)) if result["vpp"] else 0.6)
        pn_result = compute_phase_noise_from_noise_data(
            noise_data, v_rms_v=v_rms, carrier_freq_hz=result["frequency_hz"] or 10e9
        )
        result["phase_noise"] = pn_result
        result["converged"] = True

    # Cleanup
    try:
        Path(noise_path).unlink(missing_ok=True)
        for suffix in ["noise_output.txt", ".raw"]:
            p = Path(workdir) / suffix
            if p.exists():
                p.unlink(missing_ok=True)
    except OSError:
        pass

    return result


# =============================================================================
# Phase Noise via Transient Analysis (correct method for oscillators)
# =============================================================================

def create_transient_pn_netlist(netlist_path: str, output_path: str = None,
                                 tstop_ns: float = 100.0) -> str:
    """Create a netlist for transient-based phase noise extraction.

    For oscillators, .noise analysis doesn't work (no stable DC point).
    Instead, we run a long transient and extract phase noise from the
    zero-crossing times.

    Parameters
    ----------
    netlist_path : str
        Original SPICE netlist
    output_path : str
        Output path for the modified netlist
    tstop_ns : float
        Transient simulation time in nanoseconds (longer = more periods = better statistics)

    Returns
    -------
    str : Path to the generated netlist
    """
    with open(netlist_path, "r") as f:
        lines = f.readlines()

    # Strip .control/.endc blocks
    cleaned = []
    in_control = False
    for line in lines:
        s = line.strip().lower()
        if s.startswith(".control"):
            in_control = True
            continue
        if s.startswith(".endc"):
            in_control = False
            continue
        if in_control:
            continue
        if s.startswith(".tran"):
            continue
        cleaned.append(line)

    # Find output node
    out_node = "out_p"
    for line in cleaned:
        ls = line.strip().lower()
        if ls.startswith("*") or ls.startswith("."):
            continue
        if "out_p" in ls:
            break

    # Detect VDD for threshold
    vdd = 1.2
    for line in cleaned:
        ls = line.strip().lower()
        if ls.startswith("vdd") or (ls.startswith("v") and "dc" in ls and "vdd" in ls):
            parts = ls.split()
            for i, p in enumerate(parts):
                if p == "dc" and i + 1 < len(parts):
                    try:
                        vdd = float(parts[i + 1])
                    except ValueError:
                        pass
                    break
            if vdd != 1.2:
                break
    threshold = vdd / 2.0

    # Build transient + measurement cards
    meas_lines = [
        f"\n* Added by SiliconForge — transient phase noise extraction\n",
        f".tran 0.2p {tstop_ns}n\n",
        f".control\n",
        f"run\n",
        f"wrdata transient_pn.txt TIME v({out_node})\n",
        f"quit\n",
        f".endc\n",
    ]

    final = []
    for line in cleaned:
        if line.strip().lower() == ".end":
            final.extend(meas_lines)
        final.append(line)

    if output_path is None:
        base = Path(netlist_path).stem
        output_path = str(Path(netlist_path).parent / f"{base}_pn.cir")

    with open(output_path, "w") as f:
        f.writelines(final)

    return output_path


def parse_transient_data(workdir: str = ".") -> Optional[dict]:
    """Parse transient waveform data from ngspice wrdata output.

    Returns
    -------
    dict with 'time' and 'voltage' arrays, or None
    """
    data_file = Path(workdir) / "transient_pn.txt"
    if not data_file.exists():
        return None

    try:
        with open(data_file, "r") as f:
            lines = f.readlines()

        times = []
        voltages = []

        for line in lines:
            line = line.strip()
            if not line or line.startswith("*") or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    t = float(parts[0])
                    v = float(parts[1])
                    times.append(t)
                    voltages.append(v)
                except ValueError:
                    continue

        if not times:
            return None

        return {
            "time": np.array(times),
            "voltage": np.array(voltages),
        }
    except (IOError, UnicodeDecodeError):
        return None


def extract_zero_crossings(time: np.ndarray, voltage: np.ndarray,
                           threshold: float = 0.6) -> np.ndarray:
    """Extract times where voltage crosses threshold (rising edge).

    Uses linear interpolation for sub-timestep accuracy.

    Parameters
    ----------
    time : array
        Time points
    voltage : array
        Voltage waveform
    threshold : float
        Crossing threshold (typically VDD/2)

    Returns
    -------
    array of crossing times
    """
    crossings = []
    for i in range(len(voltage) - 1):
        if voltage[i] < threshold and voltage[i + 1] >= threshold:
            frac = (threshold - voltage[i]) / (voltage[i + 1] - voltage[i] + 1e-30)
            t_cross = time[i] + frac * (time[i + 1] - time[i])
            crossings.append(t_cross)
    return np.array(crossings)


def compute_phase_noise_from_transient(netlist_path: str, workdir: str = None,
                                        pdk_root: str = "/tmp",
                                        tstop_ns: float = 100.0,
                                        threshold: float = None) -> dict:
    """Compute phase noise from transient simulation of an oscillator.

    This is the CORRECT method for oscillator phase noise in ngspice.
    The .noise analysis doesn't work for oscillators because there's no
    stable DC operating point.

    Method:
    1. Run long transient (many oscillation periods)
    2. Extract zero-crossing times
    3. Compute period jitter (variation in instantaneous period)
    4. Convert to phase noise L(f) using the 1/f^2 relationship

    Parameters
    ----------
    netlist_path : str
        Path to SPICE netlist
    workdir : str
        Working directory
    pdk_root : str
        PDK root in WSL
    tstop_ns : float
        Transient simulation time (ns). More periods = better statistics.
    threshold : float
        Zero-crossing threshold (default: auto-detect VDD/2)

    Returns
    -------
    dict with keys:
        'converged' : bool
        'frequency_hz' : float
        'vpp' : float
        'period_jitter_s' : float (RMS period jitter)
        'phase_noise_1mhz' : float (L(f) at 1 MHz offset, dBc/Hz)
        'phase_noise_data' : dict with offsets_hz and phase_noise_dbch
        'raw_output' : str
        'elapsed_s' : float
    """
    import time as time_mod
    t0 = time_mod.time()

    result = {
        "converged": False,
        "frequency_hz": None,
        "vpp": None,
        "period_jitter_s": None,
        "phase_noise_1mhz": None,
        "phase_noise_data": None,
        "raw_output": "",
        "elapsed_s": 0.0,
    }

    if workdir is None:
        workdir = str(Path(netlist_path).parent)

    # Create transient netlist
    pn_path = create_transient_pn_netlist(netlist_path, tstop_ns=tstop_ns)

    # Run ngspice
    stdout, stderr = run_ngspice(pn_path, workdir=workdir, pdk_root=pdk_root)
    result["raw_output"] = stdout + "\n" + stderr
    result["elapsed_s"] = time_mod.time() - t0

    # Parse transient data
    data = parse_transient_data(workdir)

    if data is not None:
        time_arr = data["time"]
        voltage = data["voltage"]

        # Auto-detect threshold if not provided
        if threshold is None:
            v_min = np.min(voltage)
            v_max = np.max(voltage)
            threshold = (v_min + v_max) / 2.0

        # Extract zero crossings
        crossings = extract_zero_crossings(time_arr, voltage, threshold)

        if len(crossings) >= 3:
            # Compute instantaneous periods
            periods = np.diff(crossings)

            # Compute period jitter
            T_avg = np.mean(periods)
            T_jitter = np.std(periods, ddof=1) if len(periods) > 1 else 0.0

            result["period_jitter_s"] = T_jitter
            result["vpp"] = float(np.max(voltage) - np.min(voltage))

            if T_avg > 0 and T_jitter > 0:
                f0 = 1.0 / T_avg
                result["frequency_hz"] = f0

                # Phase noise from period jitter
                # For 1/f^2 region: L(f) = 2 * (f0/f)^2 * (sigma_T / T)^2
                sigma_T_over_T = T_jitter / T_avg

                offsets = np.logspace(3, 9, 50)  # 1 kHz to 1 GHz
                pn_db = np.zeros_like(offsets)

                for i, f_off in enumerate(offsets):
                    if f_off < f0:  # Valid below carrier
                        pn_linear = 2.0 * (f0 / f_off) ** 2 * sigma_T_over_T ** 2
                        pn_db[i] = 10.0 * np.log10(max(pn_linear, 1e-30))
                    else:
                        pn_db[i] = -200.0  # Above carrier

                result["phase_noise_data"] = {
                    "offsets_hz": offsets,
                    "phase_noise_dbch": pn_db,
                    "carrier_freq_hz": f0,
                    "period_jitter_s": T_jitter,
                    "method": "transient_zero_crossing",
                }

                # PN at 1 MHz
                idx_1mhz = np.argmin(np.abs(offsets - 1e6))
                result["phase_noise_1mhz"] = float(pn_db[idx_1mhz])

                result["converged"] = True

    # Cleanup
    try:
        Path(pn_path).unlink(missing_ok=True)
        for suffix in ["transient_pn.txt", ".raw"]:
            p = Path(workdir) / suffix
            if p.exists():
                p.unlink(missing_ok=True)
    except OSError:
        pass

    return result
