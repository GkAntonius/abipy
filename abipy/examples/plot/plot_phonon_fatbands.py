#!/usr/bin/env python
#
# This example shows how to plot the phonon fatbands of AlAs.
# See tutorial/lesson_rf2.html
from abipy.abilab import PhononBands
import abipy.data as abidata

# Path to the PHBST file produced by anaddb.
filename = abidata.ref_file("trf2_5.out_PHBST.nc")

# Create the object from file.
phbands = PhononBands.from_file(filename)

# Mapping reduced coordinates -> labels
qlabels = {
    (0,0,0): "$\Gamma$",
    (0.375, 0.375, 0.75): "K",
    (0.5, 0.5, 1.0): "X",
    (0.5, 0.5, 0.5): "L",
    (0.5, 0.0, 0.5): "X",
    (0.5, 0.25, 0.75): "W",
}

# Plot the phonon band structure.
phbands.plot_fatbands(title="AlAs phonon fatbands without LO-TO splitting", qlabels=qlabels)
