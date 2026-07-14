"""
siliconforge.backends.ngspice_shared
=======================================

Concrete `Simulator` backend that drives ngspice through its shared-library
C API (``libngspice.so``), as opposed to spawning the ``ngspice`` executable
as a subprocess per evaluation.

Why the shared library and not subprocess + .raw files
----------------------------------------------------------
Module 3's matrix-free GMRES needs the directional derivative

    A v  ~=  [F(x + eps*v) - F(x)] / eps

evaluated once per Krylov basis vector, and a full Shooting-Newton outer
iteration typically needs several GMRES iterations before the residual
||x(T) - x(0)|| converges. Each directional-derivative evaluation is one
state-transition evaluation: inject a perturbed state, integrate one
period T, read back the resulting state. If each of those evaluations
paid the cost of spawning a new ``ngspice`` process, re-parsing the
(potentially large, post-layout-extracted) netlist text, and re-building
internal model data structures from scratch, a single outer Newton step
could cost seconds to minutes before any GMRES iteration even begins.
Driving ``libngspice.so`` in-process lets a perturbed evaluation be
exactly: one ``alter`` command (microseconds) + one ``tran ... uic``
command (the actual integration cost, which is unavoidable) -- nothing
else is re-parsed or re-allocated.

The libngspice C API itself
------------------------------
This module binds the API documented in ``/usr/include/ngspice/sharedspice.h``
(installed by the ``libngspice0-dev`` package). The struct layouts and
callback signatures below are transcribed directly from that header, not
from memory or secondhand documentation, specifically because subtly
wrong ctypes struct field ordering is a classic source of silent memory
corruption rather than a clean exception. Two behaviours were additionally
verified empirically against a running ngspice 42 instance (see
``docs/M1_simulation_backend.md``, Section "Verification of the alter/ic
mechanism") rather than assumed from the header comments alone:

1. ``alter @<device>[ic]=<value>`` overwrites a capacitor's or inductor's
   initial-condition value in the already-loaded, in-memory circuit, and
   a subsequent ``tran ... uic`` genuinely restarts the integration at
   t=0 using the new value (not a continuation of the previous run's
   time axis).
2. Without ``bg_run``, ``ngSpice_Command`` blocks the calling thread for
   the full duration of the analysis; results are guaranteed available
   via ``ngGet_Vec_Info`` the moment the call returns. This lets the
   entire backend avoid the BGThreadRunning polling loop the API
   otherwise supports, which materially simplifies this implementation.

Process-wide singleton constraint
------------------------------------
libngspice maintains process-global state. Constructing more than one
``NgspiceSharedBackend`` in the same Python process is not supported by
ngspice itself (this is a limitation of ngspice, not of this wrapper --
every other libngspice binding, e.g. ngspyce, documents the same
constraint). This module enforces it explicitly rather than allowing a
confusing failure deep inside the second instance's first command.
"""

from __future__ import annotations

import ctypes
import logging
import time
from typing import Sequence

from siliconforge.backends.base import (
    BenchmarkMetrics,
    CircuitState,
    ReactiveElement,
    Simulator,
    TransientResult,
)
from siliconforge.exceptions import NgspiceCommandError, NgspiceExitedError
from siliconforge.netlist_utils import find_reactive_elements

logger = logging.getLogger(__name__)

_LIB_CANDIDATES: tuple[str, ...] = ("libngspice.so", "libngspice.so.0")

# Lines emitted by ngspice that indicate a real failure when they appear
# on the stderr callback channel during a command. This list was built
# from observed ngspice 42 output (see docs/M1_simulation_backend.md) and
# is intentionally checked case-insensitively as a substring match, since
# ngspice's diagnostic wording is not a stable, versioned API.
_ERROR_MARKERS: tuple[str, ...] = (
    "error",
    "no such vector",
    "unable to",
    "fatal",
    "doesn't evaluate",
)


