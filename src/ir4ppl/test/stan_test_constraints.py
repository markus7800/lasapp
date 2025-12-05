# %%
import sys
sys.path.append("src/ir4ppl")
from stan.syntaxnode import *
from stan.stan_cfg import *
from utils.bcolors import bcolors
from analysis.constraint_verification import verify_constraints
import os

stanc = "/Users/markus/Documents/stanc3/_build/default/src/stanc/stanc.exe"
folder = "/Users/markus/Documents/stan-example-models/"

can_be_analyzed_count = 0
count = 0
for root, dir, files in os.walk(folder):
    for file in files:
        if file.endswith(".stan"):
            filename = root + "/" + file
            if filename.startswith("/Users/markus/Documents/stan-example-models/regression_tests/"):
                continue
            count += 1
            
            try:
                ir = get_IR_for_stan(filename, stanc=stanc)
                violations, can_be_analyzed = verify_constraints(ir)
            except:
                can_be_analyzed = False
                violations = []

            if can_be_analyzed:
                can_be_analyzed_count += 1
                print(bcolors.HEADER, filename, bcolors.ENDC, bcolors.OKGREEN, " OK", bcolors.ENDC, sep="")
                for violation in violations:
                    print(violation)
            else:                
                print(bcolors.HEADER, filename, bcolors.ENDC, bcolors.FAIL, " NO", bcolors.ENDC, sep="")
                pass
            print()
            
print("COUNT:", can_be_analyzed_count, "/", count)