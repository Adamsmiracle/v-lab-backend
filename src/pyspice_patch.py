"""
PySpice ngspice compatibility patch.

This module patches PySpice to work with ngspice-38 by handling the 
"Note" vs "Circuit" output format difference.
"""

import PySpice.Spice.RawFile
import PySpice.Spice.NgSpice.RawFile


def patched_read_header_field_line(self, header_line_iterator, expected_label):
    """
    Patched version that handles both "Circuit" and "Note" labels for ngspice-38 compatibility.
    Also handles both bytes and string input and skips empty lines.
    """
    try:
        while True:
            line = next(header_line_iterator)
            
            # Handle both bytes and string input
            if isinstance(line, bytes):
                line = line.decode('utf-8')
            
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            items = line.split(':', 1)
            if len(items) == 2:
                label, value = items
                label = label.strip()
                value = value.strip()
                
                # Handle both "Circuit" and "Note" labels for ngspice-38 compatibility
                if expected_label == 'Circuit' and label == 'Note':
                    # ngspice-38 outputs "Note" instead of "Circuit"
                    return value
                elif label == expected_label:
                    return value
                else:
                    raise NameError(f"Expected label {expected_label} instead of {label}")
            else:
                # Debug: print the problematic line
                print(f"DEBUG: Invalid header line format: '{line}' (expected '{expected_label}')")
                continue  # Skip malformed lines instead of failing
                
    except StopIteration:
        raise NameError("Expected label %s but reached end of header" % expected_label)


# Apply the patch to the NgSpice RawFile class
def apply_patch():
    """Apply the compatibility patch to PySpice RawFile classes"""
    # Patch the main RawFile class
    PySpice.Spice.RawFile.RawFileAbc._read_header_field_line = patched_read_header_field_line
    
    # Also patch the NgSpice-specific RawFile class if it exists
    if hasattr(PySpice.Spice.NgSpice.RawFile, 'RawFile'):
        PySpice.Spice.NgSpice.RawFile.RawFile._read_header_field_line = patched_read_header_field_line

# Apply the patch immediately when module is imported
apply_patch()
