# %%
from analysis.symbolics import *
from ir4ppl.ir import * 
from analysis.interval_arithmetic import *
from analysis.distribution_properties import get_distribution_properties, to_interval, ParamDependentBound, IntervalConstraint
from utils.bcolors import bcolors
import z3
from pprint import pprint
from dataclasses import dataclass

def symexpr_to_z3(d: Dict[SampleNode, SymbolicExpression]) -> Dict[SampleNode,z3.ExprRef]:
    # now convert to z3 expression
    def minus(x, y=None):
        if y is None:
            return -x
        else:
            return x - y

    z3_symbol_to_variable = {}
    z3_name_to_func = {
        "Real": z3.Real,
        "Int": z3.Int,
        "Bool": z3.Bool,
        "+": lambda x, y: x + y,
        "-": minus,
        "*": lambda x, y: x * y,
        "/": lambda x, y: x / y,
        "^": lambda x, y: x ** y,
        "&": z3.And,
        "|": z3.Or,
        "!": z3.Not,
        "==": lambda x, y: x == y,
        "!=": lambda x, y: x != y,
        ">": lambda x, y: x > y,
        ">=": lambda x, y: x >= y,
        "<": lambda x, y: x < y,
        "<=": lambda x, y: x <= y,
        "ife": z3.If
    }
    def to_z3(sym: SymbolicExpression):
        # print("...", sym)
        if isinstance(sym, SymOperation):
            return z3_name_to_func[sym.op](*[to_z3(arg) for arg in sym.args])
        elif isinstance(sym, SymConstant):
            return sym.value
        else:
            assert isinstance(sym, Symbol)
            if sym.name in z3_symbol_to_variable:
                variable = z3_symbol_to_variable[sym.name]
            else:
                variable = z3_name_to_func[sym.type](sym.name)
                # print("create variable", variable)
                z3_symbol_to_variable[sym.name] = variable
            return variable

    res = dict()
    for node, s in d.items():
        # print("s", s)
        s_z3 = to_z3(s)
        # print("to z3", s_z3, z3_symbol_to_variable)
        res[node] = s_z3
        
    return res


def get_distribution_constraint(ir: PPL_IR, node: SampleNode):
    assumptions: Dict[AbstractAssignNode,Interval] = dict() # TODO: compute in order
    dist = node.get_distribution()
    properties = get_distribution_properties(dist.name)
    assert properties is not None
    constraint = properties.support
    if isinstance(constraint, IntervalConstraint) and isinstance(constraint.low, ParamDependentBound):
        constraint.low = estimate_value_range(ir, node, dist.args[constraint.low.param], assumptions).low
    if isinstance(constraint, IntervalConstraint) and isinstance(constraint.high, ParamDependentBound):
        constraint.high = estimate_value_range(ir, node, dist.args[constraint.high.param], assumptions).high
    interval = to_interval(constraint)
    if interval is None:
        return None
    # assert interval is not None, f"No interval for {constraint}"

    name = node.symbolic_name()
    var = z3.Real(name) # z3.Int(name) if properties.is_discrete() else z3.Real(name)

    if float('-inf') < interval.low and interval.high < float('inf'):
        dc = z3.And(interval.low <= var, var <= interval.high)
    elif interval.high < float('inf'):
        dc = var <= interval.high
    elif float('-inf') < interval.low:
        dc = interval.low <= var
    else:
        dc = True

    return dc

@dataclass
class AbsoluteContinuityViolation:
    counterexample: z3.ModelRef
    guide: CFG
    
    def __str__(self) -> str:
        return f"AbsoluteContinuityViolation: Density of P greater than 0 does not imply density of Q greater than 0 (Counterexample: {self.counterexample})"
    
    def get_diagnostic_ranges(self) -> list[tuple[int,int]]:
        location = self.guide.get_source_location()
        return [(location.first_byte, location.last_byte)]

# checks if P << Q
def check_ac(ir: PPL_IR, P_sample_nodes: List[SampleNode], Q_sample_nodes: List[SampleNode]) -> Optional[z3.ModelRef]:
    P_assumptions: Dict[AbstractAssignNode,SymbolicExpression] = {node: Symbol(node.symbolic_name()) for node in P_sample_nodes}
    Q_assumptions: Dict[AbstractAssignNode,SymbolicExpression] = {node: Symbol(node.symbolic_name()) for node in Q_sample_nodes}

    P_pc = {node: get_path_condition(ir, node, P_assumptions) for node in P_sample_nodes}
    Q_pc = {node: get_path_condition(ir, node, Q_assumptions) for node in Q_sample_nodes}
    path_condition = symexpr_to_z3(P_pc | Q_pc)

    distribution_constraint = {node: get_distribution_constraint(ir, node) for node in P_sample_nodes + Q_sample_nodes}
    # print("Assumptions:")
    # pprint(assumptions)
    # print("Path conditions:")
    # pprint(path_condition)
    # print("Distribution constraints")
    # pprint(distribution_constraint)


    solver = z3.Solver()
    impl = z3.Implies(
        z3.And([z3.Implies(path_condition[node],distribution_constraint[node]) for node in P_sample_nodes if distribution_constraint[node] is not None]),
        z3.And([z3.Implies(path_condition[node],distribution_constraint[node]) for node in Q_sample_nodes if distribution_constraint[node] is not None]),
    )
    # print("Implication")
    # print(impl)
    # print("Simplified Implication")
    # print(z3.simplify(impl))
    solver.add(z3.Not(impl))
    res = solver.check()
    if res == z3.sat:
        return solver.model()
    else:
        return None
    
def check_ac_guide(ir: PPL_IR) -> Optional[AbsoluteContinuityViolation]:
    model = ir.get_model()
    assert model is not None
    guide = ir.get_guide()
    assert guide is not None
    
    sample_nodes = ir.get_sample_nodes()

    model_sample_nodes = [n for n in sample_nodes if model.contains(n)]
    guide_sample_nodes = [n for n in sample_nodes if guide.contains(n)]
    
    m = check_ac(ir, guide_sample_nodes,  model_sample_nodes)
    if m is not None:
        return AbsoluteContinuityViolation(m, guide)
    else:
        return None
