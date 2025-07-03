import PySpice.Logging.Logging as Logging
from PySpice.Spice.Netlist import Circuit
# Keep `from PySpice.Unit import *` as PySpice's simulator methods
# can often directly interpret strings like '10kOhm', '1us', '1kHz' etc.
# when passed as parameters, or when defining components.
from PySpice.Unit import *
import sys
import PySpice
from typing import Dict, List, Union, Any, Optional
# Removed `import re` as _parse_analysis_param is removed

# Import the models we defined
from .models import SimulationRequest, SimulationResults, NodeVoltageResult, BranchCurrentResult, AnalysisType

# Setup logging for PySpice
logger = Logging.setup_logging()

# # Configure the default SPICE simulator globally
# # THIS BLOCK MUST BE UNCOMMENTED FOR SIMULATIONS TO WORK
# if sys.platform == 'linux' or sys.platform == 'linux2':
PySpice.Spice.Simulation.CircuitSimulator.DEFAULT_SIMULATOR = 'ngspice-subprocess'
# elif sys.platform == 'win32':
#     # On Windows, PySpice might try to use a DLL or subprocess.
#     # If NGSPICE is in your PATH, 'ngspice-subprocess' might still work.
#     # Otherwise, direct DLL binding might be preferred if configured.
#     pass


