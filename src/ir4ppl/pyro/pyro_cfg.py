from copy import copy
from ir4ppl.cfg import *
import ast

from ir4ppl.cfg import AssignTarget, Dict, Distribution, Expression, FunctionDefinition, SymbolicExpression, Variable
from ir4ppl.cfg import SourceLocation
from ir4ppl.cfg import CFGNode, EndNode, FuncStartNode, StartNode
from pyro.syntaxnode import Dict
from .node_finder import NodeVisitor, NodeFinder
from .syntaxnode import *
import ast_scope
from ast_scope.annotate import ScopeInfo
from ir4ppl.ir import PPL_IR
from typing import Any, List, Set
from ir4ppl.base_cfg import AbstractCFGBuilder
from analysis.symbolics import Symbol, SymOperation, SymConstant
from analysis.interval_arithmetic import * 
from typing import Callable

class PythonVariable(Variable):
    def __init__(self, syntaxnode: SyntaxNode, scope_info: ScopeInfo) -> None:
        super().__init__()
        assert isinstance(syntaxnode.ast_node, ast.Name)
        self.syntaxnode = syntaxnode
        self.name = syntaxnode.ast_node.id
        self.scope = scope_info[syntaxnode.ast_node]
    def __eq__(self, value: object) -> bool:
        if isinstance(value, PythonVariable):
            return self.syntaxnode == value.syntaxnode
        else:
            return False
    def __hash__(self) -> int:
        return hash(self.syntaxnode)
    
    def is_indexed_variable(self) -> bool:
        # x[i]
        return self.syntaxnode.parent is not None and self.syntaxnode.parent.is_kind(ast.Subscript)
    
    def __repr__(self) -> str:
        return f"PythonVariable({self.name})"

import math
def peval_ints(node: ast.AST):
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return peval_ints(node.left) + peval_ints(node.right)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
        return peval_ints(node.left) - peval_ints(node.right)
    return math.nan

def get_static_index_of_ref_identifier(ref_node: ast.AST):
    match ref_node:
        case ast.Subscript(slice=ast.Tuple(elts=_elts)):
            return [peval_ints(el) for el in _elts]
        case ast.Subscript(slice=_slice):
            return [peval_ints(_slice)]
    return math.nan


class PythonAssignTarget(AssignTarget):
    def __init__(self, target: SyntaxNode, scope_info: ScopeInfo) -> None:
        super().__init__()
        assert target.is_kind((ast.Name, ast.Subscript, ast.Attribute, ast.arg)), f"target {target} is of wrong kind {target.kind()}"
        self.target = target
        self.scope_info = scope_info

        if isinstance(target.ast_node, ast.Name):
            self.name = target.ast_node.id
            self.scope = scope_info[target.ast_node]
        elif isinstance(target.ast_node, ast.Subscript):
            assert isinstance(target.ast_node.value, ast.Name), "Subscript AssignTarget has to be static"
            name_node = target.ast_node.value
            self.name = name_node.id
            self.scope = scope_info[name_node]
        elif isinstance(target.ast_node, ast.Attribute):
            # a.b -> (a, scope[a])
            name_node = target.ast_node
            while isinstance(name_node, ast.Attribute):
                name_node = name_node.attr
            assert isinstance(name_node, ast.Name)
            self.name = name_node.id
            self.scope = scope_info[name_node]
        else: #isinstance(target.ast_node, ast.arg):
            assert isinstance(target.ast_node, ast.arg)
            self.name = target.ast_node.arg
            self.scope = scope_info[target.ast_node]
    
    def is_equal(self, variable: Variable) -> bool:
        assert isinstance(variable, PythonVariable)
        return self.name == variable.name and self.scope == variable.scope
    
    def is_indexed_target(self) -> bool:
        return self.target.is_kind(ast.Subscript)
    
    def index_is_equal(self, variable: Variable) -> bool:
        assert isinstance(variable, PythonVariable)
        assert self.target.is_kind(ast.Subscript)
        assert variable.syntaxnode.parent is not None and variable.syntaxnode.parent.is_kind(ast.Subscript) # variable.is_indexed_variable()
        return get_static_index_of_ref_identifier(self.target.ast_node) == get_static_index_of_ref_identifier(variable.syntaxnode.parent.ast_node)
        
    def get_index_expr(self) -> Expression:
        assert self.target.is_kind(ast.Subscript)
        return PythonExpression(self.target["slice"], self.scope_info)
 
    def __repr__(self) -> str:
        return ast.unparse(self.target.ast_node)

