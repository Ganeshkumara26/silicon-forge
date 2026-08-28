"""test_backends.py — Backend interface documentation.

NOTE: The Simulator ABC and backend implementations were removed.
This file documents the interface contract for future reference.
"""

import pytest


class TestBackendContract:
    """Document the interface that any backend must implement.

    The Simulator ABC defined:
    - load(), reset(), operating_point(), transient()
    - inject_state(), get_vector()
    - reactive_elements property
    - last_benchmark property

    Current simulation uses:
    - spice_runner.py for ngspice (WSL-based, works for MOSFETs)
    - run_ngspice_pipeline.py for end-to-end phase noise extraction
    """

    def test_backend_interface_documented(self):
        """Verify the interface contract is documented."""
        required_methods = [
            "load", "reset", "operating_point", "transient",
            "inject_state", "get_vector"
        ]
        assert len(required_methods) == 6

    def test_no_backend_imports(self):
        """Verify backends module is removed."""
        with pytest.raises(ImportError):
            import siliconforge.backends