# ---------------------------------------------------------------------------
# ctypes struct definitions, transcribed field-for-field from sharedspice.h.
# ---------------------------------------------------------------------------


class _NgComplex(ctypes.Structure):
    _fields_ = [("cx_real", ctypes.c_double), ("cx_imag", ctypes.c_double)]


class _VectorInfo(ctypes.Structure):
    _fields_ = [
        ("v_name", ctypes.c_char_p),
        ("v_type", ctypes.c_int),
        ("v_flags", ctypes.c_short),
        ("v_realdata", ctypes.POINTER(ctypes.c_double)),
        ("v_compdata", ctypes.POINTER(_NgComplex)),
        ("v_length", ctypes.c_int),
    ]


class _VecValues(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("creal", ctypes.c_double),
        ("cimag", ctypes.c_double),
        ("is_scale", ctypes.c_bool),
        ("is_complex", ctypes.c_bool),
    ]


class _VecValuesAll(ctypes.Structure):
    _fields_ = [
        ("veccount", ctypes.c_int),
        ("vecindex", ctypes.c_int),
        ("vecsa", ctypes.POINTER(ctypes.POINTER(_VecValues))),
    ]


class _VecInfo(ctypes.Structure):
    _fields_ = [
        ("number", ctypes.c_int),
        ("vecname", ctypes.c_char_p),
        ("is_real", ctypes.c_bool),
        ("pdvec", ctypes.c_void_p),
        ("pdvecscale", ctypes.c_void_p),
    ]


class _VecInfoAll(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("title", ctypes.c_char_p),
        ("date", ctypes.c_char_p),
        ("type", ctypes.c_char_p),
        ("veccount", ctypes.c_int),
        ("vecs", ctypes.POINTER(ctypes.POINTER(_VecInfo))),
    ]


# Callback typedefs, matching sharedspice.h exactly.
_SendChar_t = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_SendStat_t = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_ControlledExit_t = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p
)
_SendData_t = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.POINTER(
        _VecValuesAll), ctypes.c_int, ctypes.c_int, ctypes.c_void_p
)
_SendInitData_t = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.POINTER(_VecInfoAll), ctypes.c_int, ctypes.c_void_p
)
_BGThreadRunning_t = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)


def _load_library() -> ctypes.CDLL:
    last_error: OSError | None = None
    for candidate in _LIB_CANDIDATES:
        try:
            return ctypes.CDLL(candidate, mode=ctypes.RTLD_GLOBAL)
        except OSError as exc:
            last_error = exc
    raise OSError(
        f"Could not load the ngspice shared library. Tried: {_LIB_CANDIDATES}. "
        "On Debian/Ubuntu install it with: apt-get install libngspice0-dev"
    ) from last_error


def _configure_signatures(lib: ctypes.CDLL) -> None:
    lib.ngSpice_Init.argtypes = [
        _SendChar_t,
        _SendStat_t,
        _ControlledExit_t,
        _SendData_t,
        _SendInitData_t,
        _BGThreadRunning_t,
        ctypes.c_void_p,
    ]
    lib.ngSpice_Init.restype = ctypes.c_int

    lib.ngSpice_Command.argtypes = [ctypes.c_char_p]
    lib.ngSpice_Command.restype = ctypes.c_int

    lib.ngSpice_Circ.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
    lib.ngSpice_Circ.restype = ctypes.c_int

    lib.ngGet_Vec_Info.argtypes = [ctypes.c_char_p]
    lib.ngGet_Vec_Info.restype = ctypes.POINTER(_VectorInfo)

    lib.ngSpice_CurPlot.argtypes = []
    lib.ngSpice_CurPlot.restype = ctypes.c_char_p

    lib.ngSpice_AllPlots.argtypes = []
    lib.ngSpice_AllPlots.restype = ctypes.POINTER(ctypes.c_char_p)

    lib.ngSpice_AllVecs.argtypes = [ctypes.c_char_p]
    lib.ngSpice_AllVecs.restype = ctypes.POINTER(ctypes.c_char_p)

    lib.ngSpice_running.argtypes = []
    lib.ngSpice_running.restype = ctypes.c_bool


