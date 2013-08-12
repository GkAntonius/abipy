#!/usr/bin/env python
#
# This example shows how to plot the so-called fatbands for electrons
from abipy import abiopen
import abipy.data as data

# Open the WKF file.
gsr_file = abiopen(data.ref_file("si_nscf_GSR.nc"))

# Extract the band structure. 
ebands = gsr_file.ebands

# Define the mapping reduced_coordinates -> name of the k-point.
klabels = {
    (0.5,  0.0,  0.0) : "L",
    (0.0,  0.0,  0.0) : "$\Gamma$",
    (0.0,  0.5,  0.5) : "X",
}

# Set the width 
import numpy as np
import collections
ones = np.ones(ebands.shape)
widths = collections.OrderedDict([
    ("Si-3s", ones),
    ("Si-3p", 2*ones),
])

for key, value in widths.items():
    ebands.set_width(key, value)

# Plot the fatbands
ebands.plot_fatbands()
