from typing import List, Tuple, Dict, Set, Optional
from analysis.interval_arithmetic import Interval
from analysis.symbolics import SymbolicExpression
from typing import Set, Dict, Optional
from graphviz import Source

class Variable:
    def is_indexed_variable(self) -> bool:
        # x[i]
        raise NotImplementedError
    def __eq__(self, value: object) -> bool:
        raise NotImplementedError
    def __hash__(self) -> int:
        raise NotImplementedError
    
class FunctionDefinition:
    def is_equal(self, variable: Variable) -> bool:
        raise NotImplementedError

# abtract
# an expression does not modify state
# -> this is a big assumption (implies function calls have no side-effects)
class Expression:
    def __eq__(self, value: object) -> bool:
        raise NotImplementedError
    def __hash__(self) -> int:
        raise NotImplementedError
    def get_free_variables(self) -> List[Variable]:
        raise NotImplementedError
    def get_function_calls(self, fdef: FunctionDefinition) -> List['FunctionCall']:
        raise NotImplementedError
    def estimate_value_range(self, variable_mask: Dict[Variable,Interval]) -> Interval:
        raise NotImplementedError
    def symbolic(self, variable_mask: Dict[Variable,SymbolicExpression]) -> SymbolicExpression:
        raise NotImplementedError

class AssignTarget:
    def is_equal(self, variable: Variable) -> bool:
        raise NotImplementedError
    
    def is_indexed_target(self) -> bool:
        # x[i] = ...
        raise NotImplementedError
    
    def index_is_equal(self, variable: Variable) -> bool:
        raise NotImplementedError
    
    def get_index_expr(self) -> Expression:
        raise NotImplementedError
    
class FunctionCall(Expression):
    def get_expr_for_func_arg(self, node: 'FuncArgNode') -> Expression:
        raise NotImplementedError
    
class Distribution:
    def __init__(self, name: str, args: Dict[str,Expression]) -> None:
        self.name = name
        self.args = args
    def __repr__(self) -> str:
        args_s = ", ".join([f"{name}: {arg}" for name, arg in self.args.items()])
        return f"{self.name}({args_s})"
    
class CFGNode:
    def __init__(self, id: str) -> None:
        self.id = id
        self.parents: Set[CFGNode] = set()
        self.children: Set[CFGNode]  = set()
        self.is_blocked = False
    def block(self):
        self.is_blocked = True
    def unblock(self):
        self.is_blocked = False
    def __repr__(self) -> str:
        s = type(self).__name__
        return f"{s}({self.id})"

class StartNode(CFGNode): pass

class EndNode(CFGNode): pass

class SkipNode(CFGNode): pass

class AbstractAssignNode(CFGNode):
    def __init__(self, id: str, target: AssignTarget, value: Expression) -> None:
        super().__init__(id)
        self.target = target
        self.value = value
    def get_target(self) -> AssignTarget:
        return self.target
    def get_value_expr(self) -> Expression:
        return self.value
    def __repr__(self) -> str:
        s = type(self).__name__
        return f"{s}({self.get_target()} = {self.get_value_expr()}, {self.id})"
        

class AssignNode(AbstractAssignNode):
    pass

class SampleNode(AbstractAssignNode):
    def get_distribution_expr(self) -> Expression:
        raise NotImplementedError
    def get_address_expr(self) -> Expression:
        raise NotImplementedError
    def get_distribution(self) -> Distribution:
        raise NotImplementedError
    def symbolic_name(self) -> str:
        raise NotImplementedError
    

class LoopIterNode(AbstractAssignNode): pass

class FuncArgNode(AbstractAssignNode):
    def __init__(self, id: str, target: AssignTarget, value: Expression, name: str, index: int) -> None:
        super().__init__(id, target, value)
        self.name = name
        self.index = index
    def get_arg_name(self) -> str:
        return self.name
    def get_index_in_func(self) -> int:
        return self.index