PYTHON_AST_NODE_TO_SYM_OP: Dict[type,str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Pow: "^",
    ast.And: "&",
    ast.Or: "|",
    ast.Not: "!",
    ast.USub: "-",
    ast.Eq: "==",
    ast.Is: "==",
    ast.NotEq: "!=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Lt: "<",
    ast.LtE: "<="
}

PYTHON_AST_NODE_TO_INTERVAL_OP: Dict[type | str ,Callable] = {
    ast.Add: interval_add,
    ast.Sub: interval_sub,
    ast.USub: interval_usub,
    ast.Mult: interval_mul,
    ast.Div: interval_div,
    ast.Pow: interval_pow,
    'sqrt': interval_sqrt,
    'exp': interval_exp,
    'log': interval_log,
    'maximum': interval_maximum,
    'minimum': interval_minimum,

    # pytensor
    'ifelse': interval_ifelse,
    'switch': interval_ifelse,
    'invlogit': interval_invlogit,
    'outer': interval_mul, # outer product
    'eq': interval_eq,
    'flatten': interval_no_op,
    'stack': interval_no_op,
    'reshape': interval_no_op,
    'repeat': interval_no_op,
    'clip': interval_clip,
    'erf': interval_erf,
    'ones': interval_ones,
    'prod': interval_prod,
    'constant': interval_no_op, # pm.math.constant
    'eye': interval_eye,
}
from functools import reduce

def get_call_name(node: ast.Call) -> str:
    assert isinstance(node, ast.Call)
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute): # and isinstance(node.func.value, ast.Name):
        return node.func.attr
    raise Exception(f"Cannot find name for call {ast.dump(node)}")

