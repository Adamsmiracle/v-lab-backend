from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import List
import subprocess
import time
from datetime import timedelta

from .models import (
    SimulationRequest, SimulationResults, ErrorResponse,
    UserCreate, UserLogin, UserResponse, Token,
    CircuitCreate, CircuitResponse,
    SimulationHistoryResponse
)
from .circuit_services import CircuitSimulatorService
from .database import connect_to_mongo, close_mongo_connection
from .auth import auth_service, get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES
from .services import circuit_service, simulation_history_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_to_mongo()
    yield
    # Shutdown
    await close_mongo_connection()

# Create FastAPI app instance
# Set a descriptive title and description for your API documentation (Swagger UI/Redoc)
app = FastAPI(
    title="V-Lab Backend",
    description="A backend service for simulating electronic circuits using PySpice and NGSPICE. "
                "Includes user authentication, circuit management, and simulation history.",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the circuit simulation service
# This creates an instance of your service class that handles PySpice interactions
circuit_simulator_service = CircuitSimulatorService()

@app.get("/health", summary="Health Check")
async def read_root():
    """
    Basic health check endpoint to ensure the backend is running.
    """

    # Check if the ngspice command is available and can run
    result = subprocess.run(
                ['ngspice', '-v'],
                capture_output=True,
                text=True,
                check=True, # Raise CalledProcessError if return code is non-zero
                timeout=5 # seconds
            )
    return {"Backend_dependecies": result, "message": "Circuit simulator backend is running and ready!"}



# Simulation backend endpoint
# This endpoint accepts a raw SPICE netlist string and simulation parameters,
# runs the simulation using PySpice, and returns the requested node voltages,
# branch currents, and time/frequency data.
@app.post(
    "/simulate",
    response_model=SimulationResults, # Specifies the Pydantic model for the successful response
    summary="Run Circuit Simulation",
    description="Accepts a raw SPICE netlist string and simulation parameters (e.g., analysis type, "
                "duration for transient, frequencies for AC). It then runs the simulation using PySpice "
                "and returns the requested node voltages, branch currents, and time/frequency data.",
    responses={
        200: {"description": "Simulation completed successfully. Returns structured results."},
        400: {"model": ErrorResponse, "description": "Bad Request: Invalid input data or simulation failed due to circuit error."},
        500: {"model": ErrorResponse, "description": "Internal Server Error: An unexpected error occurred on the server side."}
    }
)


async def run_simulation(
    request: SimulationRequest,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Handles the POST request to run a circuit simulation for authenticated users.

    Args:
        request (SimulationRequest): The incoming request body, validated by Pydantic.
                                     It contains the netlist, analysis type, parameters, and requested outputs.
        current_user (UserResponse): The authenticated user making the request.

    Returns:
        SimulationResults: A Pydantic model containing the simulation outcomes
                           (success status, message, and requested data).

    Raises:
        HTTPException: If the input is invalid or a simulation error occurs,
                       appropriate HTTP status codes and error messages are returned.
    """
    try:
        # Record start time for performance tracking
        start_time = time.time()
        
        # Call the circuit service to perform the simulation
        results = circuit_simulator_service.simulate_circuit(request)
        
        # Calculate execution time
        execution_time = time.time() - start_time
        
        # Save simulation to history if requested
        if request.save_to_history:
            try:
                await simulation_history_service.save_simulation(
                    user=current_user,
                    simulation_request=request,
                    simulation_results=results,
                    execution_time=execution_time
                )
            except Exception as e:
                # Log the error but don't fail the simulation
                print(f"Failed to save simulation history: {e}")

        # Check the success flag from the service to determine the HTTP response
        if not results.success:
            # If the service indicates a simulation failure, return a 400 Bad Request
            # This is for logical errors within the simulation, e.g., invalid netlist
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    message=results.message,
                    details="Please check your netlist syntax or simulation parameters."
                ).model_dump() # Convert Pydantic model to dictionary for FastAPI detail
            )
        return results

    except ValueError as ve:
        # Catch specific validation errors (e.g., missing analysis parameters)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                message="Invalid simulation parameters.",
                details=str(ve) # This line was moved inside the ErrorResponse constructor
            ).model_dump()
        )

    except Exception as e:
        # Catch any other unexpected exceptions that might occur
        # Log the full traceback for debugging on the server side
        print(f"Unhandled exception in /simulate endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                message="An unexpected internal server error occurred.",
                details="Please contact support or try again later."
            ).model_dump()
        )

# Non-authenticated simulation endpoint for testing
@app.post(
    "/simulate-test",
    response_model=SimulationResults,
    summary="Run Circuit Simulation (No Auth)",
    description="Test endpoint for circuit simulation without authentication required.",
    responses={
        200: {"description": "Simulation completed successfully. Returns structured results."},
        400: {"model": ErrorResponse, "description": "Bad Request: Invalid input data or simulation failed due to circuit error."},
        500: {"model": ErrorResponse, "description": "Internal Server Error: An unexpected error occurred on the server side."}
    }
)
async def run_simulation_test(request: SimulationRequest):
    """
    Handles the POST request to run a circuit simulation without authentication.
    This is for testing purposes when the database is not available.
    """
    try:
        # Call the circuit service to perform the simulation
        results = circuit_simulator_service.simulate_circuit(request)

        # Check the success flag from the service to determine the HTTP response
        if not results.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    message=results.message,
                    details="Please check your netlist syntax or simulation parameters."
                ).model_dump()
            )
        return results

    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                message="Invalid simulation parameters.",
                details=str(ve)
            ).model_dump()
        )

    except Exception as e:
        print(f"Unhandled exception in /simulate-test endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                message="An unexpected internal server error occurred.",
                details="Please contact support or try again later."
            ).model_dump()
        )

# === Authentication Endpoints ===

@app.post("/auth/register", response_model=UserResponse, summary="Register New User")
async def register_user(user_create: UserCreate):
    """
    Register a new user account.
    """
    try:
        user = await auth_service.create_user(user_create)
        return UserResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            created_at=user.created_at
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {str(e)}"
        )

@app.post("/auth/login", response_model=Token, summary="User Login")
async def login_user(user_login: UserLogin):
    """
    Authenticate user and return access token.
    """
    try:
        user = await auth_service.authenticate_user(user_login.username, user_login.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth_service.create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        
        return Token(access_token=access_token, token_type="bearer")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )

@app.get("/auth/me", response_model=UserResponse, summary="Get Current User")
async def get_current_user_info(current_user: UserResponse = Depends(get_current_user)):
    """
    Get current authenticated user information.
    """
    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        created_at=current_user.created_at
    )

# === Circuit Management Endpoints ===

@app.post("/circuits", response_model=CircuitResponse, summary="Create Circuit")
async def create_circuit(
    circuit_create: CircuitCreate,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Create a new circuit for the authenticated user.
    """
    try:
        circuit = await circuit_service.create_circuit(circuit_create, current_user)
        return circuit
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create circuit: {str(e)}"
        )

@app.get("/circuits", response_model=List[CircuitResponse], summary="Get User Circuits")
async def get_user_circuits(current_user: UserResponse = Depends(get_current_user)):
    """
    Get all circuits for the authenticated user.
    """
    try:
        circuits = await circuit_service.get_user_circuits(current_user)
        return circuits
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve circuits: {str(e)}"
        )

