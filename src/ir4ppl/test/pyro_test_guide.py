# %%
import sys
sys.path.append("src/ir4ppl")
from pyro.pyro_cfg import *
from utils.bcolors import bcolors
from analysis.absolute_continuity_checker import check_ac, check_ac_guide
import os

folder = "evaluation/pyro"

for root, dir, files in os.walk(folder):
    for file in files:
        if file.endswith(".py"):
            filename = root + "/" + file
            print(bcolors.HEADER, filename, bcolors.ENDC, sep="")
        
            ir = get_IR_for_pyro(filename)

            violation = check_ac_guide(ir)
            if violation:
                print(violation.get_diagnostic_ranges(), violation)