class PythonExpression(Expression):
    def __init__(self, syntaxnode: SyntaxNode, scope_info: ScopeInfo) -> None:
        super().__init__()
        self.syntaxnode = syntaxnode
        self.scope_info = scope_info
    def __eq__(self, value: object) -> bool:
        if isinstance(value, PythonExpression):
            return self.syntaxnode == value.syntaxnode
        else:
            return False
    def __hash__(self) -> int:
        return hash(self.syntaxnode)

    def get_free_variables(self) -> List[Variable]:
        name_finder = NodeFinder(
            lambda node: isinstance(node.ast_node, ast.Name) and isinstance(node.ast_node.ctx, ast.Load),
            lambda node: PythonVariable(node, self.scope_info)) # this also returns variable names for user-defined functions
        return name_finder.visit(self.syntaxnode)
    
    def get_function_calls(self, fdef: FunctionDefinition) -> List[FunctionCall]:
        call_finder = NodeFinder(
            lambda node: (isinstance(node.ast_node, ast.Call) and
                          node["func"].is_kind(ast.Name) and
                          fdef.is_equal(PythonVariable(node["func"], self.scope_info))),
            lambda node: PythonFunctionCall(node, self.scope_info))
        return call_finder.visit(self.syntaxnode)

    def _estimate_value_range_rec(self, node: ast.AST, variable_mask: Dict[Variable,Interval]) -> Interval:
        match node:
            case ast.Name(id=name):
                v = PythonVariable(get_syntaxnode(node), self.scope_info)
                return variable_mask.get(v, Interval(float('-inf'), float('inf')))
            case ast.Constant(value=value):
                return Interval(value, value)
            case ast.UnaryOp(operand=operand, op=op):
                func = PYTHON_AST_NODE_TO_INTERVAL_OP.get(type(op), StaticRangeOp(Interval(float('-inf'), float('inf'))))
                return func(self._estimate_value_range_rec(operand, variable_mask))
            case ast.BinOp(left=left, right=right, op=op):
                intleft = self._estimate_value_range_rec(left, variable_mask)
                intright = self._estimate_value_range_rec(right, variable_mask)
                func = PYTHON_AST_NODE_TO_INTERVAL_OP.get(type(op), StaticRangeOp(Interval(float('-inf'), float('inf'))))
                return func(intleft, intright)
            case ast.BoolOp(values=values, op=op):
                symvalues = [self._estimate_value_range_rec(value, variable_mask) for value in values]
                func = PYTHON_AST_NODE_TO_INTERVAL_OP.get(type(op), StaticRangeOp(Interval(float('-inf'), float('inf'))))
                return func(*symvalues)
            case ast.Compare(left=left, ops=[op], comparators=[right]):
                intleft = self._estimate_value_range_rec(left, variable_mask)
                intright = self._estimate_value_range_rec(right, variable_mask)
                func = PYTHON_AST_NODE_TO_INTERVAL_OP.get(type(op), StaticRangeOp(Interval(float('-inf'), float('inf'))))
                return func(intleft, intright)
            case ast.Call(func=name, args=args):
                symvalues = [self._estimate_value_range_rec(value, variable_mask) for value in args]
                if isinstance(name, ast.Name):
                    v = PythonVariable(get_syntaxnode(name), self.scope_info)
                    if v in variable_mask:
                        return variable_mask[v]
                name = get_call_name(node)
                func = PYTHON_AST_NODE_TO_INTERVAL_OP.get(name, StaticRangeOp(Interval(float('-inf'), float('inf'))))
                return func(*symvalues)
            case ast.List(elts=elts):
                symvalues = [self._estimate_value_range_rec(value, variable_mask) for value in elts]
                return reduce(interval_union, symvalues)
            case ast.Subscript(value=value):
                return self._estimate_value_range_rec(value, variable_mask)
            case _:
                raise Exception(f"Unsupported expr {ast.dump(node)}")
            
    def estimate_value_range(self, variable_mask: Dict[Variable,Interval]) -> Interval:
        return self._estimate_value_range_rec(self.syntaxnode.ast_node, variable_mask)
    
    def _symbolic_rec(self, node: ast.AST, variable_mask: Dict[Variable,SymbolicExpression]) -> SymbolicExpression:
        match node:
            case ast.Name(id=name):
                v = PythonVariable(get_syntaxnode(node), self.scope_info)
                return variable_mask.get(v, Symbol(name))
            case ast.Constant(value=value):
                return SymConstant(value)
            case ast.UnaryOp(operand=operand, op=op):
                return SymOperation(PYTHON_AST_NODE_TO_SYM_OP[type(op)], self._symbolic_rec(operand, variable_mask))
            case ast.BinOp(left=left, right=right, op=op):
                symleft = self._symbolic_rec(left, variable_mask)
                symright = self._symbolic_rec(right, variable_mask)
                return SymOperation(PYTHON_AST_NODE_TO_SYM_OP[type(op)], symleft, symright)
            case ast.BoolOp(values=values, op=op):
                symvalues = [self._symbolic_rec(value, variable_mask) for value in values]
                return SymOperation(PYTHON_AST_NODE_TO_SYM_OP[type(op)], *symvalues)
            case ast.Compare(left=left, ops=[op], comparators=[right]):
                symleft = self._symbolic_rec(left, variable_mask)
                symright = self._symbolic_rec(right, variable_mask)
                return SymOperation(PYTHON_AST_NODE_TO_SYM_OP[type(op)], symleft, symright)
            case ast.Call(args=args):
                # we do not support recursing in user-defined functions yet
                symvalues = [self._symbolic_rec(value, variable_mask) for value in args]
                name = get_call_name(node)
                return SymOperation(name, *symvalues)
            case ast.List(elts=elts):
                symvalues = [self._symbolic_rec(value, variable_mask) for value in elts]
                return SymOperation("List", *symvalues)
            case _:
                raise Exception(f"Unsupported expr {ast.dump(node)}")

    def symbolic(self, variable_mask: Dict[Variable,SymbolicExpression]) -> SymbolicExpression:
        return self._symbolic_rec(self.syntaxnode.ast_node, variable_mask)
    
    def __repr__(self) -> str:
        return ast.unparse(self.syntaxnode.ast_node)
    
