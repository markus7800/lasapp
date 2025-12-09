
from collections import deque
from ir4ppl.ir import * 
from typing import Deque, Tuple, List

def get_graph(program_ir: PPL_IR):

    random_stmts = program_ir.get_sample_nodes() + program_ir.get_factor_nodes()

    edges = []

    for r in random_stmts:
        marked: Set[CFGNode] = set()
        # we recursively get all data and control dependencies of random variable node
        queue: Deque[Tuple[CFGNode,Expression]] = deque()
        if isinstance(r, SampleNode):
            queue.append((r, r.get_address_expr()))
            queue.append((r, r.get_distribution_expr()))
        else:
            queue.append((r, r.get_factor_expr()))

        while len(queue) > 0:
            # get next node, FIFO
            node, expr = queue.popleft()

            # get all data dependencies
            for dep in program_ir.get_data_deps_for_expr(node, expr):
                # check if we have already processed node
                if dep not in marked:
                    if isinstance(dep, SampleNode):
                        # if node is random variable, we do not continue recursion and add edge to graph
                        edges.append((dep, r))
                        queue.append((dep, dep.get_address_expr()))

                    else:
                        queue.append((dep, dep.get_value_expr()))
                        if dep.get_target().is_indexed_target():
                            queue.append((dep, dep.get_target().get_index_expr()))

                    marked.add(dep)
            
            # get all control dependencies, this are loop / if nodes
            for dep in program_ir.get_control_deps_for_node(node, expr):
                # get data dependencies of condition / loop variable (control subnode) of control node
                if dep not in marked:
                    queue.append((dep, dep.get_test_expr()))
                    marked.add(dep)
                    

    return random_stmts, edges
