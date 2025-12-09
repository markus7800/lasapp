import sys
sys.path.insert(0, 'lasapp/src/ir4ppl')

import argparse
import json
from stan.stan_cfg import *
from analysis.model_graph import get_graph, model_graph_svg
import os
import uuid
import pathlib

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Graph a Stan probabilistic program.")
    parser.add_argument("stanc")
    args = parser.parse_args()
    
    file_content = sys.stdin.read()

    
    pathlib.Path(".pipe", "tmp").mkdir(exist_ok=True)
    uid = str(uuid.uuid4())[:8]
    filename = pathlib.Path(".pipe", "tmp", f"{uid}.stan")
    hppname = pathlib.Path(".pipe", "tmp", f"{uid}.hpp")
    with open(filename, "w") as f:
        f.write(file_content)
    
    try:
        # currently only stan
        ir = get_IR_for_stan(filename, stanc=args.stanc)
    finally:
        if filename.exists():
            os.remove(filename)
        if hppname.exists():
            os.remove(hppname)
        
    nodes, edges = get_graph(ir)
    
    svg = model_graph_svg(nodes, edges)
    
    print(json.dumps({
        "svg": svg,
        "rv_positions": {node.id: (node.get_source_location().first_byte, node.get_source_location().last_byte) for node in nodes}
    }))

        