@app.get("/circuits/{circuit_id}", response_model=CircuitResponse, summary="Get Circuit by ID")
async def get_circuit(
    circuit_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get a specific circuit by ID.
    """
    try:
        circuit = await circuit_service.get_circuit_by_id(circuit_id, current_user)
        if not circuit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Circuit not found"
            )
        return circuit
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve circuit: {str(e)}"
        )

@app.put("/circuits/{circuit_id}", response_model=CircuitResponse, summary="Update Circuit")
async def update_circuit(
    circuit_id: str,
    circuit_update: CircuitCreate,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Update a circuit (only if user owns it).
    """
    try:
        circuit = await circuit_service.update_circuit(circuit_id, circuit_update, current_user)
        if not circuit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Circuit not found or you don't have permission to update it"
            )
        return circuit
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update circuit: {str(e)}"
        )

@app.delete("/circuits/{circuit_id}", summary="Delete Circuit")
async def delete_circuit(
    circuit_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Delete a circuit (only if user owns it).
    """
    try:
        success = await circuit_service.delete_circuit(circuit_id, current_user)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Circuit not found or you don't have permission to delete it"
            )
        return {"message": "Circuit deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete circuit: {str(e)}"
        )

# === Simulation History Endpoints ===

@app.get("/simulations", response_model=List[SimulationHistoryResponse], summary="Get Simulation History")
async def get_simulation_history(
    limit: int = 50,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get simulation history for the authenticated user.
    """
    try:
        history = await simulation_history_service.get_user_simulations(current_user, limit)
        return history
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve simulation history: {str(e)}"
        )

@app.get("/simulations/{simulation_id}", summary="Get Simulation Details")
async def get_simulation_details(
    simulation_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get detailed simulation results by ID.
    """
    try:
        simulation = await simulation_history_service.get_simulation_by_id(simulation_id, current_user)
        if not simulation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Simulation not found"
            )
        return simulation
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve simulation details: {str(e)}"
        )

# This block allows you to run the FastAPI application directly using Uvicorn
# when you execute `python main.py` during development.
# In a production environment, you would typically use a WSGI server like Gunicorn
# to run Uvicorn workers.
if __name__ == "__main__":
    import uvicorn
    # The --reload flag automatically reloads the server when code changes are detected.
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)


