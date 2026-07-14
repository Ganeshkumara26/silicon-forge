import re
import time
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.integrate import solve_ivp

from siliconforge.backends.base import (
    Simulator,
    CircuitState,
    ReactiveKind,
    ReactiveElement,
    TransientResult,
    BenchmarkMetrics
)
from siliconforge.exceptions import UnsupportedCircuitError


def _parse_spice_number(token: str) -> float:
    token = token.upper()
    m = re.match(r'^([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)(.*)$', token)
    if not m:
        raise UnsupportedCircuitError(f"Malformed value: {token}")

    num_str, suffix = m.groups()
    val = float(num_str)

    if suffix.startswith('MEG'):
        return val * 1e6
    if suffix.startswith('F'):
        return val * 1e-15
    if suffix.startswith('P'):
        return val * 1e-12
    if suffix.startswith('N'):
        return val * 1e-9
    if suffix.startswith('U'):
        return val * 1e-6
    if suffix.startswith('M'):
        return val * 1e-3
    if suffix.startswith('K'):
        return val * 1e3
    if suffix.startswith('G'):
        return val * 1e9
    if suffix.startswith('T'):
        return val * 1e12

    return val


@dataclass
class _TankCircuit:
    c_name: str
    l_name: str
    r_name: str | None
    node_p: str
    node_n: str
    c_val: float
    l_val: float
    r_val: float
    ic_c: float
    ic_l: float
    l_sign: float


def _rhs(t, y, c, l, g):
    v, i_l = y
    return [-g*v/c - i_l/c, v/l]


