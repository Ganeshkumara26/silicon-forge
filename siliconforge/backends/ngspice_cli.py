"""
siliconforge.backends.xyce
==========================

NgspiceCli simulator backend for SG13G2 PDK support.
Implements the Simulator contract for NgspiceCli's PSP 103.6 models.
"""

from __future__ import annotations

import os
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
from siliconforge.exceptions import SiliconForgeError, NgspiceCliNotFoundError


def _check_ngspice_cli(ngspice_path: str) -> None:
    if shutil.which(ngspice_path) is None:
        raise NgspiceCliNotFoundError(
            xyce_path=ngspice_path,
            message=(
                f"NgspiceCli executable '{ngspice_path}' not found in PATH. "
                "Install via Spack, MSYS2 MinGW, or build from source."
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
class NgspiceCliBackend(Simulator):
    """NgspiceCli simulator backend using subprocess calls.

    NgspiceCli supports PSP 103.6 models natively, enabling use of IHP PDK models.

    Usage:
        sim = NgspiceCliBackend(xyce_path="NgspiceCli")
        sim.load(netlist_lines)
        sim.transient(tstep=1e-12, tstop=100e-12)
    """

    xyce_path: str = "NgspiceCli"
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
        """Run DC analysis via NgspiceCli."""
        if not self._circuit_loaded or not self._circuit_file:
            raise SiliconForgeError("No circuit loaded")

        _check_ngspice_cli(self.xyce_path)
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
                f"NgspiceCli DC analysis failed: {result.stderr}")

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
        """Run transient analysis via NgspiceCli."""
        if not self._circuit_loaded or not self._circuit_file:
            raise SiliconForgeError("No circuit loaded")

        _check_ngspice_cli(self.xyce_path)
        start_time = time.time()

        # Ensure .TRAN card is in the file
        with open(self._circuit_file, "r") as f:
            lines = f.readlines()

        has_tran = any(line.strip().upper().startswith(".TRAN")
                       for line in lines)
        if not has_tran:
            uic_str = " UIC" if use_ic else ""
            lines.append(f"\n.TRAN {tstep} {tstop}{uic_str}\n")
            with open(self._circuit_file, "w") as f:
                f.writelines(lines)

        cmd = [self.xyce_path]
        cmd.append(self._circuit_file)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.working_dir,
        )

        if result.returncode != 0:
            raise SiliconForgeError(
                f"NgspiceCli transient failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

        dat_file = os.path.splitext(self._circuit_file)[0] + ".raw"
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
            for elem in self._reactive_elements.values():
                val = state.values.get(elem.name)
                if val is not None and stripped.lower().startswith(elem.name.lower() + " "):
                    ic_token = f"IC={val}"
                    if re.search(r"\bIC\s*=\s*\S+", stripped, re.IGNORECASE):
                        stripped = re.sub(
                            r"\bIC\s*=\s*\S+", ic_token, stripped, flags=re.IGNORECASE)
                    else:
                        stripped = stripped.rstrip() + " " + ic_token
            new_lines.append(stripped + "\n")

        with open(self._circuit_file, "w") as f:
            f.writelines(new_lines)

    def get_vector(self, name: str) -> list[float]:
        dat_file = os.path.splitext(self._circuit_file or "")[0] + ".dat"
        headers, rows = _parse_dat_file(dat_file)
        if not headers:
            return []
        col = next((i for i, h in enumerate(headers) if h == name), None)
        if col is None:
            raise KeyError(
                f"{name!r} not found in NgspiceCli output (available: {headers})"
            )
        return [float(row[col]) for row in rows if len(row) > col]

    @property
    def last_benchmark(self) -> BenchmarkMetrics | None:
        return self._last_benchmark
