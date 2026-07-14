import pytest
import os
from pathlib import Path
from siliconforge.core.pipeline import SiliconForgePipeline

def test_pipeline_execution():
    pipeline = SiliconForgePipeline(verbose=False)
    
    # Run the pipeline (this uses analytical/reference ODE solvers)
    success = pipeline.run(project_name="TEST_PROJECT")
    
    assert success is True
    assert pipeline.state.rtl_generated is True
    
    # Verify RTL was dumped
    assert Path("generated/rtl/aac_core.sv").exists()
    assert Path("generated/rtl/afc_core.sv").exists()
    
    # Verify characterization JSON was dumped
    assert Path("generated/json/characterization_data.json").exists()