class PythonFunctionCall(PythonExpression, FunctionCall):
    def get_expr_for_func_arg(self, node: FuncArgNode) -> Expression:
        target = node.get_target()
        assert isinstance(target, PythonAssignTarget)
        assert target.target.is_kind(ast.arg)
        assert self.syntaxnode.is_kind(ast.Call)
        call_site = self.syntaxnode
        # first check if the argument is passed by name
        for kw in call_site.get_children("keywords"):
            assert isinstance(kw.ast_node, ast.keyword)
            if kw.ast_node == node.get_arg_name():
                return PythonExpression(kw["value"], self.scope_info)

        param_ix = node.get_index_in_func()
        args = list(call_site.get_children("args"))
        if param_ix < len(args):
            # select param_ix-th argument in call site
            return PythonExpression(args[param_ix], self.scope_info)
        else:
            return EmptyPythonExpression() # has to have default argument

    
class EmptyPythonExpression(PythonExpression):
    def __init__(self) -> None:
        pass
    def __hash__(self) -> int:
        return 0
    def __eq__(self, value: object) -> bool:
        return isinstance(value, EmptyPythonExpression)
    def get_free_variables(self) -> List[Variable]:
        return list()
    def get_function_calls(self, fdef: FunctionDefinition) -> List[FunctionCall]:
        return list()
    def estimate_value_range(self, variable_mask: Dict[Variable,Interval]) -> Interval:
        return Interval(float('-inf'),float('inf'))
    def symbolic(self, variable_mask: Dict[Variable, SymbolicExpression]) -> SymbolicExpression:
        return SymConstant(True)
    def __repr__(self) -> str:
        return "<>"
    
def get_only_elem(s: Set[CFGNode]) -> CFGNode:
    assert len(s) == 1
    return list(s)[0]

class PythonFunctionDefinition(FunctionDefinition):
    def __init__(self, syntaxnode: SyntaxNode, scope_info: ScopeInfo) -> None:
        super().__init__()
        assert syntaxnode.is_kind(ast.Module) or syntaxnode.is_kind(ast.FunctionDef) # toplevel ("main") or functiondef
        self.syntaxnode = syntaxnode
        self.name = ""
        if isinstance(syntaxnode.ast_node, ast.FunctionDef):
            self.name = syntaxnode.ast_node.name
            self.scope = scope_info[syntaxnode.ast_node]
            # is the scope in which the function is defined
            # ast.Name in ast.Call will also have this scope
        else:
            self.name = "Toplevel"
            self.scope = None

    def is_equal(self, variable: Variable) -> bool:
        assert isinstance(variable, PythonVariable)
        return self.name == variable.name and self.scope == variable.scope
        
    def __repr__(self) -> str:
        if self.syntaxnode.is_kind(ast.Module):
            return "PythonFunctionDefinition(Main)"
        else:
            assert isinstance(self.syntaxnode.ast_node, ast.FunctionDef)
            return f"PythonFunctionDefinition{self.syntaxnode.ast_node.name})"

from .torch_distribution import parse_torch_distribution
def get_distribution_from_node(distribution_node: ast.AST, scope_info: ScopeInfo):
    # dist.Normal(0,1).to_event() ... -> dist.Normal(0,1)
    while isinstance(distribution_node, ast.Call) and isinstance(distribution_node.func, ast.Attribute) and isinstance(distribution_node.func.value, ast.Call):
        distribution_node = distribution_node.func.value

    assert isinstance(distribution_node, ast.Call)
    name = get_call_name(distribution_node)

    args = distribution_node.args
    kwargs = {kw.arg: kw.value for kw in distribution_node.keywords}

    dist_name, dist_params = parse_torch_distribution(name, args, kwargs)
    dist_args: Dict[str, Expression] = {argname: PythonExpression(get_syntaxnode(ast_node), scope_info) for argname, ast_node in dist_params.items()}
    return Distribution(dist_name, dist_args)