class ReferenceOdeBackend(Simulator):
    """
    A pure numpy/scipy `Simulator` backend for evaluating a source-free 
    parallel RLC tank analytically, ensuring the matrix-free numerical 
    tools can be developed and unit-tested without an external ngspice binary.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self._tank = None
        self._last_benchmark = None
        self._results = None
        self._elements = {}

    def _require_loaded(self):
        if self._tank is None:
            raise RuntimeError("Circuit not loaded")

    def load(self, netlist_lines: Sequence[str]) -> None:
        self.reset()

        merged = []
        for line in netlist_lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('+') and merged:
                merged[-1] += " " + line[1:]
            else:
                merged.append(line)

        in_subckt = False
        top_level = []
        for line in merged:
            if line.upper().startswith('.SUBCKT'):
                in_subckt = True
            elif line.upper().startswith('.ENDS'):
                in_subckt = False
            elif not in_subckt:
                top_level.append(line)

        c_name, l_name, r_name = None, None, None
        c_val, l_val, r_val = 0.0, 0.0, 0.0
        ic_c, ic_l = 0.0, 0.0

        c_nodes, l_nodes, r_nodes = None, None, None

        elements = {}

        for line in top_level:
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            letter = name[0].upper()
            if letter == 'C':
                if c_name is not None:
                    raise UnsupportedCircuitError("Two capacitors")
                c_name = name
                c_nodes = (parts[1], parts[2])
                c_val = _parse_spice_number(parts[3])
                for p in parts[4:]:
                    if p.upper().startswith('IC='):
                        ic_c = float(p[3:])
                elements[name] = ReactiveElement(
                    name, ReactiveKind.CAPACITOR, parts[1], parts[2])
            elif letter == 'L':
                if l_name is not None:
                    raise UnsupportedCircuitError("Two inductors")
                l_name = name
                l_nodes = (parts[1], parts[2])
                l_val = _parse_spice_number(parts[3])
                for p in parts[4:]:
                    if p.upper().startswith('IC='):
                        ic_l = float(p[3:])
                elements[name] = ReactiveElement(
                    name, ReactiveKind.INDUCTOR, parts[1], parts[2])
            elif letter == 'R':
                if r_name is not None:
                    raise UnsupportedCircuitError("Two resistors")
                r_name = name
                r_nodes = (parts[1], parts[2])
                r_val = _parse_spice_number(parts[3])
                if r_val == 0:
                    raise UnsupportedCircuitError("Zero ohm resistor")
            elif letter in ('V', 'I'):
                raise UnsupportedCircuitError("Independent source rejected")

        if c_name is None or l_name is None:
            raise UnsupportedCircuitError(
                f"Missing {'capacitor' if c_name is None else 'inductor'}")

        nodes = set(c_nodes)
        if set(l_nodes) != nodes:
            raise UnsupportedCircuitError("Inductor on unrelated nodes")
        if r_nodes is not None and set(r_nodes) != nodes:
            raise UnsupportedCircuitError("Resistor on different nodes")

        l_sign = 1.0 if l_nodes[0] == c_nodes[0] else -1.0

        self._tank = _TankCircuit(
            c_name=c_name, l_name=l_name, r_name=r_name,
            node_p=c_nodes[0], node_n=c_nodes[1],
            c_val=c_val, l_val=l_val, r_val=r_val,
            ic_c=ic_c, ic_l=ic_l, l_sign=l_sign
        )
        self._elements = elements

    @property
    def reactive_elements(self):
        return self._elements

    @property
    def last_benchmark(self) -> BenchmarkMetrics | None:
        return self._last_benchmark

    def operating_point(self) -> CircuitState:
        self._require_loaded()
        t0 = time.time()
        state = CircuitState(
            values={self._tank.c_name: 0.0, self._tank.l_name: 0.0}, time=0.0)
        self._last_benchmark = BenchmarkMetrics(
            wall_time_s=time.time() - t0,
            converged=True,
            n_timepoints=1
        )
        return state

    def inject_state(self, state: CircuitState) -> None:
        self._require_loaded()
        for k, v in state.values.items():
            if k == self._tank.c_name:
                self._tank.ic_c = v
            elif k == self._tank.l_name:
                self._tank.ic_l = v
            else:
                raise KeyError(f"Unknown element: {k}")

    def transient(self, tstep: float, tstop: float, use_ic: bool = True, extra_signals: Sequence[str] = ()) -> TransientResult:
        self._require_loaded()
        if tstep <= 0 or tstop <= 0:
            raise ValueError("tstep and tstop must be positive")

        t0 = time.time()

        c = self._tank.c_val
        l = self._tank.l_val
        g = 1.0 / self._tank.r_val if self._tank.r_val != 0 else 0.0

        y0 = [self._tank.ic_c, self._tank.ic_l *
              self._tank.l_sign] if use_ic else [0.0, 0.0]

        # Adjust t_eval so it cleanly ends at tstop
        n_steps = int(round(tstop / tstep))
        t_eval = np.linspace(0, tstop, n_steps + 1)

        sol = solve_ivp(
            _rhs, (0, tstop), y0, t_eval=t_eval, args=(c, l, g),
            method='Radau', rtol=1e-9, atol=1e-12
        )

        v_tank = list(sol.y[0])
        i_l = list(sol.y[1] * self._tank.l_sign)
        t_list = list(sol.t)

        v_key = f"v({self._tank.node_p.lower()},{self._tank.node_n.lower()})"
        i_key = f"i({self._tank.l_name.lower()})"

        signals = {
            "time": t_list,
            v_key: v_tank,
            i_key: i_l
        }

        if self._tank.node_n == '0':
            signals[f"v({self._tank.node_p.lower()})"] = v_tank

        self._results = {
            "time": t_list,
            **signals
        }

        final_state = CircuitState(
            values={
                self._tank.c_name: v_tank[-1],
                self._tank.l_name: i_l[-1]
            },
            time=t_list[-1]
        )

        self._last_benchmark = BenchmarkMetrics(
            wall_time_s=time.time() - t0,
            converged=sol.success,
            n_timepoints=len(t_list)
        )

        return TransientResult(
            time=t_list,
            signals=signals,
            final_state=final_state,
            n_timepoints=len(t_list)
        )

    def get_vector(self, name: str) -> list[float]:
        self._require_loaded()
        if self._results is None:
            raise RuntimeError("Call transient first")
        if name not in self._results:
            raise KeyError(f"Vector {name} not found")
        return self._results[name]
