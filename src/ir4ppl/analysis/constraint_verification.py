from ir4ppl.ir import * 
from analysis.distribution_properties import get_distribution_properties, to_interval, ParamDependentBound, IntervalConstraint
from dataclasses import dataclass

@dataclass
class ConstraintViolation:
    node: SampleNode | FactorNode
    param_name: str
    param_expr: Expression
    constraint: IntervalConstraint
    estimated_range: Interval
    distribution: Distribution

    def __repr__(self) -> str:
        s = f"Possible constraint violation in \"{self.node.get_source_location().source_text}\":\n"
        dist_name = self.distribution.name
        s += f"    Parameter {self.param_name} of {dist_name} distribution has constraint {self.constraint}, but values are estimated to be in {self.estimated_range}."
        return s
    
    def get_diagnostic_ranges(self) -> list[tuple[int,int]]:
        location = self.param_expr.get_source_location()
        return [(location.first_byte, location.last_byte)]

def verify_constraints(program_ir: PPL_IR) -> tuple[list[ConstraintViolation],bool]:
    can_be_analyzed = True
    for node in program_ir.get_sample_nodes() + program_ir.get_factor_nodes():
        try:
            distribution = node.get_distribution()
        except:
            continue
        if distribution.name.startswith("Unknown"):
            can_be_analyzed = False
        else:
            properties = get_distribution_properties(distribution.name)
            if properties is not None:
                if not isinstance(properties.support, IntervalConstraint) or not all(isinstance(constraint, IntervalConstraint) for _, constraint in properties.param_constraints.items()):
                    can_be_analyzed = False
            else:
                can_be_analyzed = False
    
    if not can_be_analyzed:
        return [], False
    
    assumptions : Dict[AbstractAssignNode,Interval] = dict()

    for node in program_ir.get_sample_nodes():
        dist = node.get_distribution()
        # print(node, dist)
        properties = get_distribution_properties(dist.name)
        assert properties is not None
        constraint = properties.support
        if isinstance(constraint, IntervalConstraint) and isinstance(constraint.low, ParamDependentBound):
            constraint.low = estimate_value_range(program_ir, node, dist.args[constraint.low.param], assumptions).low
        if isinstance(constraint, IntervalConstraint) and isinstance(constraint.high, ParamDependentBound):
            constraint.high = estimate_value_range(program_ir, node, dist.args[constraint.high.param], assumptions).high
        interval = to_interval(constraint)
        if interval is not None:
            assumptions[node] = interval

    violations = []
    for node in program_ir.get_sample_nodes() + program_ir.get_factor_nodes():
        try:
            dist = node.get_distribution()
        except:
            continue
        # dist = node.get_distribution()        
        properties = get_distribution_properties(dist.name)
        assert properties is not None
        for param_name, param_expr in dist.args.items():
            param_interval = estimate_value_range(program_ir, node, param_expr, assumptions)
            assert param_name in properties.param_constraints, f"Cannot find constraints for {param_name} in {properties}"
            param_constraints = properties.param_constraints[param_name]
            assert isinstance(param_constraints, IntervalConstraint), f"Param constraints {param_constraints} are not IntervalConstraint"
            if param_interval.low < param_constraints.low or param_constraints.high < param_interval.high:
                violations.append(ConstraintViolation(node, param_name, param_expr, param_constraints, param_interval, dist))

    return violations, True