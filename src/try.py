import PySpice.Logging.Logging as Logging
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import * # Import all units for convenience
import numpy as np # For numerical operations, especially for plotting
import matplotlib.pyplot as plt # For plotting results

# 1. Configure PySpice to use NGSPICE
# This line is crucial for PySpice to find and use NGSPICE as the simulator.
# Ensure NGSPICE is installed and in your system's PATH.
# PySpice.Spice.Simulation.CircuitSimulator.DEFAULT_SIMULATOR = 'ngspice-subprocess'

# Setup logging for PySpice (optional, but useful for debugging)
logger = Logging.setup_logging()

# 2. Define the Circuit
circuit = Circuit('RC Low-Pass Filter with Pulse Input')

# Define components:
# Voltage Source: Pulse (V1 node1 node2 PULSE(V1 V2 TD TR TF PW PER))
# V1 = initial voltage, V2 = pulsed voltage, TD = delay time,
# TR = rise time, TF = fall time, PW = pulse width, PER = period
circuit.V('input', 1, circuit.gnd, 'PULSE(0 5 0 100n 100n 10u 20u)') # 0V to 5V pulse, 10us width, 20us period
circuit.R(1, 1, 2, 1@u_kOhm) # 1 kOhm resistor between node 1 and node 2
circuit.C(1, 2, circuit.gnd, 1@u_uF) # 1 uF capacitor between node 2 and ground

# 3. Set up and Run Transient Analysis
# simulator.tran(step_time, end_time)
# step_time: The time increment for the simulation (how often to save data)
# end_time: The total duration of the simulation
# Ensure these values are appropriate for your circuit's time constants (RC = 1k * 1u = 1ms)
# We'll simulate for a few periods of the pulse.
step_time = 10@u_us # 10 microseconds step
end_time = 50@u_ms # 50 milliseconds total simulation time

# Create the simulator object
simulator = circuit.simulator(temperature=25, nominal_temperature=25)

print(f"Running transient analysis for '{circuit.title}' from 0 to {end_time} with step {step_time}...")

try:
    # Run the transient simulation
    analysis = simulator.transient(step_time=step_time, end_time=end_time)

    print("Simulation completed successfully!")

    # 4. Access and Plot Results
    # The analysis object contains the time axis and node voltages/branch currents
    # as NumPy arrays.
    time_points = np.array(analysis.time) # Time axis
    input_voltage = np.array(analysis.nodes['1']) # Voltage at node 1 (input)
    output_voltage = np.array(analysis.nodes['2']) # Voltage at node 2 (output, across capacitor)

    # Plotting the results
    plt.figure(figsize=(10, 6))
    plt.plot(time_points * 1000, input_voltage, label='V(input) [V]') # Convert time to ms for readability
    plt.plot(time_points * 1000, output_voltage, label='V(output) [V]')
    plt.title('RC Low-Pass Filter Transient Analysis')
    plt.xlabel('Time [ms]')
    plt.ylabel('Voltage [V]')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()

    # You can also print specific values
    print(f"\nVoltage at output node (node 2) at {10@u_ms}: {output_voltage[np.where(time_points >= 10@u_ms)[0][0]]} V")
    print(f"Voltage at output node (node 2) at {20@u_ms}: {output_voltage[np.where(time_points >= 20@u_ms)[0][0]]} V")

except Exception as e:
    print(f"An error occurred during simulation: {e}")
    # Print full traceback for detailed debugging
    import traceback
    traceback.print_exc()

