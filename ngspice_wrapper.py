#!/usr/bin/env python3
"""
Custom ngspice simulation wrapper that bypasses PySpice's problematic parsing
"""
import subprocess
import tempfile
import os
import re
from typing import Dict, Any, List, Tuple
from pathlib import Path


class NgspiceSimulationWrapper:
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
        """Parse ngspice text output"""
        results = {
            'node_voltages': {},
            'branch_currents': {},
            'success': True,
            'error': None
        }
        
        lines = output.split('\n')
        
        if analysis_type == 'op':
            return self._parse_op_output(lines)
        elif analysis_type == 'ac':
            return self._parse_ac_output(lines)
        elif analysis_type == 'tran':
            return self._parse_tran_output(lines)
        else:
            results['success'] = False
            results['error'] = f"Unknown analysis type: {analysis_type}"
            return results
    
    def _parse_op_output(self, lines: List[str]) -> Dict[str, Any]:
        """Parse operating point output"""
        results = {
            'node_voltages': {},
            'branch_currents': {},
            'success': True,
            'error': None
        }
        
        # Find voltage section
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
        
        return results
    
    def _parse_ac_output(self, lines: List[str]) -> Dict[str, Any]:
        """Parse AC analysis output"""
        results = {
            'frequencies': [],
            'nodes': {},
            'success': True,
            'error': None
        }
        
        # Look for AC output data
        data_section = False
        header_parsed = False
        node_names = []
        
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
            
            # Look for frequency data
            if re.match(r'^\s*\d+\.\d+[eE]?[+-]?\d*\s+', line):
                # This looks like frequency data
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        freq = float(parts[0])
                        results['frequencies'].append(freq)
                        
                        # Parse node values (magnitude and phase pairs)
                        node_idx = 0
                        for i in range(1, len(parts), 2):
                            if i + 1 < len(parts):
                                mag = float(parts[i])
                                phase = float(parts[i + 1])
                                
                                if node_idx < len(node_names):
                                    node_name = node_names[node_idx]
                                    if node_name not in results['nodes']:
                                        results['nodes'][node_name] = {'magnitude': [], 'phase': []}
                                    results['nodes'][node_name]['magnitude'].append(mag)
                                    results['nodes'][node_name]['phase'].append(phase)
                                    node_idx += 1
                    except ValueError:
                        continue
            
            # Look for header with node names
            elif 'frequency' in line.lower() and not header_parsed:
                # Extract node names from header
                parts = line.split()
                for part in parts[1:]:  # Skip 'frequency'
                    if part.lower() not in ['magnitude', 'phase', 'real', 'imag']:
                        node_names.append(part)
                header_parsed = True
        
        return results
    
    def _parse_tran_output(self, lines: List[str]) -> Dict[str, Any]:
        """Parse transient analysis output"""
        results = {
            'time': [],
            'nodes': {},
            'success': True,
            'error': None
        }
        
        # Look for transient output data
        header_parsed = False
        node_names = []
        
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
            
            # Look for time data
            if re.match(r'^\s*\d+\.\d+[eE]?[+-]?\d*\s+', line):
                # This looks like time data
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        time = float(parts[0])
                        results['time'].append(time)
                        
                        # Parse node values
                        for i, node_name in enumerate(node_names):
                            if i + 1 < len(parts):
                                value = float(parts[i + 1])
                                if node_name not in results['nodes']:
                                    results['nodes'][node_name] = []
                                results['nodes'][node_name].append(value)
                    except ValueError:
                        continue
            
            # Look for header with node names
            elif 'time' in line.lower() and not header_parsed:
                # Extract node names from header
                parts = line.split()
                node_names = parts[1:]  # Skip 'time'
                header_parsed = True
        
        return results
    
    def simulate_op(self, netlist: str, circuit_name: str = "Circuit") -> Dict[str, Any]:
        """Run operating point simulation"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False) as f:
                # Ensure proper netlist format
                if not netlist.strip().startswith('.title'):
                    netlist = f".title {circuit_name}\n{netlist}"
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
    
    def simulate_ac(self, netlist: str, start_freq: float, stop_freq: float, 
                   points_per_decade: int = 10, circuit_name: str = "Circuit") -> Dict[str, Any]:
        """Run AC analysis"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False) as f:
                # Ensure proper netlist format
                if not netlist.strip().startswith('.title'):
                    netlist = f".title {circuit_name}\n{netlist}"
                
                # Add AC analysis command
                ac_cmd = f".ac dec {points_per_decade} {start_freq} {stop_freq}"
                if '.ac' not in netlist:
                    netlist = f"{netlist}\n{ac_cmd}"
                
                # Add print command to get output
                if '.print' not in netlist:
                    # Find all nodes in the netlist
                    nodes = self._extract_nodes_from_netlist(netlist)
                    if nodes:
                        print_cmd = f".print ac {' '.join(nodes)}"
                        netlist = f"{netlist}\n{print_cmd}"
                
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
                return self._parse_output(result.stdout, 'ac')
            else:
                return {
                    'success': False,
                    'error': f"ngspice failed: {result.stderr}",
                    'frequencies': [],
                    'nodes': {}
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'frequencies': [],
                'nodes': {}
            }
    
    def simulate_tran(self, netlist: str, step_time: float, stop_time: float, 
                     circuit_name: str = "Circuit") -> Dict[str, Any]:
        """Run transient analysis"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False) as f:
                # Ensure proper netlist format
                if not netlist.strip().startswith('.title'):
                    netlist = f".title {circuit_name}\n{netlist}"
                
                # Add transient analysis command
                tran_cmd = f".tran {step_time} {stop_time}"
                if '.tran' not in netlist:
                    netlist = f"{netlist}\n{tran_cmd}"
                
                # Add print command to get output
                if '.print' not in netlist:
                    # Find all nodes in the netlist
                    nodes = self._extract_nodes_from_netlist(netlist)
                    if nodes:
                        print_cmd = f".print tran {' '.join(nodes)}"
                        netlist = f"{netlist}\n{print_cmd}"
                
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
                return self._parse_output(result.stdout, 'tran')
            else:
                return {
                    'success': False,
                    'error': f"ngspice failed: {result.stderr}",
                    'time': [],
                    'nodes': {}
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'time': [],
                'nodes': {}
            }
    
    def _extract_nodes_from_netlist(self, netlist: str) -> List[str]:
        """Extract node names from netlist"""
        nodes = set()
        lines = netlist.split('\n')
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('.') and not line.startswith('*'):
                # Component lines
                parts = line.split()
                if len(parts) >= 3:
                    # For components like R1 n1 n2 1k, nodes are at positions 1 and 2
                    node1 = parts[1]
                    node2 = parts[2]
                    if node1 != '0':  # Skip ground
                        nodes.add(node1)
                    if node2 != '0':  # Skip ground
                        nodes.add(node2)
        
        return list(nodes)


# Test the wrapper
if __name__ == "__main__":
    wrapper = NgspiceSimulationWrapper()
    
    # Test with voltage divider
    netlist = """
V1 in 0 DC 5
R1 in out 1000
R2 out 0 2000
.op
"""
    
    result = wrapper.simulate_op(netlist, "Test Circuit")
    print("Simulation result:", result)
    
    if result['success']:
        print("✅ Simulation successful!")
        print(f"Node voltages: {result['node_voltages']}")
        print(f"Branch currents: {result['branch_currents']}")
    else:
        print(f"❌ Simulation failed: {result['error']}")