class BranchNode(CFGNode):
    def __init__(self, id: str, test_expression: Expression) -> None:
        super().__init__(id)
        self.test_expression = test_expression
        self.join_nodes: Set[CFGNode] = set()
        self.then: CFGNode = None # type: ignore
        self.orelse: CFGNode = None # type: ignore
    def get_test_expr(self) -> Expression:
        return self.test_expression
    def __repr__(self) -> str:
        s = type(self).__name__
        return f"{s}({self.get_test_expr()}, {self.id})"
        

class JoinNode(CFGNode): pass

class ReturnNode(CFGNode):
    def __init__(self, id: str, return_expression: Expression) -> None:
        super().__init__(id)
        self.return_expression = return_expression
    def get_return_expr(self) -> Expression:
        return self.return_expression
    def __repr__(self) -> str:
        s = type(self).__name__
        return f"{s}({self.get_return_expr()}, {self.id})"

class BreakNode(CFGNode): pass

class ContinueNode(CFGNode): pass

class FuncStartNode(CFGNode):
    def __init__(self, id: str, func_signature: str) -> None:
        super().__init__(id)
        self.func_signature = func_signature
    def __repr__(self) -> str:
        s = type(self).__name__
        return f"{s}({self.func_signature}, {self.id})"

class ExprNode(CFGNode): 
    def __init__(self, id: str, expression: Expression) -> None:
        super().__init__(id)
        self.expression = expression
    def get_expr(self) -> Expression:
        return self.expression
    def __repr__(self) -> str:
        s = type(self).__name__
        return f"{s}({self.get_expr()}, {self.id})"

class FactorNode(ExprNode):
    def __init__(self, id: str, factor_expression: Expression) -> None:
        super().__init__(id, factor_expression)
    def get_factor_expr(self):
        return self.get_expr()
    def get_distribution(self) -> Distribution:
        raise NotImplementedError

def add_edge(from_node: CFGNode, to_node: CFGNode):
    from_node.children.add(to_node)
    to_node.parents.add(from_node)

def delete_edge(from_node: CFGNode, to_node: CFGNode):
    from_node.children.discard(to_node)
    to_node.parents.discard(from_node)

# from copy import copy

# returns true if startnode is reachable from endnode
# def _is_reachable(startnode: CFGNode, endnode: CFGNode, path: list[CFGNode]):
#     if startnode == endnode:
#         return True
#     for parent in endnode.parents:
#         if parent.is_blocked:
#             continue
#         is_cycle = any(p == parent for p in path)
#         if not is_cycle:
#             new_path = copy(path) if len(endnode.parents) > 1 else path
#             new_path.append(parent)
#             if _is_reachable(startnode, parent, new_path):
#                 return True
#     return False

# def is_reachable(startnode:CFGNode, endnode: CFGNode):
#     return _is_reachable(startnode, endnode, [])

# def _is_reachable_2(startnode: CFGNode, endnode: CFGNode, path: list[CFGNode], memo: Dict[BranchNode,bool]):
#     if startnode == endnode:
#         return True
    
#     if isinstance(endnode, BranchNode) and endnode in memo:
#         return memo[endnode]
    
#     result = False
#     for parent in endnode.parents:
#         if parent.is_blocked:
#             continue
#         is_cycle = any(p == parent for p in path)
#         if not is_cycle:
#             new_path = copy(path) if len(endnode.parents) > 1 else path
#             new_path.append(parent)
#             if _is_reachable_2(startnode, parent, new_path, memo):
#                 result = True
#                 break
        
#     if isinstance(endnode, BranchNode):
#         memo[endnode] = result

#     return result

# def is_reachable(startnode:CFGNode, endnode: CFGNode):
#     return _is_reachable_2(startnode, endnode, [], dict())

def _dfs_visit_nodes(node: CFGNode, visited: Set[CFGNode]):
    visited.add(node)
    for parent in node.parents:
        if parent.is_blocked:
            visited.add(parent) # TODO: check if this makes sense
            continue
        if parent in visited:
            continue
        _dfs_visit_nodes(parent, visited)
        
def is_reachable(startnode: CFGNode, endnode: CFGNode):
    if startnode == endnode:
        return True
    visited = set()
    _dfs_visit_nodes(endnode, visited)
    return startnode in visited

