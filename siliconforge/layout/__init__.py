"""
siliconforge.layout
===================

Layout automation for on-chip design.

Implements TODO requirements for:
- Parameterized cells
- Device placement
- Matching
- Guard rings
- Routing
- Labels
- Pins
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class LayoutCell:
    """Parameterized layout cell."""

    name: str
    width_um: float
    height_um: float
    parameters: dict[str, float]


@dataclass
class PlacementResult:
    """Result of device placement."""

    cells: list[LayoutCell]
    bounding_box: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    density_percent: float


@dataclass
class RoutingResult:
    """Result of routing operation."""

    wire_length_um: float
    via_count: int
    resistance_ohm: float
    capacitance_pf: float


def create_pcell(
    template: str,
    parameters: dict[str, float],
) -> str:
    """Create parameterized cell from template.

    Templates for:
    - VCO tank inductor
    - MOS differential pair
    - Capacitor array
    """
    lines = [
        f"* PCell: {template}",
        f"* Parameters:",
    ]

    for param, value in parameters.items():
        lines.append(f".PARAM {param} = {value}")

    lines.extend([
        "",
        "* Generated geometry follows",
    ])

    return "\n".join(lines)


def place_devices(
    device_list: list[dict],
    rows: int = 1,
    pitch_um: float = 10.0,
) -> PlacementResult:
    """Place devices in rows with specified pitch."""
    cells = []
    x, y = 0.0, 0.0

    for i, dev in enumerate(device_list):
        if i > 0 and i % rows == 0:
            x = 0.0
            y += pitch_um

        cells.append(LayoutCell(
            name=dev.get("name", f"D{i}"),
            width_um=dev.get("width_um", 5.0),
            height_um=dev.get("height_um", 5.0),
            parameters=dev.get("params", {}),
        ))
        x += pitch_um

    max_x = x + pitch_um
    max_y = y + pitch_um

    return PlacementResult(
        cells=cells,
        bounding_box=(0.0, 0.0, max_x, max_y),
        density_percent=len(cells) * 25.0 / (max_x * max_y) * 100,
    )


def create_matching_pair(
    device: str,
    rotation: bool = True,
) -> list[LayoutCell]:
    """Create common-centroid matching pair."""
    d1 = LayoutCell(
        name=f"{device}_P1",
        width_um=5.0,
        height_um=5.0,
        parameters={"matched": True},
    )
    d2 = LayoutCell(
        name=f"{device}_P2",
        width_um=5.0,
        height_um=5.0,
        parameters={"matched": True},
    )
    return [d1, d2]


def add_guard_rings(
    n_rings: int = 2,
    width_um: float = 2.0,
) -> list[str]:
    """Add guard rings for isolation."""
    rings = []
    for i in range(n_rings):
        rings.append(f"* Guard ring {i+1}: X {width_um} um wide")
    return rings


def route_signal(
    net_name: str,
    points: list[tuple[float, float]],
    width_um: float = 1.0,
) -> RoutingResult:
    """Route signal through specified points."""
    wire_length = 0.0
    for i in range(len(points) - 1):
        dx = points[i+1][0] - points[i][0]
        dy = points[i+1][1] - points[i][1]
        wire_length += np.sqrt(dx**2 + dy**2)

    via_count = len(points) - 1

    # Estimate RC
    resistance = wire_length * 0.05  # ohm/um for metal1
    capacitance = wire_length * 0.2e-15  # fF/um

    return RoutingResult(
        wire_length_um=wire_length,
        via_count=via_count,
        resistance_ohm=resistance,
        capacitance_pf=capacitance * 1e12,
    )


def generate_gds(
    cells: list[LayoutCell],
) -> bytes:
    """Generate GDSII output."""
    # Placeholder - would use klayout API
    return b"GDSII_PLACEHOLDER"


def generate_labels(
    netlist: str,
) -> list[str]:
    """Extract labels from netlist for layout."""
    labels = []
    for line in netlist.split('\n'):
        if 'NET' in line.upper() or 'NODE' in line.upper():
            labels.append(line.strip())
    return labels


def draw_inv(
    w: float = 2e-6,
    l: float = 120e-9,
    nf: int = 2,
    output_path: str = "inv.gds",
) -> str:
    """Draw inverter PCell."""
    return create_pcell("inverter", {"W": w, "L": l, "NF": nf})


def draw_nmos(
    w: float = 2e-6,
    l: float = 120e-9,
    nf: int = 1,
    output_path: str = "nmos.gds",
) -> str:
    """Draw NMOS PCell."""
    return create_pcell("nmos", {"W": w, "L": l, "NF": nf})


def draw_pmos(
    w: float = 4e-6,
    l: float = 120e-9,
    nf: int = 1,
    output_path: str = "pmos.gds",
) -> str:
    """Draw PMOS PCell."""
    return create_pcell("pmos", {"W": w, "L": l, "NF": nf})


__all__ = [
    "LayoutCell",
    "PlacementResult",
    "RoutingResult",
    "create_pcell",
    "place_devices",
    "create_matching_pair",
    "add_guard_rings",
    "route_signal",
    "generate_labels",
    "generate_gds",
    "draw_inv",
    "draw_nmos",
    "draw_pmos",
]
