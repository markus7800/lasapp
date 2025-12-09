
from collections import deque
from ir4ppl.ir import * 
from typing import Deque, Tuple, List
from dataclasses import dataclass


@dataclass
class RandomControlDependentWarning:
    node: SampleNode | FactorNode
    random_control_deps: list[SampleNode]

    def __str__(self) -> str:
        s = f"RandomControlDependentWarning: Random variable \"{self.node.get_source_location().source_text}\" is control dependent on following variables:\n"
        for rv_dep in self.random_control_deps:
            s += f"        {rv_dep.get_source_location().source_text}\n"
        s += "    Random control dependencies may cause discontinuities in the posterior distribution, which are challenging for HMC/NUTS."
        return s
    
    def get_diagnostic_ranges(self) -> list[tuple[int,int]]:
        location = self.node.get_source_location()
        return [(location.first_byte, location.last_byte)]

def get_random_control_dependencies(program_ir: PPL_IR, r: SampleNode | FactorNode) -> List[SampleNode]:
    random_control_deps: List[SampleNode] = list()
    marked: Set[Tuple[CFGNode,bool]] = set()
    queue: Deque[Tuple[CFGNode,Expression,bool]] = deque()
    if isinstance(r, SampleNode):
        queue.append((r, r.get_address_expr(), False))
        queue.append((r, r.get_distribution_expr(), False))
    else:
        queue.append((r, r.get_factor_expr(), False))

    while len(queue) > 0:
        node, expr, is_control = queue.popleft()

        # get all data dependencies
        for dep in program_ir.get_data_deps_for_expr(node, expr):
            # check if we have already processed node
            if (dep, is_control) not in marked:
                if isinstance(dep, SampleNode):
                    # if node is random variable, we do not continue recursion and add edge to graph
                    if is_control:
                        random_control_deps.append(dep)
                    queue.append((dep, dep.get_address_expr(),is_control))
                else:
                    queue.append((dep, dep.get_value_expr(),is_control))
                    if dep.get_target().is_indexed_target():
                        queue.append((dep, dep.get_target().get_index_expr(), is_control))

                marked.add((dep, is_control))
        
        # get all control dependencies, this are loop / if nodes
        for dep in program_ir.get_control_deps_for_node(node, expr):
            # get data dependencies of condition / loop variable (control subnode) of control node
            if (dep,True) not in marked:
                queue.append((dep, dep.get_test_expr(),True))
                marked.add((dep,True))
    return random_control_deps


def check_for_random_control_flow(program_ir: PPL_IR):
    warnings: list[RandomControlDependentWarning] = []
    random_stmts = program_ir.get_sample_nodes() + program_ir.get_factor_nodes()
    for r in random_stmts:
        random_control_deps = get_random_control_dependencies(program_ir, r)
        if len(random_control_deps) > 0:
            warnings.append(RandomControlDependentWarning(r, random_control_deps))
    return warnings