class PyroSampleNode(SampleNode):
    def get_distribution_expr(self) -> Expression:
        value_expr = self.get_value_expr()
        assert isinstance(value_expr, PythonExpression)
        assert value_expr.syntaxnode.is_kind(ast.Call)
        return PythonExpression(value_expr.syntaxnode["args_1"], value_expr.scope_info)
    
    def get_distribution(self) -> Distribution:
        value_expr = self.get_value_expr()
        assert isinstance(value_expr, PythonExpression)
        assert value_expr.syntaxnode.is_kind(ast.Call)
        distribution_syntaxnode = value_expr.syntaxnode["args_1"]
        distribution_node = distribution_syntaxnode.ast_node
        return get_distribution_from_node(distribution_node, value_expr.scope_info)
        
    def get_address_expr(self) -> Expression:
        value_expr = self.get_value_expr()
        assert isinstance(value_expr, PythonExpression)
        assert value_expr.syntaxnode.is_kind(ast.Call)
        return PythonExpression(value_expr.syntaxnode["args_0"], value_expr.scope_info)
    
    def symbolic_name(self) -> str:
        addr = self.get_address_expr()
        assert isinstance(addr, PythonExpression)
        return ast.unparse(addr.syntaxnode.ast_node)

class PyroFactorNode(FactorNode):
    def __init__(self, id: str, factor_expression: Expression) -> None:
        super().__init__(id, factor_expression)
    def get_distribution(self) -> Distribution:
        value_expr = self.get_factor_expr()
        assert isinstance(value_expr, PythonExpression)
        assert value_expr.syntaxnode.is_kind(ast.Call)
        distribution_syntaxnode = value_expr.syntaxnode["args_1"]
        distribution_node = distribution_syntaxnode.ast_node
        return get_distribution_from_node(distribution_node, value_expr.scope_info)


def is_supported_expression(node: ast.AST):
    if not isinstance(node, (
        ast.Expr, ast.Import, ast.ImportFrom, # stmt
        ast.BoolOp, ast.NamedExpr, ast.BinOp, ast.UnaryOp, ast.Dict, ast.Set, ast.Compare, ast.Call, ast.JoinedStr, ast.FormattedValue,
        ast.Constant, ast.Attribute, ast.Subscript, ast.Name, ast.List, ast.Tuple, ast.Slice, # expr
        ast.expr_context, ast.boolop, ast.operator, ast.unaryop, ast.cmpop, ast.arguments, ast.arg, ast.keyword, ast.alias,
        ast.Pass
        )):
        print("Is unsupported expression", node)
        return False
    return all(is_supported_expression(child) for child in ast.iter_child_nodes(node))

class PyroCFG(CFG):
    def __init__(self, startnode: StartNode | FuncStartNode, nodes: Set[CFGNode], endnode: EndNode, source_location: Optional[SourceLocation]) -> None:
        super().__init__(startnode, nodes, endnode)
        self.source_location = source_location
    def get_source_location(self) -> SourceLocation:
        assert self.source_location is not None
        return self.source_location

