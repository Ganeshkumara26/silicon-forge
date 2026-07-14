"""
siliconforge.backends.base
============================

Backend-agnostic abstraction layer for circuit simulation evaluation.

`Simulator` is the abstract contract every concrete simulation engine
(ngspice today; others later, only if actually needed) must implement.
Higher layers -- the netlist utilities, and eventually the shooting-
Newton / matrix-free GMRES outer loop -- are written against this
contract only, never against a concrete backend directly. That is what
lets the numerics layer be developed and unit-tested against a
lightweight in-process reference backend in environments (such as this
sandbox, today) where the real ngspice shared library isn't installed.

Provenance note
----------------
This module did not exist as an uploaded file. It was reconstructed by
reading the actual `import` statements and call sites in the two files
that *were* genuinely uploaded (`ngspice_shared.py`, `netlist_utils.py`)
and inferring the minimum contract that makes both of them work exactly
as written, rather than from any narrative description of prior work.
See docs/HANDOFF.md for why that distinction matters in this project.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class ReactiveKind(Enum):
    """The two element types whose stored-energy variable (capacitor
    voltage / inductor current) makes up the state vector this
    project's state-injection and, eventually, Floquet/PPV machinery
    operates on."""

    CAPACITOR = "c"
    INDUCTOR = "l"


@dataclass(frozen=True)
class ReactiveElement:
    """One top-level reactive element discovered in a netlist by
    `siliconforge.netlist_utils.find_reactive_elements`.

    `node_p`/`node_n` are stored exactly as written in the netlist;
    `read_vector`/`alter_target` apply ngspice's own lower-casing of
    identifiers (SPICE syntax is case-insensitive, but ngspice's
    internal vector database is not) so callers never have to think
    about case themselves.
    """

    name: str
    kind: ReactiveKind
    node_p: str
    node_n: str

    @property
    def read_vector(self) -> str:
        """ngspice vector name to read this element's state variable
        from after a `.op` or `.tran` analysis.

        Capacitors use the two-argument differential form
        ``v(node_p,node_n)`` unconditionally (not just ``v(node_p)``),
        so this is correct even when `node_n` is not ground -- ngspice
        treats ``v(n,0)`` and ``v(n)`` as equivalent, so there is no
        special-casing needed for the ground-referenced case.

        Inductors are read by element name, ``i(name)``: inductor
        current is itself an MNA unknown in modified nodal analysis
        (unlike capacitor current, which is why capacitors are read by
        node voltage instead).
        """
        if self.kind is ReactiveKind.CAPACITOR:
            return f"v({self.node_p.lower()},{self.node_n.lower()})"
        return f"i({self.name.lower()})"

    @property
    def alter_target(self) -> str:
        """``alter`` left-hand-side target that overwrites this
        element's initial-condition parameter in the already-loaded,
        in-memory circuit, e.g. ``"@c1[ic]"``. Identical form for both
        capacitors and inductors -- both expose an ``ic`` instance
        parameter to ``alter``."""
        return f"@{self.name.lower()}[ic]"


@dataclass
class CircuitState:
    """A snapshot of every reactive element's state variable at a
    single point in time. `values` maps element name -> value in SI
    units (volts for capacitors, amps for inductors). This is the
    object type `Simulator.inject_state` consumes and
    `Simulator.operating_point` / `TransientResult.final_state`
    produce -- the common currency the shooting-Newton loop will
    iterate on once it exists."""

    values: dict[str, float] = field(default_factory=dict)
    time: float = 0.0


@dataclass
class TransientResult:
    """Full output of one `Simulator.transient` call."""

    time: list[float]
    signals: dict[str, list[float]]
    final_state: CircuitState
    n_timepoints: int


@dataclass
class BenchmarkMetrics:
    """Timing/convergence metadata every `Simulator` call populates,
    so solver performance is measured from the start rather than
    bolted on later. Backends populate whatever fields they actually
    know; the rest keep their defaults."""

    wall_time_s: float
    converged: bool
    n_timepoints: int = 0
    note: str = ""


class Simulator(abc.ABC):
    """Abstract backend contract. A concrete `Simulator` wraps exactly
    one underlying circuit-simulation engine (or, for
    `ReferenceOdeBackend`, a closed-form/numerically-integrated ODE
    standing in for one) and exposes it through this fixed surface."""

    @abc.abstractmethod
    def load(self, netlist_lines: Sequence[str]) -> None:
        """Load (or replace) the active circuit. Implementations
        should discover and cache reactive elements here."""

    @abc.abstractmethod
    def reset(self) -> None:
        """Discard the active circuit and any cached results. Does not
        need to tear down the underlying engine instance itself."""

    @abc.abstractmethod
    def operating_point(self) -> CircuitState:
        """Run a DC operating-point analysis; return the resulting
        state of every reactive element."""

    @abc.abstractmethod
    def transient(
        self,
        tstep: float,
        tstop: float,
        use_ic: bool = True,
        extra_signals: Sequence[str] = (),
    ) -> TransientResult:
        """Run a transient analysis from t=0 to `tstop`. When `use_ic`
        is True, integration starts from each element's currently-set
        IC rather than from a fresh DC operating point -- the mode the
        shooting-Newton state-transition evaluator will need."""

    @abc.abstractmethod
    def inject_state(self, state: CircuitState) -> None:
        """Overwrite the IC of every reactive element named in
        `state.values`, in place, in the already-loaded circuit."""

    @abc.abstractmethod
    def get_vector(self, name: str) -> list[float]:
        """Return the most recently computed values of an arbitrary
        named signal, not limited to reactive-element state."""

    @property
    @abc.abstractmethod
    def last_benchmark(self) -> BenchmarkMetrics | None:
        """Benchmark metadata from the most recent `operating_point`
        or `transient` call, or `None` if neither has run yet."""
