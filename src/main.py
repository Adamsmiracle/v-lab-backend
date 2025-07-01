from fastapi import FastAPI, HTTPException, status
from .models import SimulationRequest, SimulationResults, ErrorResponse
from .circuit_services import CircuitSimulatorService # Ensure this matches your filename (plural 'services')
import subprocess


# Create FastAPI app instance
# Set a descriptive title and description for your API documentation (Swagger UI/Redoc)
app = FastAPI(
    title="V lab backend",
    description="A backend service for simulating electronic circuits using PySpice and NGSPICE. "
                "Receive SPICE netlists, run simulations, and return structured results.",
    version="1.0.0",
)

# Initialize the circuit simulation service
# This creates an instance of your service class that handles PySpice interactions
circuit_service = CircuitSimulatorService()

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


async def run_simulation(request: SimulationRequest):
    """
    Handles the POST request to run a circuit simulation.

    Args:
        request (SimulationRequest): The incoming request body, validated by Pydantic.
                                     It contains the netlist, analysis type, parameters, and requested outputs.

    Returns:
        SimulationResults: A Pydantic model containing the simulation outcomes
                           (success status, message, and requested data).

    Raises:
        HTTPException: If the input is invalid or a simulation error occurs,
                       appropriate HTTP status codes and error messages are returned.
    """
    try:
        # Call the circuit service to perform the simulation
        results = circuit_service.simulate_circuit(request)

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

# This block allows you to run the FastAPI application directly using Uvicorn
# when you execute `python main.py` during development.
# In a production environment, you would typically use a WSGI server like Gunicorn
# to run Uvicorn workers.
if __name__ == "__main__":
    import uvicorn
    # The --reload flag automatically reloads the server when code changes are detected.
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)