class CircuitSimulatorService:
    """
    Service class to handle circuit creation, simulation, and result extraction
    using PySpice.
    """

    def __init__(self):
        # Any service-level initialization can go here
        pass

    def _create_circuit_from_netlist(self, netlist_string: str, circuit_name: str) -> Circuit:
        """
        Creates a PySpice Circuit object from a raw SPICE netlist string.
        """
        # PySpice provides a convenient way to parse a netlist string directly
        circuit = Circuit(circuit_name)
        # Append the raw netlist content. PySpice handles parsing.
        circuit.raw_spice = netlist_string
        return circuit

    # Removed the _parse_analysis_param method as it's no longer needed.
    # PySpice's simulator methods are expected to handle unit strings directly now.


    def _run_simulation(self, circuit: Circuit, analysis_type: AnalysisType, analysis_params: Dict[str, Union[str, float, int]]) -> Any:
        """
        Runs the specified simulation on the circuit.
        Returns the PySpice analysis object.
        """
        simulator = circuit.simulator(temperature=25, nominal_temperature=25)

        analysis = None # Initialize analysis variable

        if analysis_type == AnalysisType.OPERATING_POINT:
            # For OP analysis, parameters usually aren't needed but can be passed
            analysis = simulator.operating_point(**analysis_params)
        elif analysis_type == AnalysisType.TRANSIENT:
            # Transient analysis requires step_time and end_time
            step_time = analysis_params.get('step_time')
            end_time = analysis_params.get('end_time')
            if not step_time or not end_time:
                raise ValueError("Transient analysis requires 'step_time' and 'end_time' parameters.")
            
            parsed_step_time = self._parse_pyspice_unit_string(step_time)
            parsed_end_time = self._parse_pyspice_unit_string(end_time)
            print(f"DEBUG: step_time={step_time}, parsed_step_time={parsed_step_time}, end_time={end_time}, parsed_end_time={parsed_end_time}")
            # Pass parameters directly; PySpice's .tran method can interpret unit strings
            analysis = simulator.transient(step_time=parsed_step_time, end_time=parsed_end_time)
        
        elif analysis_type == AnalysisType.AC:
            # AC analysis requires start_frequency, stop_frequency, number_of_points, and sweep_type
            start_frequency = analysis_params.get('start_frequency')
            stop_frequency = analysis_params.get('stop_frequency') # Corrected keyword
            number_of_points = analysis_params.get('number_of_points')
            sweep_type = analysis_params.get('sweep_type', 'lin') # Default to linear sweep

            if not all([start_frequency, stop_frequency, number_of_points]):
                raise ValueError("AC analysis requires 'start_frequency', 'stop_frequency', and 'number_of_points'.")

            # Pass parameters directly; PySpice's .ac method can interpret unit strings
            analysis = simulator.ac(start_frequency=start_frequency,
                                    stop_frequency=stop_frequency, # Corrected keyword
                                    number_of_points=number_of_points,
                                    variation=sweep_type)
        
        elif analysis_type == AnalysisType.DC:
            # DC sweep analysis requires source, start, stop, step
            # Example: .dc Vsource 0 5 0.1
            source_name = analysis_params.get('source_name')
            start_value = analysis_params.get('start_value')
            end_value = analysis_params.get('end_value')
            step_value = analysis_params.get('step_value')
            if not all([source_name, start_value, end_value, step_value]):
                raise ValueError("DC analysis requires 'source_name', 'start_value', 'end_value', and 'step_value'.")

            # Pass parameters directly
            analysis = simulator.dc(source_name, start_value, end_value, step_value)

        elif analysis_type == AnalysisType.NOISE:
            # Noise analysis requires output_node, input_source, number_of_points, start_frequency, end_frequency, sweep_type
            # Example: .noise V(out) Vsource lin 10 1k 100k
            output_node = analysis_params.get('output_node')
            input_source = analysis_params.get('input_source')
            number_of_points = analysis_params.get('number_of_points')
            start_frequency = analysis_params.get('start_frequency')
            end_frequency = analysis_params.get('end_frequency') # Noise still uses end_frequency in PySpice
            sweep_type = analysis_params.get('sweep_type', 'lin')

            if not all([output_node, input_source, number_of_points, start_frequency, end_frequency]):
                raise ValueError("Noise analysis requires 'output_node', 'input_source', 'number_of_points', 'start_frequency', and 'end_frequency'.")

            # Pass parameters directly
            analysis = simulator.noise(output_node, input_source, number_of_points, start_frequency, end_frequency, variation=sweep_type)

        elif analysis_type == AnalysisType.FOURIER:
            # Fourier analysis is often performed on transient results.
            # PySpice's .four method might be part of transient analysis results post-processing
            # or a direct simulator method depending on PySpice version.
            # This implementation assumes a direct simulator call if available.
            output_variable = analysis_params.get('output_variable') # e.g., 'V(out)', 'I(R1)'
            fundamental_frequency = analysis_params.get('fundamental_frequency')

            if not all([output_variable, fundamental_frequency]):
                raise ValueError("Fourier analysis requires 'output_variable' and 'fundamental_frequency'.")

            # Pass parameters directly
            analysis = simulator.fourier(output_variable, fundamental_frequency)

        else:
            raise ValueError(f"Unsupported analysis type: {analysis_type}")

        return analysis


    def simulate_circuit(self, request: SimulationRequest) -> SimulationResults:
        """
        Main function to process a simulation request.
        """
        try:
            # 1. Create Circuit from Netlist String
            circuit = self._create_circuit_from_netlist(request.netlist_string, request.circuit_name)
            print(f"--- Circuit Netlist for '{request.circuit_name}':\n{circuit}\n---") # For debugging

            # 2. Run Simulation
            analysis = self._run_simulation(circuit, request.analysis_type, request.analysis_parameters)

            # Debug: Print all available node voltages and branch currents (for internal debugging)
            # Corrected to use [0] for operating point results to avoid DeprecationWarning
            print("Available node voltages:")
            for node_name, value in analysis.nodes.items(): # Iterate using .items() for clarity
                # Check if it's a scalar (like from .op) or an array (like from .tran/.ac)
                # For consistency and to avoid DeprecationWarning, always try to get [0] if it's an array-like
                if hasattr(value, '__getitem__') and len(value) > 0:
                    print(f"  Node {node_name}: {float(value[0])} V")
                else:
                    print(f"  Node {node_name}: {float(value)} V") # Fallback for truly scalar (non-array) types if any
            print("Available branch currents:")
            for branch_name, value in analysis.branches.items(): # Iterate using .items() for clarity
                # Check if it's a scalar (like from .op) or an array (like from .tran/.ac)
                # For consistency and to avoid DeprecationWarning, always try to get [0] if it's an array-like
                if hasattr(value, '__getitem__') and len(value) > 0:
                    print(f"  Branch {branch_name}: {float(value[0])} A")
                else:
                    print(f"  Branch {branch_name}: {float(value)} A") # Fallback for truly scalar (non-array) types if any


            # 3. Extract and Format Requested Results
            node_voltages: List[NodeVoltageResult] = []
            branch_currents: List[BranchCurrentResult] = []
            time_axis: Optional[List[float]] = None
            frequency_axis: Optional[List[float]] = None

            # Extract only the specifically requested results
            for req_result in request.requested_results:
                result_type = req_result['type']
                result_name = req_result['name'] # This is the name from the request payload

                if result_type == 'node_voltage':
                    # Use dictionary-style access for robustness
                    if result_name in analysis.nodes: # Check if key exists
                        voltage_waveform = analysis.nodes[result_name] # Access using key
                        if request.analysis_type == AnalysisType.OPERATING_POINT:
                            # For OP, it's a single value (extract [0] to avoid warning)
                            node_voltages.append(NodeVoltageResult(
                                node=result_name,
                                voltage=float(voltage_waveform[0]),
                                unit=str(voltage_waveform.unit)
                            ))
                        else:
                            # For TRAN/AC, it's a series of values
                            node_voltages.append(NodeVoltageResult(
                                node=result_name,
                                voltage=[float(v) for v in voltage_waveform],
                                unit=str(voltage_waveform.unit)
                            ))
                    else:
                        logger.warning(f"Requested node voltage for '{result_name}' not found in analysis results.")

                elif result_type == 'branch_current':
                    # Use dictionary-style access for robustness
                    if result_name in analysis.branches: # Check if key exists
                        current_waveform = analysis.branches[result_name] # Access using key
                        if request.analysis_type == AnalysisType.OPERATING_POINT:
                            branch_currents.append(BranchCurrentResult(
                                branch=result_name,
                                current=float(current_waveform[0]),
                                unit=str(current_waveform.unit)
                            ))
                        else:
                            branch_currents.append(BranchCurrentResult(
                                branch=result_name,
                                current=[float(c) for c in current_waveform],
                                unit=str(current_waveform.unit)
                            ))
                    else:
                        logger.warning(f"Requested branch current for '{result_name}' not found directly in analysis.branches.")
                        # --- OPTIONAL: Add logic here to calculate resistor currents via Ohm's Law ---
                        # Example: If result_name is 'R1', and you know its nodes and value
                        # You'd need a way to get component values from the circuit object or netlist
                        # For now, this is a warning.

            # Handle Time/Frequency Axis for plotting
            if request.analysis_type == AnalysisType.TRANSIENT:
                if hasattr(analysis, 'time'): # Check if 'time' attribute exists
                    time_axis = [float(t) for t in analysis.time]
                else:
                    logger.warning("Transient analysis performed, but 'time' axis not found in analysis object.")
            elif request.analysis_type == AnalysisType.AC:
                if hasattr(analysis, 'frequency'): # Check if 'frequency' attribute exists
                    frequency_axis = [float(f) for f in analysis.frequency]
                else:
                    logger.warning("AC analysis performed, but 'frequency' axis not found in analysis object.")


            return SimulationResults(
                success=True,
                message="Simulation completed successfully.",
                simulation_type=request.analysis_type,
                node_voltages=node_voltages,
                branch_currents=branch_currents,
                time_axis=time_axis,
                frequency_axis=frequency_axis
            )

        except Exception as e:
            logger.error(f"Simulation failed: {e}", exc_info=True)
            return SimulationResults(
                success=False,
                message=f"Simulation failed: {str(e)}",
                simulation_type=request.analysis_type, # Even on failure, report type
            )

    def _parse_pyspice_unit_string(self, value: str) -> float:
        """
        Converts a string like '1u', '5ms', '0.01', or a number to a float value for PySpice.
        Returns None if the value is invalid.
        """
        if value is None:
            return None
        try:
            if isinstance(value, (int, float)):
                return float(value)
            value = value.strip().lower()
            unit_map = {
                'ps': 1e-12, 'ns': 1e-9, 'us': 1e-6, 'ms': 1e-3, 's': 1,
                'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3,
                'k': 1e3, 'meg': 1e6, 'g': 1e9, 't': 1e12
            }
            import re
            match = re.match(r'^([\d\.eE+-]+)\s*([a-zA-Z]+)?$', value)
            if match:
                num_str = match.group(1)
                unit = match.group(2)
                if not num_str or num_str == '' or (unit and not num_str.replace('.', '', 1).isdigit()):
                    return None
                num = float(num_str)
                if unit is None:
                    return num
                unit = unit.lower()
                for k in sorted(unit_map, key=len, reverse=True):
                    if unit == k:
                        return num * unit_map[k]
                return None
            # fallback: try to convert directly
            return float(value)
        except Exception:
            return None