_PROCESS_HAS_ACTIVE_INSTANCE = False


class NgspiceSharedBackend(Simulator):
    """`Simulator` implementation driving ngspice via ``libngspice.so``.

    Parameters
    ----------
    stdout_buffer_size:
        Number of most-recent stdout lines from ngspice to retain for
        diagnostics (e.g. surfaced inside `NgspiceCommandError`).
    stderr_buffer_size:
        Same, for the stderr channel. ngspice reports most convergence
        and parse failures on this channel.
    """

    def __init__(self, stdout_buffer_size: int = 500, stderr_buffer_size: int = 500) -> None:
        global _PROCESS_HAS_ACTIVE_INSTANCE
        if _PROCESS_HAS_ACTIVE_INSTANCE:
            raise RuntimeError(
                "An NgspiceSharedBackend is already active in this process. "
                "libngspice maintains process-global state and does not support "
                "multiple concurrent shared-library instances; this is a "
                "limitation of ngspice itself. Use reset()+load() to reuse this "
                "instance for a different circuit instead of constructing a new one."
            )

        self._lib = _load_library()
        _configure_signatures(self._lib)

        self._stdout_lines: list[str] = []
        self._stderr_lines: list[str] = []
        self._stdout_buffer_size = stdout_buffer_size
        self._stderr_buffer_size = stderr_buffer_size

        self._exited = False
        self._exit_status: int | None = None
        self._exit_due_to_quit: bool | None = None

        self._netlist_lines: list[str] | None = None
        self._reactive_elements: dict[str, ReactiveElement] = {}
        self._last_benchmark: BenchmarkMetrics | None = None

        # Keep references to the CFUNCTYPE-wrapped callbacks alive for the
        # lifetime of this instance -- ctypes does not keep them alive on
        # its own, and a garbage-collected callback that the C side later
        # invokes is a use-after-free.
        self._cb_send_char = _SendChar_t(self._on_send_char)
        self._cb_send_stat = _SendStat_t(self._on_send_stat)
        self._cb_controlled_exit = _ControlledExit_t(self._on_controlled_exit)
        self._cb_send_data = _SendData_t(self._on_send_data)
        self._cb_send_init_data = _SendInitData_t(self._on_send_init_data)
        self._cb_bg_thread_running = _BGThreadRunning_t(
            self._on_bg_thread_running)

        rc = self._lib.ngSpice_Init(
            self._cb_send_char,
            self._cb_send_stat,
            self._cb_controlled_exit,
            self._cb_send_data,
            self._cb_send_init_data,
            self._cb_bg_thread_running,
            None,
        )
        if rc != 0:
            raise RuntimeError(f"ngSpice_Init returned non-zero status {rc}")

        _PROCESS_HAS_ACTIVE_INSTANCE = True
        logger.debug("ngspice shared-library backend initialized (rc=%d)", rc)

    # -- libngspice callbacks -------------------------------------------------
    # Every callback body is wrapped in try/except: an uncaught Python
    # exception crossing back into C through a ctypes callback is undefined
    # behaviour we should never risk, regardless of cause.

    def _on_send_char(self, message: bytes, _ident: int, _user: object) -> int:
        try:
            text = message.decode("utf-8", errors="replace")
            # ngspice's convention is to prefix each line with "stdout " or
            # "stderr " to indicate which channel it originated from.
            if text.startswith("stderr"):
                line = text[len("stderr"):].strip()
                self._stderr_lines.append(line)
                if len(self._stderr_lines) > self._stderr_buffer_size:
                    del self._stderr_lines[: -self._stderr_buffer_size]
                logger.debug("ngspice[stderr]: %s", line)
            else:
                line = text[len("stdout"):].strip(
                ) if text.startswith("stdout") else text
                self._stdout_lines.append(line)
                if len(self._stdout_lines) > self._stdout_buffer_size:
                    del self._stdout_lines[: -self._stdout_buffer_size]
                logger.debug("ngspice[stdout]: %s", line)
        except Exception:  # noqa: BLE001 - must never propagate into C
            logger.exception("Error inside ngspice SendChar callback")
        return 0

    def _on_send_stat(self, message: bytes, _ident: int, _user: object) -> int:
        try:
            logger.debug("ngspice[status]: %s",
                         message.decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            logger.exception("Error inside ngspice SendStat callback")
        return 0

    def _on_controlled_exit(
        self, exit_status: int, immediate_unload: bool, due_to_quit: bool, _ident: int, _user: object
    ) -> int:
        try:
            self._exited = True
            self._exit_status = exit_status
            self._exit_due_to_quit = due_to_quit
            logger.warning(
                "ngspice signalled ControlledExit(status=%d, immediate_unload=%s, due_to_quit=%s)",
                exit_status, immediate_unload, due_to_quit,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Error inside ngspice ControlledExit callback")
        return 0

    def _on_send_data(self, _data: object, _count: int, _ident: int, _user: object) -> int:
        return 0

    def _on_send_init_data(self, _data: object, _ident: int, _user: object) -> int:
        return 0

    def _on_bg_thread_running(self, _running: bool, _ident: int, _user: object) -> int:
        return 0

    # -- internal helpers -----------------------------------------------------

    def _guard_not_exited(self) -> None:
        if self._exited:
            raise NgspiceExitedError(
                self._exit_status or 0, bool(self._exit_due_to_quit))

    def _run_command(self, command: str) -> None:
        """Issue one ngspice command, blocking until it completes, and raise
        `NgspiceCommandError` if the stderr channel reported a failure."""
        self._guard_not_exited()
        self._stderr_lines.clear()
        logger.debug("ngSpice_Command(%r)", command)
        self._lib.ngSpice_Command(command.encode("utf-8"))
        self._guard_not_exited()  # a command (e.g. 'quit') may itself trigger exit
        lowered_errors = [
            line for line in self._stderr_lines
            if any(marker in line.lower() for marker in _ERROR_MARKERS)
        ]
        if lowered_errors:
            raise NgspiceCommandError(command, lowered_errors)

    def _read_vector_raw(self, name: str) -> list[float]:
        info_ptr = self._lib.ngGet_Vec_Info(name.encode("utf-8"))
        if not info_ptr:
            raise NgspiceCommandError(
                f"ngGet_Vec_Info({name!r})", [
                    f"vector {name!r} not found in current plot"]
            )
        info = info_ptr.contents
        if not info.v_realdata:
            raise NgspiceCommandError(
                f"ngGet_Vec_Info({name!r})",
                [f"vector {name!r} has no real data (complex-only vectors are "
                 "not yet supported by this M1 backend; needed only from M4 onward)"],
            )
        length = info.v_length
        return list(info.v_realdata[0:length])

    # -- Simulator interface ---------------------------------------------------

    def load(self, netlist_lines: Sequence[str]) -> None:
        self._guard_not_exited()
        lines = list(netlist_lines)
        circ_lines = ["siliconforge auto-generated netlist", *lines, ".end"]
        encoded: list[bytes | None] = [
            line.encode("utf-8") for line in circ_lines]
        encoded.append(None)
        array_type = ctypes.c_char_p * len(encoded)
        circ_array = array_type(*encoded)

        self._stderr_lines.clear()
        rc = self._lib.ngSpice_Circ(circ_array)
        self._guard_not_exited()
        if rc != 0 or any(
            any(marker in line.lower() for marker in _ERROR_MARKERS) for line in self._stderr_lines
        ):
            raise NgspiceCommandError(
                "ngSpice_Circ(<netlist>)", list(self._stderr_lines))

        self._netlist_lines = lines
        elements = find_reactive_elements(lines)
        self._reactive_elements = {el.name: el for el in elements}
        logger.debug(
            "Loaded circuit with %d reactive elements: %s",
            len(elements), [el.name for el in elements],
        )

    def reset(self) -> None:
        self._guard_not_exited()
        # 'destroy all' removes every stored plot/result; it does not by
        # itself unload the circuit's element/model structures, but since
        # the next call is always load() -> ngSpice_Circ(), which replaces
        # the active circuit outright, no stale circuit state survives.
        self._run_command("destroy all")
        self._netlist_lines = None
        self._reactive_elements = {}
        self._last_benchmark = None

    def operating_point(self) -> CircuitState:
        self._guard_not_exited()
        if not self._reactive_elements:
            raise RuntimeError(
                "No circuit loaded -- call load() before operating_point().")

        start = time.perf_counter()
        self._run_command("op")
        elapsed = time.perf_counter() - start

        values: dict[str, float] = {}
        for element in self._reactive_elements.values():
            samples = self._read_vector_raw(element.read_vector)
            values[element.name] = samples[-1]

        self._last_benchmark = BenchmarkMetrics(
            wall_time_s=elapsed, converged=True, n_timepoints=1)
        return CircuitState(values=values, time=0.0)

    def transient(
        self,
        tstep: float,
        tstop: float,
        use_ic: bool = True,
        extra_signals: Sequence[str] = (),
    ) -> TransientResult:
        self._guard_not_exited()
        if not self._reactive_elements:
            raise RuntimeError(
                "No circuit loaded -- call load() before transient().")

        command = f"tran {tstep:.12g} {tstop:.12g}"
        if use_ic:
            command += " uic"

        start = time.perf_counter()
        self._run_command(command)
        elapsed = time.perf_counter() - start

        time_axis = self._read_vector_raw("time")
        n_points = len(time_axis)
        final_time = time_axis[-1] if time_axis else 0.0
        converged = n_points > 0 and final_time >= 0.999 * tstop

        signals: dict[str, list[float]] = {"time": time_axis}
        final_values: dict[str, float] = {}
        for element in self._reactive_elements.values():
            samples = self._read_vector_raw(element.read_vector)
            signals[element.read_vector] = samples
            final_values[element.name] = samples[-1] if samples else float(
                "nan")
        for name in extra_signals:
            signals[name] = self._read_vector_raw(name)

        self._last_benchmark = BenchmarkMetrics(
            wall_time_s=elapsed,
            converged=converged,
            n_timepoints=n_points,
            note="" if converged else f"transient stopped at t={final_time:.6g}s, short of tstop={tstop:.6g}s",
        )
        return TransientResult(
            time=time_axis,
            signals=signals,
            final_state=CircuitState(values=final_values, time=final_time),
            n_timepoints=n_points,
        )

    def inject_state(self, state: CircuitState) -> None:
        self._guard_not_exited()
        for name, value in state.values.items():
            element = self._reactive_elements.get(name)
            if element is None:
                raise KeyError(
                    f"'{name}' is not a reactive element in the currently loaded "
                    f"circuit (known elements: {sorted(self._reactive_elements)})"
                )
            self._run_command(f"alter {element.alter_target}={value:.17g}")

    def get_vector(self, name: str) -> list[float]:
        self._guard_not_exited()
        return self._read_vector_raw(name)

    @property
    def last_benchmark(self) -> BenchmarkMetrics | None:
        return self._last_benchmark

    @property
    def reactive_elements(self) -> dict[str, ReactiveElement]:
        """Read-only view of the reactive elements discovered in the
        currently loaded circuit. Exposed (beyond the abstract `Simulator`
        interface) because Module 3 needs this to fix a canonical
        state-vector ordering before its first GMRES call."""
        return dict(self._reactive_elements)
