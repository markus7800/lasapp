# %%
import sys
sys.path.append("src/ir4ppl")
from stan.syntaxnode import *
from stan.stan_cfg import *
from utils.bcolors import bcolors
from analysis.random_control_flow import check_for_random_control_flow
import os

stanc = "/Users/markus/Documents/stanc3/_build/default/src/stanc/stanc.exe"
folder = "/Users/markus/Documents/stan-example-models/"

for root, dir, files in os.walk(folder):
    for file in files:
        if file.endswith(".stan"):
            filename = root + "/" + file
            if filename.startswith("/Users/markus/Documents/stan-example-models/regression_tests/"):
                continue
            print(bcolors.HEADER, filename, bcolors.ENDC, sep="")

            ir = get_IR_for_stan(filename, stanc=stanc)
            warnings = check_for_random_control_flow(ir)
            for warning in warnings:
                print(warning.get_diagnostic_ranges(),  warning)
            print()
            