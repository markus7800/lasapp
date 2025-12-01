import sys
sys.path.insert(0, 'lasapp/src/static')

import argparse
import lasapp
import analysis.model_graph as model_graph
import json


if __name__ == '__main__':
    
    file_content = sys.stdin.read()
    
    program = lasapp.ProbabilisticProgram("filename.py", file_content=file_content, n_unroll_loops=0)
    graph = model_graph.get_model_graph(program)
    
    svg = model_graph.plot_model_graph(graph, toFile=False)
    
    print(json.dumps({
        "svg": svg,
        "rv_positions": {node_id: (rv.node.first_byte, rv.node.last_byte) for node_id, rv in graph.random_variables.items()}
    }))
