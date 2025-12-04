from ir4ppl.cfg import *
from copy import copy

def _get_RDs(cfgnode: CFGNode, variable: Variable, path: List[CFGNode], rds: Set[AbstractAssignNode], memo: Dict[BranchNode, Set[AbstractAssignNode]]):
    for parent in cfgnode.parents:
        if isinstance(parent, (AssignNode, SampleNode)):
            target = parent.get_target()
            if target.is_equal(variable):
                rds.add(parent)
                if not target.is_indexed_target():
                    # x = ...
                    continue
                else:
                    # x[i] = ...
                    if variable.is_indexed_variable() and  target.index_is_equal(variable):
                        # x[2] = x[2]
                        continue
        elif isinstance(parent, (FuncArgNode, LoopIterNode)):
            target = parent.get_target()
            # no indexed targets
            if target.is_equal(variable):
                rds.add(parent)
                continue
        
        is_cycle = any(p == parent for p in path)
        if not is_cycle:
            new_path = copy(path) if len(cfgnode.parents) > 1 else path
            new_path.append(parent)
            # we memoise at branch nodes to avoid path explosion
            if isinstance(parent, BranchNode):
                if parent in memo:
                    branch_rds = memo[parent]
                else:
                    branch_rds = _get_RDs(parent, variable, new_path, set(), memo)
                    memo[parent] = branch_rds
                rds.update(branch_rds)
            else:
                _get_RDs(parent, variable, new_path, rds, memo)
    return rds

def get_RDs(cfgnode: CFGNode, variable: Variable) -> Set[AbstractAssignNode]:
    return _get_RDs(cfgnode, variable, [], set(), dict())


def get_BPs(cfg: CFG, cfgnode: CFGNode) -> Set[BranchNode]:
    bps: Set[BranchNode] = set()
    for branch_node in cfg.nodes:
        if isinstance(branch_node, BranchNode):
            paths = list(branch_node.children)
            branch_node.block()
            if is_reachable(paths[0], cfgnode) ^ is_reachable(paths[1], cfgnode): # xor
                bps.add(branch_node)
            branch_node.unblock()

    return bps
            
