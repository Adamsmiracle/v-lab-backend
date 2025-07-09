# Apply ngspice compatibility patch BEFORE importing PySpice components
try:
    from . import pyspice_patch
except ImportError:
    # Handle case when module is imported directly (not as package)
    import pyspice_patch

import PySpice.Logging.Logging as Logging
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
import sys
import PySpice
from typing import Dict, List, Union, Any, Optional
import re
import subprocess
import tempfile
import os

# Import the models we defined
from .models import SimulationRequest, SimulationResults, NodeVoltageResult, BranchCurrentResult, AnalysisType

# Setup logging for PySpice
logger = Logging.setup_logging()

# Configure the default SPICE simulator globally
if sys.platform == 'linux' or sys.platform == 'linux2':
    PySpice.Spice.Simulation.CircuitSimulator.DEFAULT_SIMULATOR = 'ngspice-subprocess'

class NgspiceWrapper:
    """Custom ngspice simulation wrapper that bypasses PySpice's parsing issues"""
    
    def __init__(self):
        self.ngspice_path = self._find_ngspice()
    
    def _find_ngspice(self) -> str:
        """Find the ngspice executable"""
        for path in ['/usr/local/bin/ngspice', '/usr/bin/ngspice', 'ngspice']:
            if os.path.exists(path) or subprocess.run(['which', path], capture_output=True).returncode == 0:
                return path
        raise RuntimeError("ngspice not found")
    
    def _parse_output(self, output: str, analysis_type: str = 'op') -> Dict[str, Any]:
        """Parse ngspice text output for different analysis types"""
        results = {
            'node_voltages': {},
            'branch_currents': {},
            'success': True,
            'error': None,
            'time_axis': None,
            'frequency_axis': None
        }
        
        lines = output.split('\n')
        
        if analysis_type == 'op':
            # Operating point analysis parsing
            voltage_section = False
            current_section = False
            
            for line in lines:
                line = line.strip()
                
                # Check for error conditions
                if 'error' in line.lower() or 'fatal' in line.lower():
                    results['success'] = False
                    results['error'] = line
                    continue
                
                # Detect sections
                if 'Node' in line and 'Voltage' in line:
                    voltage_section = True
                    current_section = False
                    continue
                elif 'Source' in line and 'Current' in line:
                    voltage_section = False
                    current_section = True
                    continue
                elif line.startswith('----') or line == '':
                    continue
                
                # Parse voltage data
                if voltage_section and line and not line.startswith('----'):
                    # Match lines like "out                              3.333333e+00"
                    match = re.match(r'(\S+)\s+([+-]?\d+\.?\d*[eE]?[+-]?\d*)', line)
                    if match:
                        node_name = match.group(1)
                        voltage = float(match.group(2))
                        results['node_voltages'][node_name] = voltage
                
                # Parse current data
                if current_section and line and not line.startswith('----'):
                    # Match lines like "v1#branch                        -1.66667e-03"
                    match = re.match(r'(\S+)\s+([+-]?\d+\.?\d*[eE]?[+-]?\d*)', line)
                    if match:
                        source_name = match.group(1)
                        current = float(match.group(2))
                        results['branch_currents'][source_name] = current
        
        elif analysis_type == 'ac':
            # AC analysis parsing - extract frequency response data
            results['node_voltages'] = {}
            results['frequency_axis'] = []
            
            # Look for frequency data format from ngspice
            data_started = False
            current_node = None
            
            for line in lines:
                line = line.strip()
                
                # Check for error conditions
                if 'error' in line.lower() or 'fatal' in line.lower():
                    results['success'] = False
                    results['error'] = line
                    continue
                
                # Look for frequency sweep data
                if 'frequency' in line.lower() and 'magnitude' in line.lower():
                    data_started = True
                    continue
                
                # Extract frequency and magnitude data
                if data_started and line and not line.startswith('----'):
                    # Parse frequency response format: freq magnitude phase
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            freq = float(parts[0])
                            magnitude = float(parts[1])
                            if not results['frequency_axis']:
                                results['frequency_axis'] = [freq]
                                results['node_voltages']['magnitude'] = [magnitude]
                            else:
                                results['frequency_axis'].append(freq)
                                results['node_voltages']['magnitude'].append(magnitude)
                        except ValueError:
                            continue
        
        elif analysis_type == 'tran':
            # Transient analysis parsing - extract time-domain data
            results['node_voltages'] = {}
            results['time_axis'] = []
            
            # Look for tabular data with time column
            data_started = False
            header_columns = []
            
            for line in lines:
                line = line.strip()
                
                # Check for error conditions
                if 'error' in line.lower() or 'fatal' in line.lower():
                    results['success'] = False
                    results['error'] = line
                    continue
                
                # Skip empty lines
                if not line:
                    continue
                
                # Look for header line with column names
                if 'time' in line.lower() and ('v(' in line.lower() or 'i(' in line.lower()):
                    # Header line like: "Index   time            v(in)           v(out)          v1#branch"
                    parts = line.split()
                    header_columns = parts[1:]  # Skip 'Index' column
                    data_started = True
                    continue
                
                # Look for separator line
                if line.startswith('----'):
                    continue
                
                # Parse data lines
                if data_started and line and not line.startswith('Index'):
                    # Parse data line: "0	0.000000e+00	0.000000e+00	0.000000e+00	0.000000e+00"
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            # Skip index column, get time and values
                            time_val = float(parts[1])
                            values = [float(p) for p in parts[2:]]
                            
                            results['time_axis'].append(time_val)
                            
                            # Map values to node names
                            for i, value in enumerate(values):
                                if i < len(header_columns):
                                    col_name = header_columns[i]
                                    
                                    # Extract node name from column header
                                    if col_name.startswith('v(') and col_name.endswith(')'):
                                        node_name = col_name[2:-1]  # Remove 'v(' and ')'
                                        if node_name not in results['node_voltages']:
                                            results['node_voltages'][node_name] = []
                                        results['node_voltages'][node_name].append(value)
                                    elif '#branch' in col_name:
                                        # Handle branch currents like 'v1#branch'
                                        if col_name not in results['branch_currents']:
                                            results['branch_currents'][col_name] = []
                                        results['branch_currents'][col_name].append(value)
                        except (ValueError, IndexError):
                            continue
        
        return results
    
    def _parse_ac_output(self, output: str, nodes: List[str]) -> Dict[str, Any]:
        """Parse AC analysis output from ngspice print commands"""
        results = {
            'node_voltages': {},
            'branch_currents': {},
            'success': True,
            'error': None,
            'frequency_axis': []
        }
        
        lines = output.split('\n')
        
        # Initialize node voltage arrays
        for node in nodes:
            results['node_voltages'][node] = []
        
        # Look for tabular data output
        in_data_section = False
        for line in lines:
            line = line.strip()
            
            # Check for error conditions
            if 'error' in line.lower() or 'fatal' in line.lower():
                results['success'] = False
                results['error'] = line
                continue
            
            # Check if we're in the data section
            if 'Index' in line and 'frequency' in line:
                in_data_section = True
                continue
            
            # Skip lines until we reach the data section
            if not in_data_section:
                continue
            
            # Skip separator lines
            if line.startswith('-') or not line:
                continue
            
            # Parse data lines (index, frequency, node values with magnitude and phase)
            parts = line.split()
            if len(parts) >= 3:
                try:
                    # Skip index (first column)
                    freq = float(parts[1])
                    results['frequency_axis'].append(freq)
                    
                    # Parse complex values for each node
                    # Format: magnitude,phase (comma-separated)
                    value_start = 2
                    for i, node in enumerate(nodes):
                        if value_start + i < len(parts):
                            value_str = parts[value_start + i]
                            # Remove trailing comma if present
                            if value_str.endswith(','):
                                value_str = value_str[:-1]
                            
                            # Extract magnitude (real part before comma)
                            magnitude = float(value_str)
                            results['node_voltages'][node].append(magnitude)
                except (ValueError, IndexError):
                    continue
        
        return results
    
    def _parse_tran_output(self, output: str, nodes: List[str], sources: List[str] = None) -> Dict[str, Any]:
        """Parse transient analysis output from ngspice print commands"""
        if sources is None:
            sources = []
            
        results = {
            'node_voltages': {},
            'branch_currents': {},
            'success': True,
            'error': None,
            'time_axis': []
        }
        
        lines = output.split('\n')
        
        # Initialize node voltage arrays
        for node in nodes:
            results['node_voltages'][node] = []
        
        # Initialize branch current arrays with proper source names
        for source in sources:
            results['branch_currents'][f"{source.lower()}#branch"] = []
        
        # Look for tabular data output
        in_data_section = False
        for line in lines:
            line = line.strip()
            
            # Check for error conditions
            if 'error' in line.lower() or 'fatal' in line.lower():
                results['success'] = False
                results['error'] = line
                continue
            
            # Check if we're in the data section
            if 'Index' in line and 'time' in line:
                in_data_section = True
                continue
            
            # Skip lines until we reach the data section
            if not in_data_section:
                continue
            
            # Skip separator lines and status lines
            if (line.startswith('-') or not line or 'Total' in line or 'DRAM' in line or 
                'Maximum' in line or 'Current' in line or 'Shared' in line or 
                'Text' in line or 'Stack' in line or 'Library' in line):
                continue
            
            # Parse data lines (index, time, node voltages, branch currents)
            parts = line.split()
            if len(parts) >= 3:
                try:
                    # Skip index (first column), get time (second column)
                    time = float(parts[1])
                    results['time_axis'].append(time)
                    
                    # Parse node voltages starting from column 2
                    # Format: index, time, v(node1), v(node2), ..., i(source1), i(source2), ...
                    value_start = 2
                    for i, node in enumerate(nodes):
                        if value_start + i < len(parts):
                            voltage = float(parts[value_start + i])
                            results['node_voltages'][node].append(voltage)
                    
                    # Parse branch currents (they come after node voltages)
                    branch_start = value_start + len(nodes)
                    for i, source in enumerate(sources):
                        if branch_start + i < len(parts):
                            current = float(parts[branch_start + i])
                            branch_key = f"{source.lower()}#branch"
                            results['branch_currents'][branch_key].append(current)
                            
                except (ValueError, IndexError):
                    continue
        
        return results
    
    def simulate_op(self, netlist: str, circuit_name: str = "Circuit") -> Dict[str, Any]:
        """Run operating point simulation"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False) as f:
                # Ensure proper netlist format
                if not netlist.strip().startswith('.title'):
                    netlist = f".title {circuit_name}\n{netlist}"
                
                # Ensure .op directive is present
                if '.op' not in netlist.lower():
                    # Insert .op before .end if .end exists
                    if '.end' in netlist.lower():
                        netlist = netlist.replace('.end', '.op\n.end')
                    else:
                        netlist = f"{netlist}\n.op"
                
                if not netlist.strip().endswith('.end'):
                    netlist = f"{netlist}\n.end"
                
                f.write(netlist)
                netlist_file = f.name
            
            # Run ngspice
            result = subprocess.run(
                [self.ngspice_path, '-b', netlist_file],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Clean up
            os.unlink(netlist_file)
            
            if result.returncode == 0:
                return self._parse_output(result.stdout, 'op')
            else:
                return {
                    'success': False,
                    'error': f"ngspice failed: {result.stderr}",
                    'node_voltages': {},
                    'branch_currents': {}
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'node_voltages': {},
                'branch_currents': {}
            }
    
    def simulate_ac(self, netlist: str, circuit_name: str = "Circuit", 
                    start_freq: float = 1e3, stop_freq: float = 1e6, 
                    num_points: int = 100, sweep_type: str = "dec") -> Dict[str, Any]:
        """Run AC analysis simulation"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False) as f:
                # Ensure proper netlist format
                if not netlist.strip().startswith('.title'):
                    netlist = f".title {circuit_name}\n{netlist}"
                
                # Extract nodes from netlist to know what to print
                nodes_to_print = []
                sources_to_print = []
                lines = netlist.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('.') and not line.startswith('*'):
                        parts = line.split()
                        if len(parts) >= 3:
                            component_name = parts[0]
                            # Get node names (skip component name)
                            node1, node2 = parts[1], parts[2]
                            if node1 not in ['0', 'gnd'] and node1 not in nodes_to_print:
                                nodes_to_print.append(node1)
                            if node2 not in ['0', 'gnd'] and node2 not in nodes_to_print:
                                nodes_to_print.append(node2)
                            
                            # Track voltage sources for current measurement
                            if component_name.upper().startswith('V'):
                                sources_to_print.append(component_name)
                
                # Add AC analysis directive
                ac_directive = f".ac {sweep_type} {num_points} {start_freq} {stop_freq}"
                if '.ac' not in netlist.lower():
                    # Insert .ac before .end if .end exists
                    if '.end' in netlist.lower():
                        netlist = netlist.replace('.end', f'{ac_directive}\n.end')
                    else:
                        netlist = f"{netlist}\n{ac_directive}"
                
                # Add print commands for AC analysis
                print_commands = []
                for node in nodes_to_print:
                    print_commands.append(f".print ac v({node})")
                
                # Insert print commands before .end
                if '.end' in netlist.lower():
                    print_block = '\n'.join(print_commands) + '\n'
                    netlist = netlist.replace('.end', f'{print_block}.end')
                else:
                    netlist = f"{netlist}\n{chr(10).join(print_commands)}"
                
                if not netlist.strip().endswith('.end'):
                    netlist = f"{netlist}\n.end"
                
                f.write(netlist)
                netlist_file = f.name
            
            # Run ngspice
            result = subprocess.run(
                [self.ngspice_path, '-b', netlist_file],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Clean up
            os.unlink(netlist_file)
            
            if result.returncode == 0:
                return self._parse_ac_output(result.stdout, nodes_to_print)
            else:
                return {
                    'success': False,
                    'error': f"ngspice failed: {result.stderr}",
                    'node_voltages': {},
                    'branch_currents': {},
                    'frequency_axis': None
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'node_voltages': {},
                'branch_currents': {},
                'frequency_axis': None
            }
    
    def simulate_transient(self, netlist: str, circuit_name: str = "Circuit", 
                          step_time: str = "1us", end_time: str = "1ms") -> Dict[str, Any]:
        """Run transient analysis simulation"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False) as f:
                # Ensure proper netlist format
                if not netlist.strip().startswith('.title'):
                    netlist = f".title {circuit_name}\n{netlist}"
                
                # Extract nodes from netlist to know what to print
                nodes_to_print = []
                sources_to_print = []
                lines = netlist.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('.') and not line.startswith('*'):
                        parts = line.split()
                        if len(parts) >= 3:
                            component_name = parts[0]
                            component_type = component_name[0].upper()
                            
                            # Get node names (skip component name)
                            node1, node2 = parts[1], parts[2]
                            if node1 not in ['0', 'gnd'] and node1 not in nodes_to_print:
                                nodes_to_print.append(node1)
                            if node2 not in ['0', 'gnd'] and node2 not in nodes_to_print:
                                nodes_to_print.append(node2)
                            
                            # Track voltage sources for current measurements
                            if component_type == 'V':
                                sources_to_print.append(component_name)
                
                # Add transient analysis directive
                tran_directive = f".tran {step_time} {end_time}"
                if '.tran' not in netlist.lower():
                    # Insert .tran before .end if .end exists
                    if '.end' in netlist.lower():
                        netlist = netlist.replace('.end', f'{tran_directive}\n.end')
                    else:
                        netlist = f"{netlist}\n{tran_directive}"
                
                # Add single print command for transient analysis
                print_items = []
                for node in nodes_to_print:
                    print_items.append(f"v({node})")
                for source in sources_to_print:
                    print_items.append(f"i({source})")
                
                if print_items:
                    print_directive = f".print tran {' '.join(print_items)}"
                    # Insert print command before .end
                    if '.end' in netlist.lower():
                        netlist = netlist.replace('.end', f'{print_directive}\n.end')
                    else:
                        netlist = f"{netlist}\n{print_directive}"
                
                if not netlist.strip().endswith('.end'):
                    netlist = f"{netlist}\n.end"
                
                f.write(netlist)
                netlist_file = f.name
            
            # Run ngspice
            result = subprocess.run(
                [self.ngspice_path, '-b', netlist_file],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Clean up
            os.unlink(netlist_file)
            
            if result.returncode == 0:
                return self._parse_tran_output(result.stdout, nodes_to_print, sources_to_print)
            else:
                return {
                    'success': False,
                    'error': f"ngspice failed: {result.stderr}",
                    'node_voltages': {},
                    'branch_currents': {},
                    'time_axis': None
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'node_voltages': {},
                'branch_currents': {},
                'time_axis': None
            }

# ...existing code...

# Configure the default SPICE simulator globally
if sys.platform == 'linux' or sys.platform == 'linux2':
    PySpice.Spice.Simulation.CircuitSimulator.DEFAULT_SIMULATOR = 'ngspice-subprocess'

class CircuitSimulatorService:
    """
    Service class to handle circuit creation, simulation, and result extraction
    using PySpice with fallback to custom ngspice wrapper.
    """
    def __init__(self):
        self.ngspice_wrapper = NgspiceWrapper()
        self.use_fallback = True  # Start with fallback as primary method
    
    def _create_circuit_from_netlist(self, netlist_string: str, circuit_name: str) -> Circuit:
        """
        Creates a PySpice Circuit object from a raw SPICE netlist string.
        """
        try:
            # Create circuit object
            circuit = Circuit(circuit_name)
            
            # Parse netlist line by line
            lines = netlist_string.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('*') or line.startswith('.'):
                    continue
                    
                # Parse component lines
                self._parse_component_line(circuit, line)
            
            # Validate circuit before returning
            self._validate_circuit(circuit)
            
            return circuit
            
        except Exception as e:
            logger.error(f"Failed to create circuit from netlist: {e}")
            raise ValueError(f"Invalid netlist: {e}")
    
    def _parse_component_line(self, circuit: Circuit, line: str):
        """Parse a single component line and add to circuit"""
        parts = line.split()
        if len(parts) < 3:
            return
            
        component_name = parts[0]
        component_type = component_name[0].upper()
        
        try:
            if component_type == 'R':  # Resistor
                if len(parts) >= 4:
                    node1, node2, value = parts[1], parts[2], parts[3]
                    resistance = self._parse_value_with_units(value)
                    circuit.R(component_name, node1, node2, resistance)
                    
            elif component_type == 'C':  # Capacitor
                if len(parts) >= 4:
                    node1, node2, value = parts[1], parts[2], parts[3]
                    capacitance = self._parse_value_with_units(value)
                    circuit.C(component_name, node1, node2, capacitance)
                    
            elif component_type == 'L':  # Inductor
                if len(parts) >= 4:
                    node1, node2, value = parts[1], parts[2], parts[3]
                    inductance = self._parse_value_with_units(value)
                    circuit.L(component_name, node1, node2, inductance)
                    
            elif component_type == 'V':  # Voltage Source
                if len(parts) >= 4:
                    node1, node2, value = parts[1], parts[2], parts[3]
                    voltage = self._parse_value_with_units(value)
                    circuit.V(component_name, node1, node2, voltage)
                    
            elif component_type == 'I':  # Current Source
                if len(parts) >= 4:
                    node1, node2, value = parts[1], parts[2], parts[3]
                    current = self._parse_value_with_units(value)
                    circuit.I(component_name, node1, node2, current)
                    
        except Exception as e:
            logger.warning(f"Failed to parse component {component_name}: {e}")
    
    def _parse_value_with_units(self, value_str: str) -> float:
        """Parse component value with SPICE units"""
        if isinstance(value_str, (int, float)):
            return float(value_str)
            
        value_str = value_str.strip().lower()
        
        # Unit multipliers
        unit_map = {
            'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3,
            'k': 1e3, 'meg': 1e6, 'g': 1e9, 't': 1e12
        }
        
        # Extract number and unit
        match = re.match(r'^([\d\.eE+-]+)\s*([a-zA-Z]+)?$', value_str)
        if match:
            num_str = match.group(1)
            unit = match.group(2)
            
            num = float(num_str)
            
            if unit:
                unit = unit.lower()
                for unit_key in sorted(unit_map.keys(), key=len, reverse=True):
                    if unit.startswith(unit_key):
                        return num * unit_map[unit_key]
            
            return num
        
        return float(value_str)
    
    def _validate_circuit(self, circuit: Circuit):
        """Validate circuit for common issues that cause singular matrix"""
        nodes = set()
        has_ground = False
        voltage_sources = []
        
        # Collect all nodes and check for ground
        for element in circuit.elements:
            if hasattr(element, 'nodes'):
                for node in element.nodes:
                    if node == '0' or node == 'gnd' or node == 'ground':
                        has_ground = True
                    nodes.add(node)
            
            # Check for voltage sources
            if hasattr(element, 'name') and element.name.startswith('V'):
                voltage_sources.append(element)
        
        # Ensure ground exists
        if not has_ground:
            logger.warning("Circuit may not have proper ground connection")
        
        # Check for floating nodes (basic check)
        if len(nodes) < 2:
            raise ValueError("Circuit must have at least 2 nodes")
        
        # Add small conductance to help convergence if needed
        self._add_convergence_aids(circuit)
    
    def _add_convergence_aids(self, circuit: Circuit):
        """Add small resistances to help with convergence"""
        try:
            # Add small resistance to ground to help with floating nodes
            # Use 1e9 ohms (1 GΩ) for very high resistance
            circuit.R('Rconv_gnd', 'gnd', circuit.gnd, 1e9)  # Default unit is Ohms
        except:
            # If ground reference doesn't exist, skip this aid
            pass
    
    def _run_simulation(self, circuit: Circuit, analysis_type: AnalysisType, analysis_params: Dict[str, Union[str, float, int]], original_netlist: str = None) -> Any:
        """
        Runs the specified simulation on the circuit with improved error handling.
        Uses fallback ngspice wrapper as primary method due to PySpice compatibility issues.
        """
        
        # Try fallback method first (recommended due to PySpice/ngspice-38 compatibility issues)
        if self.use_fallback and original_netlist:
            try:
                logger.info("Using fallback ngspice wrapper for simulation...")
                result = None
                
                if analysis_type == AnalysisType.OPERATING_POINT:
                    result = self.ngspice_wrapper.simulate_op(original_netlist, getattr(circuit, 'title', 'Circuit'))
                elif analysis_type == AnalysisType.AC:
                    # Extract AC parameters
                    start_freq = analysis_params.get('start_frequency', 1e3)
                    stop_freq = analysis_params.get('stop_frequency', 1e6)
                    num_points = analysis_params.get('number_of_points', 100)
                    sweep_type = analysis_params.get('sweep_type', 'dec')
                    result = self.ngspice_wrapper.simulate_ac(original_netlist, getattr(circuit, 'title', 'Circuit'),
                                                            start_freq, stop_freq, num_points, sweep_type)
                elif analysis_type == AnalysisType.TRANSIENT:
                    # Extract transient parameters
                    step_time = analysis_params.get('step_time', '1us')
                    end_time = analysis_params.get('end_time', '1ms')
                    result = self.ngspice_wrapper.simulate_transient(original_netlist, getattr(circuit, 'title', 'Circuit'),
                                                                   step_time, end_time)
                
                if result and result['success']:
                    logger.info("Fallback simulation successful!")
                    
                    # Create a mock analysis object that mimics PySpice's analysis results
                    class MockAnalysis:
                        def __init__(self, node_voltages, branch_currents, time_axis=None, frequency_axis=None):
                            self.node_voltages = node_voltages
                            self.branch_currents = branch_currents
                            # Create a dictionary-like object for nodes that can be iterated and indexed
                            self.nodes = node_voltages  # This is already a dict
                            self.branches = list(branch_currents.keys())  # Add branches property
                            self.time = time_axis
                            self.frequency = frequency_axis
                        
                        def __getitem__(self, key):
                            if key in self.node_voltages:
                                return self.node_voltages[key]
                            return 0.0
                        
                        def __getattr__(self, name):
                            if name in self.branch_currents:
                                return self.branch_currents[name]
                            return 0.0
                    
                    return MockAnalysis(result['node_voltages'], result['branch_currents'], 
                                      result.get('time_axis'), result.get('frequency_axis'))
                else:
                    logger.error(f"Fallback simulation failed: {result['error'] if result else 'No result'}")
                    # If fallback fails, try PySpice as backup
                    logger.info("Fallback failed, trying PySpice as backup...")
            except Exception as e:
                logger.error(f"Fallback simulation crashed: {e}")
                logger.info("Fallback crashed, trying PySpice as backup...")
        
        # PySpice method (as backup or if fallback not applicable)
        try:
            # Create simulator with improved options
            simulator = circuit.simulator(
                temperature=25, 
                nominal_temperature=25,
                # Add simulation options to help with convergence
                simulator_options={
                    'gmin': 1e-12,
                    'abstol': 1e-12,
                    'reltol': 1e-3,
                    'vntol': 1e-6,
                    'chgtol': 1e-14,
                    'trtol': 7,
                    'pivtol': 1e-13,
                    'pivrel': 1e-3,
                    'numdgt': 6,
                    'maxord': 2
                }
            )
            
            analysis = None
            
            if analysis_type == AnalysisType.OPERATING_POINT:
                analysis = simulator.operating_point(**analysis_params)
                
            elif analysis_type == AnalysisType.TRANSIENT:
                step_time = analysis_params.get('step_time')
                end_time = analysis_params.get('end_time')
                if not step_time or not end_time:
                    raise ValueError("Transient analysis requires 'step_time' and 'end_time' parameters.")
                
                parsed_step_time = self._parse_pyspice_unit_string(step_time)
                parsed_end_time = self._parse_pyspice_unit_string(end_time)
                
                if parsed_step_time is None or parsed_end_time is None:
                    raise ValueError("Invalid time parameters for transient analysis")
                
                analysis = simulator.transient(step_time=parsed_step_time, end_time=parsed_end_time)
            
            elif analysis_type == AnalysisType.AC:
                start_frequency = analysis_params.get('start_frequency')
                stop_frequency = analysis_params.get('stop_frequency')
                number_of_points = analysis_params.get('number_of_points')
                sweep_type = analysis_params.get('sweep_type', 'lin')
                
                if not all([start_frequency, stop_frequency, number_of_points]):
                    raise ValueError("AC analysis requires 'start_frequency', 'stop_frequency', and 'number_of_points'.")
                
                analysis = simulator.ac(
                    start_frequency=start_frequency,
                    stop_frequency=stop_frequency,
                    number_of_points=number_of_points,
                    variation=sweep_type
                )
            
            elif analysis_type == AnalysisType.DC:
                source_name = analysis_params.get('source_name')
                start_value = analysis_params.get('start_value')
                end_value = analysis_params.get('end_value')
                step_value = analysis_params.get('step_value')
                
                if not all([source_name, start_value, end_value, step_value]):
                    raise ValueError("DC analysis requires 'source_name', 'start_value', 'end_value', and 'step_value'.")
                
                analysis = simulator.dc(source_name, start_value, end_value, step_value)
            
            else:
                raise ValueError(f"Unsupported analysis type: {analysis_type}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Simulation failed: {e}")
            # Try with more relaxed convergence options
            if "singular matrix" in str(e).lower():
                logger.info("Attempting simulation with relaxed convergence options...")
                try:
                    simulator = circuit.simulator(
                        temperature=25,
                        nominal_temperature=25,
                        simulator_options={
                            'gmin': 1e-9,  # Larger gmin for better convergence
                            'abstol': 1e-9,
                            'reltol': 1e-2,
                            'vntol': 1e-3,
                            'chgtol': 1e-11,
                            'trtol': 10,
                            'pivtol': 1e-10,
                            'pivrel': 1e-2,
                            'numdgt': 4,
                            'maxord': 1
                        }
                    )
                    
                    if analysis_type == AnalysisType.OPERATING_POINT:
                        analysis = simulator.operating_point(**analysis_params)
                        return analysis
                except Exception as e2:
                    logger.error(f"Retry with relaxed options also failed: {e2}")
                    raise e
            
            # Try fallback to custom ngspice wrapper for operating point analysis
            if analysis_type == AnalysisType.OPERATING_POINT and not self.use_fallback:
                logger.info("Attempting simulation with fallback ngspice wrapper...")
                try:
                    # Use original netlist string if available, otherwise convert circuit
                    netlist_str = original_netlist if original_netlist else str(circuit)
                    
                    # Use the wrapper
                    result = self.ngspice_wrapper.simulate_op(netlist_str, circuit.title)
                    
                    if result['success']:
                        # Create a mock analysis object with the results
                        class MockAnalysis:
                            def __init__(self, node_voltages, branch_currents, time_axis=None, frequency_axis=None):
                                self.node_voltages = node_voltages
                                self.branch_currents = branch_currents
                                # Create a dictionary-like object for nodes that can be iterated and indexed
                                self.nodes = node_voltages  # This is already a dict
                                self.branches = list(branch_currents.keys())  # Add branches property
                                self.time = time_axis
                                self.frequency = frequency_axis
                            
                            def __getitem__(self, key):
                                if key in self.node_voltages:
                                    return self.node_voltages[key]
                                return 0.0
                            
                            def __getattr__(self, name):
                                if name in self.branch_currents:
                                    return self.branch_currents[name]
                                return 0.0
                        
                        self.use_fallback = True  # Use fallback for subsequent calls
                        logger.info("Fallback simulation successful!")
                        return MockAnalysis(result['node_voltages'], result['branch_currents'],
                                          result.get('time_axis'), result.get('frequency_axis'))
                    else:
                        logger.error(f"Fallback simulation failed: {result['error']}")
                except Exception as e3:
                    logger.error(f"Fallback simulation crashed: {e3}")
            
            raise e
    
    def simulate_circuit(self, request: SimulationRequest) -> SimulationResults:
        """
        Main function to process a simulation request with improved error handling.
        """
        try:
            # 1. Create Circuit from Netlist String
            circuit = self._create_circuit_from_netlist(request.netlist_string, request.circuit_name)
            
            # Debug output
            print(f"--- Circuit Created Successfully for '{request.circuit_name}' ---")
            print(f"Elements: {len(circuit.elements)}")
            print(f"Nodes: {[str(node) for node in circuit.node_names]}")
            
            # 2. Run Simulation
            analysis = self._run_simulation(circuit, request.analysis_type, request.analysis_parameters, request.netlist_string)
            
            # 3. Extract Results
            node_voltages: List[NodeVoltageResult] = []
            branch_currents: List[BranchCurrentResult] = []
            time_axis: Optional[List[float]] = None
            frequency_axis: Optional[List[float]] = None
            
            # Debug: Print available results
            print("Available node voltages:")
            for node_name in analysis.nodes:
                print(f"  {node_name}")
            
            print("Available branch currents:")
            for branch_name in analysis.branches:
                print(f"  {branch_name}")
            
            # Extract requested results
            for req_result in request.requested_results:
                result_type = req_result['type']
                result_name = req_result['name']
                
                if result_type == 'node_voltage':
                    if result_name in analysis.nodes:
                        voltage_waveform = analysis.nodes[result_name]
                        
                        if request.analysis_type == AnalysisType.OPERATING_POINT:
                            # Handle scalar value
                            if hasattr(voltage_waveform, '__getitem__') and len(voltage_waveform) > 0:
                                voltage_value = float(voltage_waveform[0])
                            else:
                                voltage_value = float(voltage_waveform)
                            
                            node_voltages.append(NodeVoltageResult(
                                node=result_name,
                                voltage=voltage_value,
                                unit=str(getattr(voltage_waveform, 'unit', 'V'))
                            ))
                        else:
                            # Handle array values - check if it's actually iterable
                            if hasattr(voltage_waveform, '__iter__') and not isinstance(voltage_waveform, (str, bytes)):
                                node_voltages.append(NodeVoltageResult(
                                    node=result_name,
                                    voltage=[float(v) for v in voltage_waveform],
                                    unit=str(getattr(voltage_waveform, 'unit', 'V'))
                                ))
                            else:
                                # Single value, treat as scalar
                                node_voltages.append(NodeVoltageResult(
                                    node=result_name,
                                    voltage=float(voltage_waveform),
                                    unit=str(getattr(voltage_waveform, 'unit', 'V'))
                                ))
                    else:
                        logger.warning(f"Requested node voltage for '{result_name}' not found.")
                
                elif result_type == 'branch_current':
                    # Try to find the branch current with different naming conventions
                    current_value = None
                    found_branch = None
                    
                    # Try exact match first
                    if hasattr(analysis, 'branch_currents') and result_name in analysis.branch_currents:
                        current_value = analysis.branch_currents[result_name]
                        found_branch = result_name
                    # Try with #branch suffix (ngspice format)
                    elif hasattr(analysis, 'branch_currents') and f"{result_name.lower()}#branch" in analysis.branch_currents:
                        found_branch = f"{result_name.lower()}#branch"
                        current_value = analysis.branch_currents[found_branch]
                    # Try accessing via getattr (for PySpice compatibility)
                    elif hasattr(analysis, result_name):
                        current_value = getattr(analysis, result_name)
                        found_branch = result_name
                    # Try with lowercase
                    elif hasattr(analysis, result_name.lower()):
                        current_value = getattr(analysis, result_name.lower())
                        found_branch = result_name.lower()
                    
                    if current_value is not None:
                        if request.analysis_type == AnalysisType.OPERATING_POINT:
                            # Handle scalar value
                            if hasattr(current_value, '__getitem__') and len(current_value) > 0:
                                current_val = float(current_value[0])
                            else:
                                current_val = float(current_value)
                            
                            branch_currents.append(BranchCurrentResult(
                                branch=result_name,
                                current=current_val,
                                unit='A'
                            ))
                        else:
                            # Handle array values - check if it's actually iterable
                            if hasattr(current_value, '__iter__') and not isinstance(current_value, (str, bytes)):
                                branch_currents.append(BranchCurrentResult(
                                    branch=result_name,
                                    current=[float(c) for c in current_value],
                                    unit='A'
                                ))
                            else:
                                # Single value, treat as scalar
                                branch_currents.append(BranchCurrentResult(
                                    branch=result_name,
                                    current=float(current_value),
                                    unit='A'
                                ))
                    else:
                        logger.warning(f"Requested branch current for '{result_name}' not found.")
            
            # Handle time/frequency axis
            if request.analysis_type == AnalysisType.TRANSIENT:
                if hasattr(analysis, 'time'):
                    time_axis = [float(t) for t in analysis.time]
                    
            elif request.analysis_type == AnalysisType.AC:
                if hasattr(analysis, 'frequency'):
                    frequency_axis = [float(f) for f in analysis.frequency]
            
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
                simulation_type=request.analysis_type,
            )
    
    def _parse_pyspice_unit_string(self, value: str) -> Optional[float]:
        """
        Converts a string like '1u', '5ms', '0.01', or a number to a float value for PySpice.
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
            
            match = re.match(r'^([\d\.eE+-]+)\s*([a-zA-Z]+)?$', value)
            if match:
                num_str = match.group(1)
                unit = match.group(2)
                
                num = float(num_str)
                
                if unit:
                    unit = unit.lower()
                    for k in sorted(unit_map, key=len, reverse=True):
                        if unit.startswith(k):
                            return num * unit_map[k]
                
                return num
            
            # Fallback: try direct conversion
            return float(value)
            
        except Exception as e:
            logger.warning(f"Failed to parse unit string '{value}': {e}")
            return None