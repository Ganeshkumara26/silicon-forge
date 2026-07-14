import pytest
from siliconforge.backends.reference_ode import ReferenceOdeBackend
from siliconforge.backends.base import CircuitState

def test_reference_ode_backend():
    sim = ReferenceOdeBackend()
    
    # Load a simple tank netlist
    netlist = [
        "C1 TANK 0 0.5p",
        "L1 TANK 0 200p",
        "R1 TANK 0 200",
    ]
    sim.load(netlist)
    
    # Inject state (start with 1V on capacitor)
    op = sim.operating_point()
    op.values["C1"] = 1.0 
    sim.inject_state(op)
    
    # Run transient
    res = sim.transient(tstep=1e-12, tstop=1e-9)
    assert res.n_timepoints > 0
    assert "time" in res.signals
    assert "v(tank)" in res.signals
    
    # The oscillation should have decayed due to R1
    final_v = res.signals["v(tank)"][-1]
    assert abs(final_v) < 1.0
