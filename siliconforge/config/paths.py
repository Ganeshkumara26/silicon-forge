"""
siliconforge.config.paths
=========================

Centralized path configuration for the SiliconForge project.

All paths are resolved relative to the project root (where this package lives).
"""

from pathlib import Path
import os

# Project root (relative to siliconforge/config/paths.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Main directories
NETLISTS_DIR = PROJECT_ROOT / "netlists"
RESULTS_DIR = PROJECT_ROOT / "results"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SILICONFORGE_DIR = PROJECT_ROOT / "siliconforge"
GENERATED_DIR = PROJECT_ROOT / "generated"

# Sub-directories
RF_PIPELINE_DIR = SILICONFORGE_DIR / "automation" / "rf_pipeline"
SIM_RESULTS_DIR = RESULTS_DIR / "simulations"
WAVEFORMS_DIR = RESULTS_DIR / "waveforms"

# Key files
VCO_NETLIST = NETLISTS_DIR / "vco_xyce.cir"
VCO_FULL_NETLIST = NETLISTS_DIR / "vco_full.cir"
TB_V1_VCO_XYCE = "tb_v1_vco_xyce.cir"
TB_V1_VCO_XYCE_PRN = "tb_v1_vco_xyce.cir.prn"
XYCE_PSP_PLUGIN_WSL = "/tmp/Xyce_Plugin_PSP103_VA.so"

# PDK paths
IHP_PDK_ROOT = Path(os.environ.get(
    "IHP_PDK_ROOT", PROJECT_ROOT / "IHP-Open-PDK-0.3.0"))
XYCE_MOS_CORNER = IHP_PDK_ROOT / "ihp-sg13g2/libs.tech/xyce/models/cornerMOSlv.lib"
XYCE_HBT_LIB = IHP_PDK_ROOT / "ihp-sg13g2/libs.tech/xyce/models/sg13g2_hbt_mod.lib"

# Xyce binary (WSL)
XYCE_BIN_WSL = "/usr/local/bin/Xyce"
NGSPICE_BIN_WSL = "/usr/bin/ngspice"

# WSL path conversion


def to_wsl_path(win_path: Path | str) -> str:
    """Convert Windows path to WSL Linux path."""
    p = str(win_path).replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[3:]  # Skip "D:/"
        return f"/mnt/{drive}/{rest}"
    return p


def ensure_dirs() -> None:
    """Create all required directories."""
    for d in [NETLISTS_DIR, RESULTS_DIR, SCRIPTS_DIR, GENERATED_DIR,
              SIM_RESULTS_DIR, WAVEFORMS_DIR, RF_PIPELINE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def verify_external_deps() -> None:
    """Verify external dependencies and issue warnings if missing."""
    import logging
    logger = logging.getLogger(__name__)

    if not IHP_PDK_ROOT.exists():
        logger.warning(
            f"[WARNING] IHP PDK not found at {IHP_PDK_ROOT}. "
            f"Analog characterization requiring Spectre/Xyce will fail. "
            f"Please install it or adjust IHP_PDK_ROOT."
        )


# Common node names for VCO
VCO_DIFF_NODES = ["out_p", "out_n"]
VCO_ALL_NODES = ["out_p", "out_n", "vtune", "tail", "tank"]

__all__ = [
    "PROJECT_ROOT", "NETLISTS_DIR", "RESULTS_DIR", "SCRIPTS_DIR",
    "SILICONFORGE_DIR", "GENERATED_DIR", "RF_PIPELINE_DIR",
    "SIM_RESULTS_DIR", "WAVEFORMS_DIR",
    "VCO_NETLIST", "VCO_FULL_NETLIST", "TB_V1_VCO_XYCE", "TB_V1_VCO_XYCE_PRN",
    "XYCE_PSP_PLUGIN_WSL", "IHP_PDK_ROOT", "XYCE_MOS_CORNER", "XYCE_HBT_LIB",
    "XYCE_BIN_WSL", "NGSPICE_BIN_WSL",
    "to_wsl_path", "ensure_dirs", "verify_external_deps",
    "VCO_DIFF_NODES", "VCO_ALL_NODES",
]