class PyroCFGBuilder(AbstractCFGBuilder):
    def __init__(self, node_to_id: Dict[SyntaxNode,str], scope_info: ScopeInfo) -> None:
        self.node_to_id = node_to_id
        self.cfgs: Dict[FunctionDefinition,CFG] = dict() # toplevel -> CFG, functiondef -> CFG
        self.scope_info = scope_info

    def is_random_variable_definition(self, node: ast.AST) -> bool:
        match node:
            case ast.Assign(value=ast.Call(func=ast.Attribute(value=ast.Name(id=_id), attr=_attr))) if _id == "pyro" and _attr == "sample":
                return True
            case ast.Assign(value=ast.Call(func=ast.Name(id=_id))) if _id == "sample":
                return True
        return False
    
    def is_observed(self, node: ast.AST) -> bool:
        match node:
            case ast.Assign(value=ast.Call(func=ast.Attribute(value=ast.Name(id=_id), attr=_attr),keywords=[*_, ast.keyword(arg='obs')])) if _id == "pyro" and _attr == "sample":
                return True
            case ast.Assign(value=ast.Call(func=ast.Name(id=_id),keywords=[*_, ast.keyword(arg='obs')])) if _id == "sample":
                return True
        return False

    def fix_break_continue(self, nodes: Set[CFGNode], breaknode: CFGNode, continuenode: CFGNode):
        for node in nodes:
            if isinstance(node, BreakNode):
                discard = [child for child in node.children if child != breaknode]
                for child in discard:
                    delete_edge(node, child)
            if isinstance(node, ContinueNode):
                discard = [child for child in node.children if child != continuenode]
                for child in discard:
                    delete_edge(node, child)
        

    def get_cfg(self, node: SyntaxNode, breaknode:Optional[JoinNode], continuenode:Optional[JoinNode], returnnode:Optional[JoinNode]) -> CFG: # type: ignore
        node_id = self.node_to_id[node]

        startnode = StartNode(node_id)
        nodes: Set[CFGNode] = set()
        endnode = EndNode(node_id)

        if node.is_kind(ast.Module):
            cfg = self.get_cfg(node["body"], None, None, None)
            self.cfgs[PythonFunctionDefinition(node, self.scope_info)] = cfg
            return cfg
        
        if node.is_kind(ast.With):
            return self.get_cfg(node["body"], None, None, None)

        if node.is_kind(Block):
            # concatentate all children if they are not functions
            # S_i -> CFG_i -> E_i
            # => S -> CFG_1 -> ... CFG_n -> E
            current_node: CFGNode = startnode
            for child in [node.children[f"stmt_{i}"] for i in range(len(node.children))]:
                child_node_id = self.node_to_id[child]
                if child.is_kind(ast.FunctionDef):
                    function_cfg = self.get_function_cfg(child)
                    self.cfgs[PythonFunctionDefinition(child, self.scope_info)] = function_cfg
                
                elif child.is_kind((ast.Return, ast.Break, ast.Continue)):
                    if child.is_kind(ast.Return):
                        if "value" in child.children:
                            special_node = ReturnNode(child_node_id, PythonExpression(child["value"], self.scope_info))
                        else:
                            special_node = ReturnNode(child_node_id, EmptyPythonExpression())
                        goto_node = returnnode
                    elif child.is_kind(ast.Break):
                        special_node = BreakNode(child_node_id)
                        goto_node = breaknode
                    else: # child.is_kind(ast.Continue):
                        special_node = ContinueNode(child_node_id)
                        goto_node = continuenode
                    
                    # CFG_i -> SPECIAL_NODE -> GOTO_NODE
                    nodes.add(special_node)
                    add_edge(current_node, special_node)
                    current_node = special_node
                    assert goto_node is not None
                    add_edge(current_node, goto_node)
                    break

                else:
                    child_cfg = self.get_cfg(child, breaknode, continuenode, returnnode)
                    nodes = nodes.union(child_cfg.nodes)

                    N1 = get_only_elem(child_cfg.startnode.children) # node after start node
                    N2 = get_only_elem(child_cfg.endnode.parents)    # node before end node

                    delete_edge(child_cfg.startnode, N1)
                    add_edge(current_node, N1)
                    delete_edge(N2, child_cfg.endnode)
                    
                    # parents come from sub-cfg
                    current_node = N2

            add_edge(current_node, endnode)


        elif node.is_kind(ast.Assign):
            # S -> Assign -> E
            assert "targets_1" not in node.children, "Multi-assignments not allowed"
            if self.is_random_variable_definition(node.ast_node):
                # print(ast.dump(node.ast_node))
                if self.is_observed(node.ast_node):
                    cfgnode = PyroFactorNode(
                        node_id,
                        PythonExpression(node["value"], self.scope_info)
                    )
                else:
                    cfgnode = PyroSampleNode(
                        node_id,        
                        PythonAssignTarget(node["targets_0"], self.scope_info),
                        PythonExpression(node["value"], self.scope_info)
                    )
            else:
                cfgnode = AssignNode(
                    node_id,
                    PythonAssignTarget(node["targets_0"], self.scope_info),
                    PythonExpression(node["value"], self.scope_info)
                )
            nodes.add(cfgnode)
            add_edge(startnode, cfgnode)
            add_edge(cfgnode, endnode)

        elif node.is_kind(ast.If):
            test_node = node["test"]
            
            branch_cfgnode = BranchNode(node_id + "_if_start", PythonExpression(test_node, self.scope_info))
            branch_join_cfgnode = JoinNode(node_id + "_if_end")
            branch_cfgnode.join_nodes.add(branch_join_cfgnode)

            consequent = node["body"]
            alternative = node["orelse"] if isinstance(node["orelse"].ast_node, Block) and len(node["orelse"].ast_node) > 0 else None

            self.build_if_cfg(startnode, nodes, endnode, branch_cfgnode, branch_join_cfgnode, consequent, alternative, continuenode, breaknode, returnnode)
            
        elif node.is_kind(ast.While):
            # S_body -> CFG_body -> E_body
            # => S -> Branch -> CFG_body \
            #           |   \<-----------/
            #            \> Join -> E   
            test_node = node["test"]

            while_start_join_cfgnode = JoinNode(node_id + "_while_start")
            while_branch_cfgnode = BranchNode(node_id + "_while_test", PythonExpression(test_node, self.scope_info))
            while_end_join_cfgnode = JoinNode(node_id + "_while_end")

            while_branch_cfgnode.join_nodes.add(while_start_join_cfgnode)
            while_branch_cfgnode.join_nodes.add(while_end_join_cfgnode)

            body = node["body"]

            self.build_while_cfg(startnode, nodes, endnode, while_start_join_cfgnode, while_branch_cfgnode, while_end_join_cfgnode, body, returnnode)

        
        elif node.is_kind(ast.For):
            loop_var = node["iter"]
            body = node["body"]

            for_start_join_cfgnode = JoinNode(node_id + "_for_start")
            for_branch_cfgnode = BranchNode(node_id + "_for_iter", PythonExpression(loop_var, self.scope_info))
            for_end_join_cfgnode = JoinNode(node_id + "_for_end")

            loop_var_cfgnode = LoopIterNode(
                node_id, 
                PythonAssignTarget(node["target"], self.scope_info),
                PythonExpression(node["iter"], self.scope_info)
            )

            self.build_for_cfg(startnode, nodes, endnode, for_start_join_cfgnode, for_branch_cfgnode, for_end_join_cfgnode, loop_var_cfgnode, body, returnnode)
            
        elif is_supported_expression(node.ast_node):
            cfgnode = ExprNode(node_id, PythonExpression(node, self.scope_info))
            nodes.add(cfgnode)
            add_edge(startnode, cfgnode)
            add_edge(cfgnode, endnode)
        else:
            raise Exception(f"Unsupported node {node}")


        cfg =  PyroCFG(startnode, nodes, endnode, None)
        try:
            verify_cfg(cfg)
        except Exception:
            print(ast.unparse(node.ast_node))
            print_cfg_dot(cfg)
            raise
        return cfg
    

    def fix_return(self, nodes: Set[CFGNode], func_join_node: CFGNode):
        for node in nodes:
            if isinstance(node, ReturnNode):
                discard = [child for child in node.children if child != func_join_node]
                for child in discard:
                    delete_edge(node, child)
        
    def get_function_cfg(self, node: SyntaxNode): # type: ignore
        # assert node.is_kind(ast.FunctionDef)
        assert isinstance(node.ast_node, ast.FunctionDef)
        ast_node = node.ast_node
        node_id = self.node_to_id[node]
        func_signature = f"{ast_node.name}({ast.unparse(ast_node.args)})"
        func_body = node["body"]

        # all returns go to join node
        func_join_cfgnode = JoinNode(node_id + "_func")
        # return stmts "break" to join_node, no continuenode
        body_cfg = self.get_cfg(func_body, None, None, func_join_cfgnode)

        nodes = copy(body_cfg.nodes)
        nodes.add(func_join_cfgnode)

        # FUNCSTART -> FUNCARG1 -> FUNCARG2 ...
        startnode = FuncStartNode(node_id, func_signature)
        current_node = startnode
        assert len(ast_node.args.posonlyargs) == 0, f"Position only args are not supported yet. ({ast_node.name, ast_node.args.posonlyargs})"
        assert len(ast_node.args.kwonlyargs) == 0, f"Keyword only args are not supported yet. ({ast_node.name, ast_node.args.kwonlyargs})"
        for i, field in enumerate(node["args"].fields):
            p = node["args"][field]
            # print(i, field, p)
            funcarg_node_id = self.node_to_id[p]
            assert isinstance(p.ast_node, ast.arg), f"Param {p} is not ast.arg"
            name = p.ast_node.arg
            funcarg_node = FuncArgNode(funcarg_node_id, PythonAssignTarget(p, self.scope_info), EmptyPythonExpression(), name, i)
            add_edge(current_node, funcarg_node)
            nodes.add(funcarg_node)
            current_node = funcarg_node
        
        endnode = EndNode(node_id)

        N1 = get_only_elem(body_cfg.startnode.children) # node after start node
        N2 = get_only_elem(body_cfg.endnode.parents)    # node before end node

        delete_edge(N2, body_cfg.endnode)
        delete_edge(body_cfg.startnode, N1)
        
        # FUNCARGS -> BODY
        add_edge(current_node, N1)
        # BODY -> JOIN_NODE -> END
        add_edge(N2, func_join_cfgnode)
        add_edge(func_join_cfgnode, endnode)

        self.fix_return(nodes, func_join_cfgnode)

        s = get_syntaxnode(ast_node)
        end_position = s.source.source.index("\n", s.position) # take one line
        cfg = PyroCFG(startnode, nodes, endnode, SourceLocation(s.source[s.position : end_position], s.position, end_position))
        try:
            verify_cfg(cfg)
        except Exception:
            print_cfg_dot(cfg)
            raise
        return cfg
    
    

