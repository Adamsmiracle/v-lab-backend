from enum import Enum
from typing import List, Union, Dict, Any, Optional, Annotated
from pydantic import BaseModel, Field, EmailStr, field_validator, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema
from datetime import datetime
from bson import ObjectId

# --- PyObjectId for MongoDB (Pydantic v2 compatible) ---

class PyObjectId(ObjectId):
    """Custom ObjectId for MongoDB that works with Pydantic v2"""
    
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetJsonSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.chain_schema([
                    core_schema.str_schema(),
                    core_schema.no_info_plain_validator_function(cls.validate_object_id),
                ])
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x)
            ),
        )
    
    @classmethod
    def validate_object_id(cls, v: Any) -> ObjectId:
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str):
            if ObjectId.is_valid(v):
                return ObjectId(v)
        raise ValueError("Invalid ObjectId")
    
    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "string", "format": "objectid"}

# --- Enums for Analysis Types ---

class AnalysisType(str, Enum):
    OPERATING_POINT = "op"
    TRANSIENT = "transient"
    AC = "ac"
    DC = 'dc'
    NOISE = 'noise'
    FOURIER = 'fourier'
    # Add more analysis types if PySpice supports them and you need them

# --- User Models ---

class UserCreate(BaseModel):
    """Model for creating a new user"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    """Model for user login"""
    username: str
    password: str

class User(BaseModel):
    """User model for MongoDB"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    username: str = Field(..., unique=True)
    email: EmailStr = Field(..., unique=True)
    hashed_password: str
    full_name: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }

class UserResponse(BaseModel):
    """User response model (without password)"""
    id: str
    username: str
    email: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime

# --- Circuit Models ---

class CircuitCreate(BaseModel):
    """Model for creating a new circuit"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    netlist: str = Field(..., description="SPICE netlist content")
    is_public: bool = False

class Circuit(BaseModel):
    """Circuit model for MongoDB"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str
    description: Optional[str] = None
    netlist: str
    owner_id: PyObjectId
    is_public: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }

class CircuitResponse(BaseModel):
    """Circuit response model"""
    id: str
    name: str
    description: Optional[str] = None
    netlist: str
    owner_id: str
    is_public: bool
    created_at: datetime
    updated_at: datetime

# --- Simulation History Models ---

class SimulationHistory(BaseModel):
    """Simulation history model for MongoDB"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId
    circuit_id: Optional[PyObjectId] = None
    circuit_name: str
    netlist: str
    analysis_type: AnalysisType
    analysis_parameters: Dict[str, Any]
    results: Dict[str, Any]  # Store the simulation results
    success: bool
    error_message: Optional[str] = None
    execution_time: Optional[float] = None  # in seconds
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }

class SimulationHistoryResponse(BaseModel):
    """Simulation history response model"""
    id: str
    user_id: str
    circuit_id: Optional[str] = None
    circuit_name: str
    analysis_type: AnalysisType
    success: bool
    error_message: Optional[str] = None
    execution_time: Optional[float] = None
    created_at: datetime

# --- Authentication Models ---

class Token(BaseModel):
    """JWT Token model"""
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    """Token data model"""
    username: Optional[str] = None

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
    save_to_history: bool = Field(True, description="Whether to save this simulation to user's history")

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