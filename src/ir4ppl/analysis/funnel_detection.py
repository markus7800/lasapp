
from collections import deque
from ir4ppl.ir import * 
from typing import Deque, Tuple, List
from dataclasses import dataclass


@dataclass
class FunnelWarning:
    funnel_node: SampleNode | FactorNode
    scale_node: SampleNode

    def __str__(self):
        return f"Funnel detected: Scale parameter of '{self.funnel_node.get_source_location().source_text}' depends on variable '{self.scale_node.get_source_location().source_text}', which may lead to poor inference performance."

    def get_diagnostic_ranges(self) -> list[tuple[int,int]]:
        loc1 = self.funnel_node.get_source_location()
        loc2 = self.scale_node.get_source_location()
        return [(loc1.first_byte, loc1.last_byte), (loc2.first_byte, loc2.last_byte)]
    

def get_funnel_relationships(program_ir: PPL_IR) -> List[FunnelWarning]:
    
    warnings: list[FunnelWarning] = []
    for node in program_ir.get_sample_nodes() + program_ir.get_factor_nodes():
        try:
            distribution = node.get_distribution()
            for name, expr in distribution.args.items():
                if name == "scale":
                    marked: Set[CFGNode] = set()
                    queue: Deque[Tuple[CFGNode,Expression]] = deque([(node,expr)])
                    for dep in program_ir.get_data_deps_for_expr(node, expr):
                        if dep not in marked:
                            if isinstance(dep, SampleNode):
                                warnings.append(FunnelWarning(node,dep))
                        else:
                            queue.append((dep, dep.get_value_expr()))
                            if dep.get_target().is_indexed_target():
                                queue.append((dep, dep.get_target().get_index_expr()))
                        marked.add(dep)
        except:
            pass
        
    return warnings
       