# def is_on_path_between_nodes(node: CFGNode, startnode: CFGNode, endnode: CFGNode):
#     return is_reachable(startnode, node) and is_reachable(node, endnode)


class CFG:
    def __init__(self, startnode: StartNode | FuncStartNode, nodes: Set[CFGNode], endnode: EndNode) -> None:
        # assert isinstance(startnode, (StartNode, FuncStartNode)), f"Wrong type for startnode {startnode}"
        # assert isinstance(endnode, EndNode), f"Wrong type for endnode {endnode}"
        # assert len(startnode.parents) == 0 and len(startnode.children) == 1
        # assert len(endnode.parents) == 1 and len(endnode.children) == 0
        self.startnode = startnode
        self.nodes = nodes
        self.endnode = endnode

    def contains(self, node: CFGNode):
        return self.startnode == node or self.endnode == node or node in self.nodes

def verify_cfg(cfg: CFG):
    if not isinstance(cfg.startnode, (StartNode, FuncStartNode)):
        raise Exception(f"Startnode has wrong type: {cfg.startnode}")
    if not isinstance(cfg.endnode, EndNode):
        raise Exception("Endnode has wrong type: $(cfg.endnode.type)")
    if len(cfg.startnode.parents) != 0 or len(cfg.startnode.children) != 1:
        raise Exception(f"Startnode has wrong number of parents / children: {cfg.startnode.parents} / {cfg.startnode.children}")
    if len(cfg.endnode.parents) != 1 or len (cfg.endnode.children) != 0:
        raise Exception(f"Endnode has wrong number of parents / children: {cfg.endnode.parents} / {cfg.endnode.children}")
    
    for node in cfg.nodes:
        for parent in node.parents:
            if not (node in parent.children):
                raise Exception(f"{parent} is parent of node {node}, but {node} is not among its children {parent.children}") 
        for child in node.children:
            if not (node in child.parents):
                raise Exception(f"{child} is child of node {node}, but {node} is not among its parents {child.parents}") 

        if not isinstance(node, (BranchNode, JoinNode)):
            if len(node.parents) != 1 or len(node.parents) != 1:
                raise Exception(f"{node} has wrong number of parents / children: {node.parents} / {node.children}")

        if isinstance(node, BranchNode):
            if len(node.parents) != 1 or len(node.children) == 0:
                raise Exception(f"{node} has wrong number of parents / children: {node.parents} / {node.children}")
            assert node.then is not None, f"Then branch not set for node {node}"
            assert node.orelse is not None, f"Else branch not set for node {node}"
        if isinstance(node, JoinNode):
            if len(node.children) != 1 or len(node.parents) == 0:
                raise Exception(f"{node} has wrong number of parents / children: {node.parents} / {node.children}")

    return True

def cfg_dot(cfg: CFG, draw_branch_join_pairs: bool = False):
    s = "digraph CFG {\n"
    s += "node [shape=box];\n"
    edges: List[Tuple[CFGNode, CFGNode]] = []
    for node in [cfg.startnode] + list(cfg.nodes) + [cfg.endnode]:
        for child in node.children:
            edges.append((node, child))

    for (node, child) in edges:
        node_s = repr(node).replace('"','\\"')
        child_s = repr(child).replace('"','\\"')
        s += f"\"{node_s}\" -> \"{child_s}\"\n"

    if draw_branch_join_pairs:
        for node in cfg.nodes:
            if isinstance(node, BranchNode):
                for join_node in node.join_nodes:
                    node_s = repr(node).replace('"','\\"')
                    join_node_s = repr(join_node).replace('"','\\"')
                    s += f"\"{node_s}\" -> \"{join_node_s}\" [dir=none, color=red]\n"


    s += "}"
    return s

def print_cfg_dot(cfg: CFG, draw_branch_join_pairs: bool = False):
    print(cfg_dot(cfg, draw_branch_join_pairs))

def plot_cfg(cfg: CFG, filename: str, draw_branch_join_pairs: bool = False):
    s = cfg_dot(cfg, draw_branch_join_pairs)
    source = Source(s, filename=filename, format="pdf", directory="tmp")
    source.view()