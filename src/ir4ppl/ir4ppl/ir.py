from typing import Set, Dict, List, Any
from .cfg import *
from analysis.rd_bp import *
from analysis.interval_arithmetic import *
from analysis.symbolics import Symbol, SymConstant, SymOperation, SymNot
from functools import reduce

class PPL_IR:
    def __init__(self, cfgs: Dict[FunctionDefinition,CFG], model_cfg: Optional[CFG] = None, guide_cfg: Optional[CFG] = None) -> None:
        self.cfgs = cfgs
        self.node_to_cfg = {node: (fdef, cfg) for fdef, cfg in cfgs.items() for node in cfg.nodes}
        self.model_cfg = model_cfg
        self.guide_cfg = guide_cfg

    def is_user_defined_function(self, variable: Variable) -> bool:
        return any(fdef.is_equal(variable) for fdef, _ in self.cfgs.items())

    def get_user_defined_function(self, variable: Variable) -> CFG:
        for fdef, fcfg in self.cfgs.items():
            if fdef.is_equal(variable):
                return fcfg
        raise ValueError
    
    def get_model(self) -> Optional[CFG]:
        return self.model_cfg
    
    def get_guide(self) -> Optional[CFG]:
        return self.guide_cfg
    
    def get_all_function_calls(self, fdef: FunctionDefinition) -> List[Tuple[CFGNode,FunctionCall]]:
        calls: List[Tuple[CFGNode,FunctionCall]] = list()
        for _, cfg in self.cfgs.items():
            for node in cfg.nodes:
                if isinstance(node, AbstractAssignNode):
                    calls_in_node = node.get_value_expr().get_function_calls(fdef)
                elif isinstance(node, BranchNode):
                    calls_in_node = node.get_test_expr().get_function_calls(fdef)
                elif isinstance(node, ReturnNode):
                    calls_in_node = node.get_return_expr().get_function_calls(fdef)
                elif isinstance(node, ExprNode):
                    calls_in_node = node.get_expr().get_function_calls(fdef)
                else:
                    calls_in_node: List[FunctionCall] = list()
                for call in calls_in_node:
                    calls.append((node, call))
        return calls

    
    def get_cfg_for_node(self, cfgnode: CFGNode) -> Tuple[FunctionDefinition,CFG]:
        return self.node_to_cfg[cfgnode]

    def get_sample_nodes(self) -> List[SampleNode]:
        nodes: List[SampleNode] = list()
        for _, cfg in self.cfgs.items():
            nodes.extend([node for node in cfg.nodes if isinstance(node, SampleNode)])
        return nodes
    
    def get_factor_nodes(self) -> List[FactorNode]:
        nodes: List[FactorNode] = list()
        for _, cfg in self.cfgs.items():
            nodes.extend([node for node in cfg.nodes if isinstance(node, FactorNode)])
        return nodes

    def get_data_deps_for_expr(self, cfgnode: CFGNode, expr: Expression) -> List[AbstractAssignNode]:
        return list(data_deps_for_expr(self, cfgnode, expr))
    
    def get_control_deps_for_node(self, cfgnode: CFGNode, expr: Expression) -> List[BranchNode]:
        return list(control_parents_for_expr(self, cfgnode, expr))


def data_deps_for_expr(ir: PPL_IR, cfgnode: CFGNode, expr: Expression) -> Set[AbstractAssignNode]:
    if isinstance(cfgnode, FuncArgNode):
        fdef, _ = ir.get_cfg_for_node(cfgnode)
        data_deps: Set[AbstractAssignNode] = set()
        # find all calls to function fdef
        calls = ir.get_all_function_calls(fdef)
        # collect all data dependencies for expression passed as argument for arg node
        for callnode, call in calls:
            call_arg_expr = call.get_expr_for_func_arg(cfgnode)
            data_deps = data_deps | data_deps_for_expr(ir, callnode, call_arg_expr)

        return data_deps
    else:
        variables = expr.get_free_variables()

        data_deps: Set[AbstractAssignNode] = set()
        for variable in variables:
            if ir.is_user_defined_function(variable):
                function_cfg = ir.get_user_defined_function(variable)
                for returnnode in function_cfg.nodes:
                    if isinstance(returnnode, ReturnNode):
                        data_deps = data_deps | data_deps_for_expr(ir, returnnode, returnnode.get_return_expr())
            else:
                rds = get_RDs(cfgnode, variable)
                data_deps = data_deps | rds

        return data_deps


