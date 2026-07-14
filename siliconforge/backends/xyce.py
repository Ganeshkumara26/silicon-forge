"""
siliconforge.backends.xyce
==========================

Xyce simulator backend for SG13G2 PDK support.
Implements the Simulator contract for Xyce's PSP 103.6 models.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
import tempfile
import time
import shutil
from dataclasses import dataclass, field
from typing import Sequence

from siliconforge.backends.base import (
    BenchmarkMetrics,
    CircuitState,
    ReactiveElement,
    ReactiveKind,
    Simulator,
    TransientResult,
)
from siliconforge.exceptions import SiliconForgeError, XyceNotFoundError


def _windows_to_wsl_path(path: str) -> str:
    if platform.system() != "Windows" or not path:
        return path
    path = path.replace(chr(92), "/")  # replace backslash with forward slash
    if path.startswith("/mnt/"):
        return path
    drive = path[0].lower()
    rest = path[2:]
    return f"/mnt/{drive}{rest}"


def _run_xyce(xyce_path: str, args: Sequence[str], cwd: str) -> subprocess.CompletedProcess:
    if shutil.which(xyce_path):
        return subprocess.run(
            [xyce_path, *args],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    wsl_cwd = _windows_to_wsl_path(cwd)
    cmd_str = "cd '" + wsl_cwd + "' && Xyce " + " ".join(args)
    return subprocess.run(
        ["wsl", "-e", "bash", "-c", cmd_str],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _check_xyce(xyce_path: str) -> None:
    if shutil.which(xyce_path):
        return
    if platform.system() == "Windows" and shutil.which("wsl"):
        try:
            result = subprocess.run(
                ["wsl", "-e", "bash", "-c", "which " + xyce_path],
                capture_output=True,
            )
            if result.returncode == 0:
                return
        except Exception:
            pass
    raise XyceNotFoundError(
        xyce_path=xyce_path,
        message=(
            "Xyce executable '" + xyce_path + "' not found in Windows PATH or WSL. "
            "Install Xyce in WSL with: sudo apt-get install xyce"
        ),
    )


def _write_temp_netlist(netlist_lines: Sequence[str], working_dir: str) -> str:
    fd, circuit_file = tempfile.mkstemp(suffix=".cir", dir=working_dir)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(netlist_lines))
    return circuit_file


def _parse_top_level_elements(netlist_lines: Sequence[str]) -> dict[str, ReactiveElement]:
    elements: dict[str, ReactiveElement] = {}
    for line in netlist_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("*") or stripped.startswith("."):
            continue
        parts = stripped.split()
        if len(parts) < 4:
            continue
        name = parts[0]
        elem_type = name[0].lower() if name else ""
        if elem_type == "c":
            elements[name] = ReactiveElement(
                name=name,
                kind=ReactiveKind.CAPACITOR,
                node_p=parts[1],
                node_n=parts[2],
            )
        elif elem_type == "l":
            elements[name] = ReactiveElement(
                name=name,
                kind=ReactiveKind.INDUCTOR,
                node_p=parts[1],
                node_n=parts[2],
            )
    return elements


def _parse_output_file(circuit_file: str) -> tuple[list[str], list[list[str]]]:
    base = os.path.splitext(circuit_file)[0]
    candidates = [f"{base}.raw", f"{base}.dat"]
    for path in candidates:
        if os.path.exists(path):
            return _parse_dat_file(path)
    return [], []


def _parse_dat_file(dat_path: str) -> tuple[list[str], list[list[str]]]:
    rows: list[list[str]] = []
    headers: list[str] = []
    if not os.path.exists(dat_path):
        return headers, rows
    with open(dat_path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("*"):
                continue
            parts = stripped.split()
            if not parts:
                continue
            if headers and parts[0].replace(".", "").replace("e", "").replace("-", "").replace("+", "").isdigit():
                rows.append(parts)
            elif not headers:
                headers = parts
    return headers, rows


@dataclass
class XyceBackend(Simulator):
    """Xyce simulator backend using subprocess calls.

    Xyce supports PSP 103.6 models natively, enabling use of IHP PDK models.

    Usage:
        sim = XyceBackend(xyce_path="Xyce")
        sim.load(netlist_lines)
        sim.transient(tstep=1e-12, tstop=100e-12)
    """

    xyce_path: str = "Xyce"
    working_dir: str = field(default_factory=lambda: os.getcwd())
    plugins: list[str] = field(default_factory=list)
    _reactive_elements: dict[str, ReactiveElement] = field(
        default_factory=dict)
    _last_benchmark: BenchmarkMetrics | None = None
    _circuit_loaded: bool = False
    _circuit_file: str | None = None

    def load(self, netlist_lines: Sequence[str]) -> None:
        """Write netlist to file and prepare for simulation."""
        if not os.path.isdir(self.working_dir):
            os.makedirs(self.working_dir, exist_ok=True)

        self._reactive_elements = {}
        self._circuit_file = _write_temp_netlist(
            netlist_lines, self.working_dir)
        self._reactive_elements = _parse_top_level_elements(netlist_lines)
        self._circuit_loaded = True

    def reset(self) -> None:
        """Clear circuit state and temp netlist."""
        self._reactive_elements = {}
        self._circuit_loaded = False
        self._last_benchmark = None
        if self._circuit_file and os.path.exists(self._circuit_file):
            os.remove(self._circuit_file)
        self._circuit_file = None

    @property
    def reactive_elements(self) -> dict[str, ReactiveElement]:
        return self._reactive_elements

    def operating_point(self) -> CircuitState:
        """Run DC analysis via Xyce."""
        if not self._circuit_loaded or not self._circuit_file:
            raise SiliconForgeError("No circuit loaded")

        _check_xyce(self.xyce_path)
        start_time = time.time()

        cmd = [self.xyce_path]
        if self.plugins:
            cmd.append("-plugin")
            cmd.append(",".join(self.plugins))
        cmd.extend(["-dc", self._circuit_file])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.working_dir,
        )

        if result.returncode != 0:
            raise SiliconForgeError(
                f"Xyce DC analysis failed: {result.stderr}")

        lis_file = os.path.splitext(self._circuit_file)[0] + ".lis"
        values: dict[str, float] = {}

        if os.path.exists(lis_file):
            with open(lis_file) as f:
                for line in f:
                    if "voltage" in line.lower():
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                values[parts[0]] = float(
                                    parts[-2] if len(parts) > 2 else parts[1])
                            except (ValueError, IndexError):
                                pass

        bm = BenchmarkMetrics(wall_time_s=time.time() -
                              start_time, converged=True)
        self._last_benchmark = bm
        return CircuitState(values=values, time=0.0)

    def transient(
        self,
        tstep: float,
        tstop: float,
        use_ic: bool = True,
        extra_signals: Sequence[str] = (),
    ) -> TransientResult:
        """Run transient analysis via Xyce."""
        if not self._circuit_loaded or not self._circuit_file:
            raise SiliconForgeError("No circuit loaded")

        _check_xyce(self.xyce_path)
        start_time = time.time()

        # Ensure .TRAN card is in the file
        with open(self._circuit_file, "r") as f:
            lines = f.readlines()

        has_tran = any(line.strip().upper().startswith(".TRAN")
                       for line in lines)
        if not has_tran:
            uic_str = " UIC" if use_ic else ""
            lines.append(
                "\n* Robust Xyce Nonlinear Solver Options for Verilog-A Models\n")
            lines.append(
                ".OPTIONS NONLIN GMIN=1e-10 MAXSTEP=100 DELVMAX=0.1\n")
            lines.append(".OPTIONS TIMEINT METHOD=2\n")
            lines.append(".OPTIONS DEVICE TRANDELMIN=1e-15\n")

            max_step = tstep / 10.0
            lines.append(f".TRAN {tstep} {tstop} 0 {max_step}{uic_str}\n")
            with open(self._circuit_file, "w") as f:
                f.writelines(lines)

        cmd = []
        if self.plugins:
            cmd.append("-plugin")
            cmd.append(",".join(self.plugins))
        cmd.append(os.path.basename(self._circuit_file))

        result = _run_xyce(self.xyce_path, cmd, self.working_dir)

        if result.returncode != 0:
            raise SiliconForgeError(
                f"Xyce transient failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

        dat_file = os.path.splitext(self._circuit_file)[0] + ".dat"
        headers: list[str] = []
        rows: list[list[str]] = []
        if os.path.exists(dat_file):
            headers, rows = _parse_dat_file(dat_file)

        signals: dict[str, list[float]] = {}
        time_points: list[float] = []
        if headers and rows:
            time_idx = next((i for i, h in enumerate(
                headers) if h.lower() == "time"), 0)
            for i, row in enumerate(rows):
                try:
                    time_points.append(float(row[time_idx]))
                except (ValueError, IndexError):
                    pass
                for j, h in enumerate(headers):
                    if h.lower() == "time":
                        continue
                    try:
                        signals.setdefault(h, []).append(float(row[j]))
                    except (ValueError, IndexError):
                        pass

        final_values: dict[str, float] = {}
        for name, series in signals.items():
            if series:
                final_values[name] = series[-1]

        n_points = len(time_points)
        bm = BenchmarkMetrics(
            wall_time_s=time.time() - start_time,
            converged=n_points > 0,
            n_timepoints=n_points,
        )
        self._last_benchmark = bm
        return TransientResult(
            time=time_points,
            signals=signals,
            final_state=CircuitState(values=final_values, time=tstop),
            n_timepoints=n_points,
        )

    def inject_state(self, state: CircuitState) -> None:
        if not self._circuit_file or not os.path.exists(self._circuit_file):
            raise SiliconForgeError("No circuit loaded")

        with open(self._circuit_file, "r") as f:
            lines = f.readlines()

        new_lines = []
        for line in lines:
            stripped = line.strip()
            matched = False
            for elem in self._reactive_elements.values():
                val = state.values.get(elem.name)
                if val is None:
                    continue
                if stripped.lower().startswith(elem.name.lower() + " "):
                    ic_token = f"IC={val}"
                    if re.search(r"\bIC\s*=\s*\S+", stripped, re.IGNORECASE):
                        stripped = re.sub(
                            r"\bIC\s*=\s*\S+", ic_token, stripped, flags=re.IGNORECASE)
                    else:
                        stripped = stripped.rstrip() + " " + ic_token
                    matched = True
                    break
            new_lines.append(stripped + "\n")

        with open(self._circuit_file, "w") as f:
            f.writelines(new_lines)

    def get_vector(self, name: str) -> list[float]:
        headers, rows = _parse_output_file(self._circuit_file or "")
        if not headers:
            raise KeyError(
                f"{name!r} not found in Xyce output: no analysis result file exists yet. "
                "Run operating_point() or transient() first."
            )
        col = next((i for i, h in enumerate(headers) if h == name), None)
        if col is None:
            raise KeyError(
                f"{name!r} not found in Xyce output (available: {headers})"
            )
        return [float(row[col]) for row in rows if len(row) > col]

    def ac_analysis(
        self,
        n_points: int = 100,
        f_start_hz: float = 1e6,
        f_end_hz: float | None = None,
    ) -> tuple[list[float], dict[str, list[float]]]:
        """Run AC analysis via Xyce and return frequency response.

        Returns
        -------
        tuple[list[float], dict[str, list[float]]]
            (frequencies_hz, {signal_name: values})
        """
        if not self._circuit_loaded or not self._circuit_file:
            raise SiliconForgeError("No circuit loaded")

        _check_xyce(self.xyce_path)
        start_time = time.time()

        f_end = f_end_hz if f_end_hz else f_start_hz * 1000

        ac_line = f".AC DEC {n_points} {f_start_hz} {f_end}"
        with open(self._circuit_file, "r") as f:
            lines = f.readlines()
        if not any(l.strip().upper().startswith(".AC") for l in lines):
            lines.append(f"\n{ac_line}\n")
            with open(self._circuit_file, "w") as f:
                f.writelines(lines)

        cmd = [self.xyce_path, self._circuit_file]
        result = subprocess.run(cmd, capture_output=True,
                                text=True, cwd=self.working_dir)

        if result.returncode != 0:
            raise SiliconForgeError(
                f"Xyce AC analysis failed:\n{result.stderr}")

        ac_dat = os.path.splitext(self._circuit_file)[0] + ".ac.dat"
        headers, rows = [], []
        if os.path.exists(ac_dat):
            headers, rows = _parse_dat_file(ac_dat)

        freqs: list[float] = []
        signals: dict[str, list[float]] = {}

        if headers and rows:
            freq_idx = next((i for i, h in enumerate(headers)
                            if "hz" in h.lower() or "freq" in h.lower()), 0)
            freqs = [float(r[freq_idx]) for r in rows if len(r) > freq_idx]
            for j, h in enumerate(headers):
                if j != freq_idx:
                    signals[h] = [float(r[j]) for r in rows if len(r) > j]

        self._last_benchmark = BenchmarkMetrics(
            wall_time_s=time.time() - start_time,
            converged=len(freqs) > 0,
            n_timepoints=len(freqs),
        )
        return freqs, signals

    def noise_analysis(
        self,
        output_node: str,
        source_name: str,
        f_start_hz: float = 1e3,
        f_end_hz: float = 1e7,
    ) -> tuple[list[float], dict[str, list[float]]]:
        """Run noise analysis via Xyce and return noise spectrum.

        Parameters
        ----------
        output_node : str
            Node at which to compute output noise (e.g., "out_p")
        source_name : str
            Noise source name (e.g., "R_TANK" or "tail")
        f_start_hz, f_end_hz : float
            Frequency sweep range

        Returns
        -------
        tuple[list[float], dict[str, list[float]]]
            (frequencies_hz, {"inoise": [...], "onoise": [...]})
        """
        if not self._circuit_loaded or not self._circuit_file:
            raise SiliconForgeError("No circuit loaded")

        _check_xyce(self.xyce_path)
        start_time = time.time()

        noise_line = f".NOISE {output_node} {source_name} DEC 100 {f_start_hz} {f_end_hz}"
        with open(self._circuit_file, "r") as f:
            lines = f.readlines()
        if not any(l.strip().upper().startswith(".NOISE") for l in lines):
            lines.append(f"\n{noise_line}\n")
            with open(self._circuit_file, "w") as f:
                f.writelines(lines)

        cmd = [self.xyce_path, self._circuit_file]
        result = subprocess.run(cmd, capture_output=True,
                                text=True, cwd=self.working_dir)

        if result.returncode != 0:
            raise SiliconForgeError(
                f"Xyce NOISE analysis failed:\n{result.stderr}")

        noise_dat = os.path.splitext(self._circuit_file)[
            0] + f".no.{source_name}.dat"
        headers, rows = [], []
        if os.path.exists(noise_dat):
            headers, rows = _parse_dat_file(noise_dat)

        freqs: list[float] = []
        signals: dict[str, list[float]] = {}

        if headers and rows:
            freq_idx = next((i for i, h in enumerate(headers)
                            if "hz" in h.lower() or "freq" in h.lower()), 0)
            freqs = [float(r[freq_idx]) for r in rows if len(r) > freq_idx]
            for j, h in enumerate(headers):
                if j != freq_idx:
                    signals[h] = [float(r[j]) for r in rows if len(r) > j]

        self._last_benchmark = BenchmarkMetrics(
            wall_time_s=time.time() - start_time,
            converged=len(freqs) > 0,
            n_timepoints=len(freqs),
        )
        return freqs, signals

    @property
    def last_benchmark(self) -> BenchmarkMetrics | None:
        return self._last_benchmark