class NodeIdAssigner(NodeVisitor):
    def __init__(self) -> None:
        self.node_to_id: Dict[SyntaxNode, str] = {}
        self.id_to_node: Dict[str, SyntaxNode] = {}

    def visit(self, node: SyntaxNode):
        i = f"node_{len(self.node_to_id) + 1}"
        self.node_to_id[node] = i
        self.id_to_node[i] = node

        self.generic_visit(node)

from .preproc import MultitargetTransformer, PyroPreprocessor, LoopUnroller
def get_IR_for_pyro(filename: str):

    line_offsets = get_line_offsets(filename)
    file_content = get_file_content(filename)
    root_node = deepcopy(ast.parse(file_content.source))
    MultitargetTransformer().visit(root_node)
    LoopUnroller(3).visit(root_node)
    root_node = PyroPreprocessor().visit(root_node)

    scope_info = ast_scope.annotate(root_node)
    syntaxtree = make_syntaxtree(root_node, line_offsets, file_content)

    node_id_assigner = NodeIdAssigner()
    node_id_assigner.visit(syntaxtree)
    node_to_id = node_id_assigner.node_to_id
    id_to_node = node_id_assigner.id_to_node

    cfgbuilder = PyroCFGBuilder(node_to_id, scope_info)
    cfgbuilder.get_cfg(syntaxtree, None, None, None)
    for _, cfg in cfgbuilder.cfgs.items():
        assert verify_cfg(cfg)

    return PPL_IR(
        cfgbuilder.cfgs,
        model_cfg=next(
            cfg for fdef, cfg in cfgbuilder.cfgs.items()
            if isinstance(fdef, PythonFunctionDefinition) and fdef.name == "model"
        ),
        guide_cfg=next(
            cfg for fdef, cfg in cfgbuilder.cfgs.items()
            if isinstance(fdef, PythonFunctionDefinition) and fdef.name == "guide"
        )
        ) # default function names for model and guide
