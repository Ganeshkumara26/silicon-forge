"""conftest.py — pytest configuration for SiliconForge solver tests."""

import os
import sys
import json
import pytest
from pathlib import Path

# Ensure the siliconforge package is importable
_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))


@pytest.fixture
def sample_pn_curve():
    """Sample phase noise curve for jitter integration tests."""
    import numpy as np
    offsets = np.logspace(3, 9, 100)
    f0 = 10.25e9
    fm = 1e6
    L_fm = -133.74
    pn = L_fm + 20 * np.log10(fm / offsets)
    return offsets.tolist(), pn.tolist(), f0


@pytest.fixture
def sample_design_config(tmp_path):
    """Create a minimal design config for testing."""
    config = {
        "design": {
            "name": "test_vco",
            "pdk": "ihp_sg13g2",
            "simulator": "ngspice",
        },
        "pss": {"fundamental_frequency": 10.25e9},
        "jitter": {"fmin_hz": 10e3, "fmax_hz": 1e9},
        "parameters": {"f0": 10.25e9},
    }
    config_path = tmp_path / "test_config.yaml"
    import yaml
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return str(config_path)


@pytest.fixture
def tmp_regression_dir(tmp_path):
    """Temporary directory for regression test outputs."""
    d = tmp_path / "regression_results"
    d.mkdir()
    return str(d)
