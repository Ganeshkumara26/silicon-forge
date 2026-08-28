"""test_design_config.py — Tests for design configuration abstraction."""

import pytest
import yaml
from siliconforge.solvers.design_config import (
    DesignConfig, PSSConfig, NoiseConfig, load_config,
    adpll_config, lc_vco_config, ring_osc_config,
)


class TestDesignConfig:
    """Test the design configuration abstraction."""

    def test_default_config(self):
        c = DesignConfig()
        assert c.name == "unnamed_design"
        assert c.pdk == "ihp_sg13g2"
        assert c.simulator == "ngspice"

    def test_adpll_preset(self):
        c = adpll_config()
        assert c.name == "adpll_10ghz"
        assert c.pss.fundamental_frequency == 10.25e9
        assert c.parameters["divider"] == 205

    def test_lc_vco_preset(self):
        c = lc_vco_config(f0_ghz=5.0)
        assert c.pss.fundamental_frequency == 5e9
        assert c.noise.carrier_frequency == 5e9

    def test_ring_osc_preset(self):
        c = ring_osc_config(f0_ghz=1.0)
        assert c.pss.fundamental_frequency == 1e9
        assert c.parameters["stages"] == 5

    def test_resolve_references(self):
        c = DesignConfig(
            pss=PSSConfig(fundamental_frequency="auto"),
            noise=NoiseConfig(carrier_frequency="auto"),
            parameters={"f0": 5e9},
        )
        c.resolve_references()
        assert c.pss.fundamental_frequency == 5e9
        assert c.noise.carrier_frequency == 5e9

    def test_yaml_roundtrip(self, tmp_path, sample_design_config):
        c = load_config(sample_design_config)
        assert c.name == "test_vco"
        assert c.pss.fundamental_frequency == 10.25e9

    def test_json_roundtrip(self, tmp_path):
        c = DesignConfig(name="json_test", pdk="sky130")
        path = str(tmp_path / "config.json")
        c.to_json(path)
        loaded = load_config(path)
        assert loaded.name == "json_test"
        assert loaded.pdk == "sky130"

    def test_no_adpll_hardcodes(self):
        """Verify that default config has no ADPLL-specific assumptions."""
        c = DesignConfig()
        assert "divider" not in c.parameters
        assert "Icp" not in c.parameters
        assert "prescaler_ratio" not in c.parameters