def control_parents_for_expr(ir: PPL_IR, cfgnode: CFGNode, expr: Expression) -> Set[BranchNode]:
    fdef, cfg = ir.get_cfg_for_node(cfgnode)
    assert cfgnode in cfg.nodes

    if isinstance(cfgnode, FuncArgNode):
        bps: Set[BranchNode] = set()
        # find all calls to function fdef
        calls = ir.get_all_function_calls(fdef)
        # collect all control parents of call node
        for callnode, call in calls:
            bps = bps | control_parents_for_expr(ir, callnode, call)        
        return bps
    else:
        bps = get_BPs(cfg, cfgnode)

        variables = expr.get_free_variables()
        for variable in variables:
            if ir.is_user_defined_function(variable):
                function_cfg = ir.get_user_defined_function(variable)
                for returnnode in function_cfg.nodes:
                    if isinstance(returnnode, ReturnNode):
                        bps = bps | control_parents_for_expr(ir, returnnode, returnnode.get_return_expr())

        return bps


DEBUG_ESTIMATE_VALUE_RANGE = False
def estimate_value_range(ir: PPL_IR, node: CFGNode, expr: Expression, assumptions: Dict[AbstractAssignNode,Interval], working_set: Set[Tuple[CFGNode,Expression]] = set(), tab="") -> Interval:
    if DEBUG_ESTIMATE_VALUE_RANGE: print(tab, "estimate_value_range", "node:", node, "expr:", expr)
    if (node, expr) in working_set:
        # expr depends on itself (e.g. in loops)
        if DEBUG_ESTIMATE_VALUE_RANGE: print(tab, "loop return [-inf, inf]")
        return Interval(float('-inf'),float('inf'))
    working_set.add((node, expr))
    
    variable_mask : Dict[Variable,Interval] = dict()

    # we have to assign an interval to each free variable in expr
    variables = expr.get_free_variables()
    for variable in variables:

        # check if value range for variable is defined in assumptions

        # recursively estimate value range of variable
        intervals : List[Interval] = list()
        if ir.is_user_defined_function(variable):
            function_cfg = ir.get_user_defined_function(variable)
            for returnnode in function_cfg.nodes:
                if isinstance(returnnode, ReturnNode):
                    intervals.append(estimate_value_range(ir, returnnode, returnnode.get_return_expr(), assumptions, working_set, tab+" |"))
        else:
            rds = get_RDs(node, variable)
            for rd in rds:
                if DEBUG_ESTIMATE_VALUE_RANGE: print(tab, "rd", rd)
                if rd in assumptions:
                    intervals.append(assumptions[rd])
                    if DEBUG_ESTIMATE_VALUE_RANGE: print(tab, "rd in assumptions", assumptions[rd])
                else:
                    intervals.append(estimate_value_range(ir, rd, rd.get_value_expr(), assumptions, working_set, tab+" |"))
        
        interval = reduce(interval_union, intervals) if len(intervals) > 0 else Interval(float('-inf'),float('inf'))
        variable_mask[variable] = interval
        if DEBUG_ESTIMATE_VALUE_RANGE: print(tab, "mask", variable, "with", interval, "as union of", intervals)

    working_set.discard((node,expr))

    if DEBUG_ESTIMATE_VALUE_RANGE: print(tab, "estimate value range of", expr)
    interval = expr.estimate_value_range(variable_mask)
    if DEBUG_ESTIMATE_VALUE_RANGE: print(tab, "return interval", interval)
    return interval

