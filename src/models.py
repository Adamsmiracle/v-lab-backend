from enum import Enum
from typing import List, Union, Dict, Any, Optional
from pydantic import BaseModel, Field

# --- Enums for Analysis Types ---

class AnalysisType(str, Enum):
    OPERATING_POINT = "op"
    TRANSIENT = "transient"
    AC = "ac"
    DC = 'dc'
    NOISE = 'noise'
    FOURIER = 'fourier'
    # Add more analysis types if PySpice supports them and you need them

# --- Simulation Request Model (Updated) ---

class SimulationRequest(BaseModel):
    """Defines the input structure for a circuit simulation request."""
    circuit_name: str = Field("Simulated Circuit", description="Name of the circuit.")
    netlist_string: str = Field(..., description="The raw SPICE netlist as a string.")
    analysis_type: AnalysisType
    analysis_parameters: Dict[str, Union[str, float, int]] = Field(
        {}, description="Parameters for the chosen analysis type (e.g., {'step_time': '1us', 'end_time': '1ms'} for transient)."
    )
    requested_results: List[Dict[str, str]] = Field(
        [], description="List of specific results to return (e.g., [{'type': 'node_voltage', 'name': 'out'}, {'type': 'branch_current', 'name': 'Vsource'}]). 'name' should match netlist node/branch names."
    )

# --- Simulation Result Models (Remain the same) ---

class NodeVoltageResult(BaseModel):
    node: str
    voltage: Union[float, List[float]] # float for OP, List[float] for TRAN/AC
    unit: str = "V"

class BranchCurrentResult(BaseModel):
    branch: str
    current: Union[float, List[float]] # float for OP, List[float] for TRAN/AC
    unit: str = "A"

class SimulationResults(BaseModel):
    """Defines the output structure for simulation results."""
    success: bool
    message: str
    simulation_type: AnalysisType
    node_voltages: List[NodeVoltageResult] = []
    branch_currents: List[BranchCurrentResult] = []
    time_axis: Optional[List[float]] = Field(None, description="Time values for transient analysis.")
    frequency_axis: Optional[List[float]] = Field(None, description="Frequency values for AC analysis.")

class ErrorResponse(BaseModel):
    """Standard error response model."""
    success: bool = False
    message: str
    details: Optional[str] = None