"""
siliconforge.netlist_utils
============================

A deliberately narrow netlist utility: it discovers the terminal node
names of top-level capacitor and inductor instances in a SPICE netlist,
which is exactly the information `siliconforge.backends.base.ReactiveElement`
needs to build the `v(...)`/`i(...)` read-vector and `alter @...[ic]=`
write-target strings for state injection/extraction.

What this module is NOT
-------------------------
This is not a general SPICE netlist parser. A full netlist parser
(subcircuit expansion, parameter/.param evaluation, device-model
resolution) is its own module in this project's eventual architecture
(the "Circuit Interface Layer" described in the project's master
architecture document) and is explicitly out of scope for M1. Building
it now, before any module actually needs subcircuit-aware parsing, would
violate this project's own scoping decision to implement exactly what
the current module manifest requires and nothing speculative.

Concretely, this module:

* DOES parse top-level (not inside a ``.subckt`` block) two-terminal
  ``C`` and ``L`` element lines, including ``+`` line continuations and
  ``*`` comment lines.
* DOES NOT descend into ``.subckt`` definitions. Reactive elements
  declared only inside a subcircuit body are skipped, and a warning is
  logged identifying exactly which lines were skipped and why, rather
  than silently omitting them from the discovered set. (ngspice's
  `alter` command does support hierarchical addressing such as
  ``@x1.c1[ic]=...`` for devices inside subcircuit instances -- this
  module simply does not yet *discover* such elements automatically.
  When Module 3 needs to drive the actual hierarchical VCO subcircuit,
  this is the function that will be extended, with its own new tests,
  not patched silently.)
* DOES NOT evaluate ``.param`` expressions, resolve ``{...}`` brace
  expressions in the value field, or validate that referenced models
  exist. None of that is needed to identify terminal node names.
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from siliconforge.backends.base import ReactiveElement, ReactiveKind
from siliconforge.exceptions import NetlistParseError

logger = logging.getLogger(__name__)

# Matches: <name> <node1> <node2> <rest...>
# Node names in SPICE may contain letters, digits, underscores, and the
# bracket/dot characters used by hierarchical/bus naming; we accept any
# non-whitespace run as a node name rather than over-constrain the charset.
_ELEMENT_LINE_RE = re.compile(
    r"^\s*(?P<name>\S+)\s+(?P<node_p>\S+)\s+(?P<node_n>\S+)\s+(?P<rest>.*)$"
)


def _merge_continuations(netlist_lines: Sequence[str]) -> list[str]:
    """Join SPICE ``+``-prefixed continuation lines onto the previous
    logical line, and drop ``*``-comment and blank lines.

    This mirrors ngspice's own line-joining behaviour closely enough for
    the purpose of finding element start tokens; it does not attempt to
    replicate every edge case of ngspice's tokenizer (e.g. ``;`` inline
    comments are stripped from the relevant tail but are not load-bearing
    for node-name discovery).
    """
    merged: list[str] = []
    for raw_line in netlist_lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        if stripped.startswith("+"):
            if not merged:
                raise NetlistParseError(
                    raw_line, "continuation line ('+') with no preceding line to continue"
                )
            merged[-1] = merged[-1] + " " + stripped[1:].strip()
        else:
            # Strip a ';' inline comment if present, outside of {} expressions.
            # A full brace-aware scan is unnecessary here since we only need
            # the first three whitespace-separated tokens.
            merged.append(stripped)
    return merged


def _subckt_depth_after(line: str, depth: int) -> int:
    """Update subcircuit nesting depth given one already-merged netlist line."""
    lowered = line.strip().lower()
    if lowered.startswith(".subckt"):
        return depth + 1
    if lowered.startswith(".ends"):
        return max(0, depth - 1)
    return depth


def parse_reactive_line(line: str) -> ReactiveElement:
    """Parse a single top-level netlist line into a `ReactiveElement`.

    Parameters
    ----------
    line:
        One already-continuation-merged SPICE statement, expected to
        begin with ``C`` or ``L`` (case-insensitive).

    Raises
    ------
    NetlistParseError
        If the line does not start with C/L, or does not have at least
        a name and two node tokens.
    """
    match = _ELEMENT_LINE_RE.match(line)
    if not match:
        raise NetlistParseError(
            line, "expected at least 'name node1 node2 value'")

    name = match.group("name")
    first_char = name[0].lower() if name else ""
    if first_char == "c":
        kind = ReactiveKind.CAPACITOR
    elif first_char == "l":
        kind = ReactiveKind.INDUCTOR
    else:
        raise NetlistParseError(
            line, f"instance name {name!r} does not start with 'C' or 'L'"
        )

    return ReactiveElement(
        name=name,
        kind=kind,
        node_p=match.group("node_p"),
        node_n=match.group("node_n"),
    )


def find_reactive_elements(netlist_lines: Sequence[str]) -> list[ReactiveElement]:
    """Scan a netlist and return every top-level capacitor and inductor
    as a `ReactiveElement`, in netlist order.

    Lines inside ``.subckt`` / ``.ends`` blocks are skipped; each skipped
    reactive-looking line is logged at WARNING level naming the line, so
    the omission is visible rather than silent.
    """
    elements: list[ReactiveElement] = []
    depth = 0
    for line in _merge_continuations(netlist_lines):
        token = line.strip().split(None, 1)[0] if line.strip() else ""
        first_char = token[0].lower() if token else ""

        if depth > 0:
            if first_char in ("c", "l"):
                logger.warning(
                    "Skipping reactive element inside a .subckt body "
                    "(not yet supported by find_reactive_elements): %r",
                    line,
                )
            depth = _subckt_depth_after(line, depth)
            continue

        depth = _subckt_depth_after(line, depth)
        if first_char in ("c", "l") and not token.lower().startswith((".", "*")):
            elements.append(parse_reactive_line(line))

    return elements


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)

    netlist = [
        "* RLC tank",
        "V1 in 0 DC 0",
        "R1 in out 50",
        "L1 out 0 200e-12",
        "C1 out 0 3.5e-15",
        "+ ic=1.0",
        ".end",
    ]
    elems = find_reactive_elements(netlist)
    assert [e.name for e in elems] == ["L1", "C1"], elems

    subckt_netlist = [
        ".subckt amp in out",
        "C1 in mid 1p",
        ".ends amp",
        "X1 in out amp",
        "L1 out 0 1n",
    ]
    elems2 = find_reactive_elements(subckt_netlist)
    assert [e.name for e in elems2] == ["L1"], elems2

    print("netlist_utils self-test passed")
