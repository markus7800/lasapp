# %%
import sys
sys.path.append(".")
import subprocess
import sexpdata
from stan.syntaxnode import *
from stan.stan_cfg import *
from utils.bcolors import bcolors
#%%

import os
from stan.unparser import unparse

stanc = "/Users/markus/Documents/stanc3/_build/default/src/stanc/stanc.exe"
folder = "/Users/markus/Documents/stan-example-models/"

can_be_analyzed_count = 0
for root, dir, files in os.walk(folder):
    for file in files:
        if file.endswith(".stan"):
            filename = root + "/" + file
            if filename.startswith("/Users/markus/Documents/stan-example-models/regression_tests/"):
                continue
            
            print(bcolors.HEADER, filename, bcolors.ENDC, sep="")
            res = subprocess.run([stanc, "--debug-ast", filename], capture_output=True)
            stan_ast = res.stdout.decode("utf-8")
            sexpr = sexpdata.loads(stan_ast, true=None)
            sexpr = sym_to_str(sexpr)
            unparse(sexpr)
