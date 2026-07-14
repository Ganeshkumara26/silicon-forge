"""
siliconforge.exceptions
==========================

Exception hierarchy for siliconforge.

Four concrete exceptions are defined here: the original three, which
are what the real, uploaded M1 code (`netlist_utils.py`,
`ngspice_shared.py`) actually raises, plus `UnsupportedCircuitError`,
added the session `backends/reference_ode.py` was written -- see each
docstring for the specific call site. New exception types belong here
when a module that actually needs them is written, not ahead of time
on the strength of a roadmap document.
"""

from __future__ import annotations


class SiliconForgeError(Exception):
    """Root of this project's exception hierarchy. Catching this
    catches every siliconforge-specific failure without also catching
    unrelated Python built-ins, which keep their normal meaning (a bad
    argument type still raises `TypeError`, not a wrapped subclass)."""


class NetlistParseError(SiliconForgeError):
    """Raised by `siliconforge.netlist_utils` when a netlist line
    expected to be a parseable element statement isn't.

    Parameters
    ----------
    line : str
        The exact source line (or other short context string) that
        failed to parse.
    reason : str
        Human-readable explanation of what was expected.
    """

    def __init__(self, line: str, reason: str) -> None:
        self.line = line
        self.reason = reason
        super().__init__(f"{reason}: {line!r}")


class XyceNotFoundError(SiliconForgeError):
    """Raised by `siliconforge.backends.xyce.XyceBackend` when the Xyce
    executable cannot be found on the host.

    Install options
    ---------------
    - Spack: ``spack install xyce && spack load xyce``
    - MSYS2/MinGW: ``pacman -S mingw-w64-x86_64-xyce``
    - Source build: see ``engineering/xyce_build_instructions.yaml``

    Parameters
    ----------
    xyce_path : str
        The executable name/path that was searched.
    message : str
        Human-readable install hint.
    """

    def __init__(self, xyce_path: str, message: str = "") -> None:
        self.xyce_path = xyce_path
        super().__init__(
            f"Xyce executable {xyce_path!r} not found. {message}".strip()
        )


class NgspiceCommandError(SiliconForgeError):
    """Raised by `NgspiceSharedBackend` when an `ngSpice_Command` (or
    `ngSpice_Circ`) call completes but ngspice reported a failure on
    its stderr callback channel during that call -- a netlist parse
    error, a missing vector name, or a non-convergent analysis.

    Parameters
    ----------
    command : str
        The command string (or pseudo-command label, e.g.
        ``"ngGet_Vec_Info('v(tank)')"``) being executed.
    error_lines : list[str]
        The specific stderr lines ngspice emitted that matched a known
        failure marker.
    """

    def __init__(self, command: str, error_lines: list[str]) -> None:
        self.command = command
        self.error_lines = list(error_lines)
        joined = "; ".join(
            error_lines) if error_lines else "(no detail captured)"
        super().__init__(f"ngspice command {command!r} failed: {joined}")


class NgspiceExitedError(SiliconForgeError):
    """Raised when any `NgspiceSharedBackend` method is called after
    ngspice has already signalled `ControlledExit`. Once this fires,
    the instance is no longer usable -- libngspice does not support
    being restarted within the same process after exit; a fresh
    process is required.

    Parameters
    ----------
    exit_status : int
        The exit status ngspice reported.
    due_to_quit : bool
        Whether the exit was a normal user-requested quit (True) or an
        abnormal/error exit (False).
    """

    def __init__(self, exit_status: int, due_to_quit: bool) -> None:
        self.exit_status = exit_status
        self.due_to_quit = due_to_quit
        kind = "normal quit" if due_to_quit else "ABNORMAL exit"
        super().__init__(
            f"ngspice has exited ({kind}, status={exit_status}); this backend "
            "instance can no longer be used -- construct a new process."
        )


class UnsupportedCircuitError(SiliconForgeError):
    """Raised by `siliconforge.backends.reference_ode` (both the
    module-level netlist-scanning helpers and `ReferenceOdeBackend.load`)
    when a netlist is not exactly the one topology this backend's v1
    supports: a single top-level capacitor and inductor sharing one pair
    of nodes, with at most one resistor also across that same pair, and
    no other top-level element.

    This is deliberately a loud, immediate failure rather than a silent
    best-effort approximation -- e.g. ignoring an independent source
    that's actually present would produce a plausible-looking but wrong
    transient result with no indication anything was dropped, which is
    a strictly worse failure mode than refusing to run. See the module
    docstring of `reference_ode.py` for the full list of what is and
    isn't supported, and why generalizing further is deferred.

    Parameters
    ----------
    reason : str
        Human-readable explanation of which v1 constraint was violated,
        normally including the offending line or element count.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


__all__ = [
    "SiliconForgeError",
    "NetlistParseError",
    "NgspiceCommandError",
    "NgspiceExitedError",
    "UnsupportedCircuitError",
    "XyceNotFoundError",
]