DEBUG_SYMBOLIC = False
def get_symbolic_expression(ir: PPL_IR, node: CFGNode, expr: Expression, assumptions: Dict[AbstractAssignNode,SymbolicExpression], working_set: Set[Tuple[CFGNode,Expression]] = set(), tab="") -> SymbolicExpression:
    if DEBUG_SYMBOLIC: print(tab, "get_symbolic_expression", "node:", node, "expr:", expr)
    if isinstance(node, FuncArgNode):
        if DEBUG_SYMBOLIC: print(tab, f"new symbol for funcarg {node.name}")
        return Symbol(node.name)
    if (node, expr) in working_set:
        # expr depends on itself (e.g. in loops)
        raise Exception(f"get_symbolic_expression does not support cyclic dependencies yet, expr {expr} in node {node}")
    working_set.add((node, expr))
    
    variable_mask : Dict[Variable,SymbolicExpression] = dict()

    # we have to assign an interval to each free variable in expr
    variables = expr.get_free_variables()
    for variable in variables:

        # recursively estimate value range of variable
        if ir.is_user_defined_function(variable):
            continue # Not supported
        else:
            rds = get_RDs(node, variable)
            if len(rds) == 0:
                print(tab, f"no rds for {variable}")
                continue

            rd = rds.pop()
            if DEBUG_SYMBOLIC: print(tab, f"rd for {variable}:", rd)
            if rd in assumptions:
                sexpr = assumptions[rd]
                if DEBUG_SYMBOLIC: print(tab, "rd in assumptions", assumptions[rd])
            else:
                sexpr = get_symbolic_expression(ir, rd, rd.get_value_expr(), assumptions, working_set, tab + " |")
            for rd in rds:
                if DEBUG_SYMBOLIC: print(tab, f"rd for {variable}:", rd)
                if rd in assumptions:
                    rd_sexpr = assumptions[rd]
                    if DEBUG_SYMBOLIC: print(tab, "rd in assumptions", assumptions[rd])
                else:
                    rd_sexpr = get_symbolic_expression(ir, rd, rd.get_value_expr(), assumptions, working_set, tab + " |")
                rd_pc = get_path_condition(ir, rd, assumptions, tab + " |")
                sexpr = SymOperation("ife", rd_pc, rd_sexpr, sexpr)

            variable_mask[variable] = sexpr
            if DEBUG_SYMBOLIC: print(tab, "mask", variable, "with", sexpr)

    working_set.discard((node,expr))

    if DEBUG_SYMBOLIC: print(tab, "get symbolic of", expr, "with", variable_mask)
    sexpr = expr.symbolic(variable_mask)
    if DEBUG_SYMBOLIC: print(tab, "return sexpr", sexpr)
    return sexpr

def get_path_condition(ir: PPL_IR, node: CFGNode, assumptions: Dict[AbstractAssignNode,SymbolicExpression], tab="") -> SymbolicExpression:
    if DEBUG_SYMBOLIC: print(tab, "get_path_condition", node)
    pc = SymConstant(True)
    _, cfg = ir.get_cfg_for_node(node)
    bps = get_BPs(cfg, node)
    for branch_node in bps:
        if DEBUG_SYMBOLIC: print(tab, "bp", branch_node)
        test_symexpr = get_symbolic_expression(ir, branch_node, branch_node.get_test_expr(), assumptions, set(), tab + " |")
        branch_node.block()
        if is_reachable(branch_node.then, node):
            pc_conj = test_symexpr
        else:
            assert is_reachable(branch_node.orelse, node)
            pc_conj = SymNot(test_symexpr)
        if isinstance(pc, SymConstant):
            pc = pc_conj
        else:
            pc = SymOperation("&", pc, pc_conj)
        branch_node.unblock()

    return pc