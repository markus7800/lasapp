from copy import copy
from ir4ppl.cfg import *
from stan.syntaxnode import StanSyntaxNode
from ir4ppl.base_cfg import AbstractCFGBuilder
from .node_finder import NodeVisitor, NodeFinder
from .syntaxnode import *
from ir4ppl.ir import PPL_IR
from typing import Any, List
from .unparser import unparse, hide_loc_data
from analysis.interval_arithmetic import *
from typing import Callable
from functools import reduce

class StanVariable(Variable):
    def __init__(self, syntaxnode: StanSyntaxNode) -> None:
        super().__init__()
        self.syntaxnode = syntaxnode
        match syntaxnode.sexpr:
            case ['Variable', [['name', name], ['id_loc', idloc]]]:
                self.name = name # not scope aware
            case _:
                raise Exception(f"Unkown Stan variable {(syntaxnode.sexpr)}")

    def is_indexed_variable(self) -> bool:
        return self.syntaxnode.parent is not None and self.syntaxnode.parent.head == "Indexed"
    
    def __hash__(self) -> int:
        return hash(self.syntaxnode)
    def __eq__(self, value: object) -> bool:
        if isinstance(value, StanVariable):
            return self.syntaxnode == value.syntaxnode
        return False
    def __repr__(self) -> str:
        return f"StanVariable({self.name})"

def match_lval_and_collect_indices(sexpr, indices: list):
    match sexpr:
        case [['lval', lval], ['lmeta', lmeta]]:
            return match_lval_and_collect_indices(lval, indices)
        case ['LVariable', [['name', name], ['id_loc', idloc]]]:
            return name
        case ['LIndexed', lval, [*index]]:
            for ix in index:
                indices.append(ix)
            return match_lval_and_collect_indices(lval, indices)
        case _:
            raise Exception(f"Unknown lval: {hide_loc_data(sexpr)}")
        
def match_arg_and_collect_indices(sexpr, indices: list):
    match sexpr:
        case [['expr', expr, ['emeta', emeta]]]:
            return match_arg_and_collect_indices(expr, indices)
        case ['Variable', [['name', name], ['id_loc', idloc]]]:
            return name
        case ['Indexed', expr, [*index]]:
            for ix in index:
                indices.append(ix)
            return match_arg_and_collect_indices(expr, indices)
        case _:
            raise Exception(f"Unknown arg: {hide_loc_data(sexpr)}")

class StanAssignTarget(AssignTarget):
    def __init__(self, syntaxnode: StanSyntaxNode, sexpr_to_node: Dict[int,StanSyntaxNode]) -> None:
        super().__init__()
        self.syntaxnode = syntaxnode
        self.is_indexed = False
        self.index: Optional[List[StanSyntaxNode]] = None
        self.sexpr_to_node = sexpr_to_node

        match syntaxnode.sexpr:
            # VarDecl
            case ['variables', [[['identifier', [['name', name], ['id_loc', idloc]]], *_]]]:
                self.name = name
            # lhs ~ ...
            case ['arg', expr]:
                indices = list()
                self.name = match_arg_and_collect_indices(expr, indices)
                if len(indices) > 0:
                    self.is_indexed = True
                    self.index = [sexpr_to_node[id(ix)] for ix in indices if isinstance(ix, list)] # index == 'All' is not sexpr
                else:
                    self.is_indexed = False
            # For
            case ['loop_variable', [['name', name], ['id_loc', idloc]]]:
                self.name = name
            # Assign lhs = ...
            case ['assign_lhs', ['LValue', lval]]:
                indices = list()
                self.name = match_lval_and_collect_indices(lval, indices)
                if len(indices) > 0:
                    self.is_indexed = True
                    self.index = [sexpr_to_node[id(ix)] for ix in indices if isinstance(ix, list)] # index == 'All' is not sexpr
                else:
                    self.is_indexed = False
            # Function parameter
            case ['AutoDiffable' | 'DataOnly', _, [['name', name], ['id_loc', idloc]]]:
                self.name = name
            case _:
                raise Exception(f"Unkown Stan assign target: {hide_loc_data(syntaxnode.sexpr)}")
            
        if isinstance(self.name, bool):
            pprint(self.syntaxnode.sexpr)
        
    
    def is_equal(self, variable: Variable) -> bool:
        assert isinstance(variable, StanVariable)
        return self.name == variable.name
    
    def is_indexed_target(self) -> bool:
        return self.is_indexed
    
    def index_is_equal(self, variable: Variable) -> bool:
        # TODO
        # would have to modify here to check if indexes are the same
        # this can identifiy that for the program X[1] = a; b = X[1]; it holds that b = a;
        # (this would be needed if we unroll loops for example)
        return False

    def get_index_expr(self) -> Expression:
        if self.index is None:
            return EmptyStanExpression()
        return StanExpression(self.index, self.sexpr_to_node)
    
    def __repr__(self) -> str:
        return str(self.name)
    

STAN_OP_TO_FUNC: Dict[str, Callable] = {
    "Plus": interval_add,
    "EltPlus": interval_add,
    "Minus": interval_sub,
    "EltMinus": interval_sub,
    "Times": interval_mul,
    "EltTimes": interval_mul,
    "Divide": interval_div,
    "IntDivide": interval_div,
    "EltDivide": interval_div,
    "PMinus": interval_usub,
    "Equals": interval_eq,
    "sqrt": interval_sqrt,
    "square": interval_square,
    "abs": interval_abs,
    "Pow": interval_pow,
    "pow": interval_pow,
    "exp": interval_exp,
    "log": interval_log,
    "inv_logit": interval_invlogit,
    "inv_cloglog": StaticRangeOp(Interval(0,1)),
    "logit": interval_real,
    "min": interval_minimum,
    "max": interval_maximum,
    "fmin": interval_minimum,
    "fmax": interval_maximum,
    "asin": StaticRangeOp(Interval(-math.pi/2, math.pi/2)),
    "Phi": StaticRangeOp(Interval(0,1)), # standard normal cumulative distribution function
    "to_vector": interval_no_op,
    "to_matrix": interval_no_op,
    "Transpose": interval_no_op,
    "transpose": interval_no_op,
    "col": interval_no_op, # selecting column of matrix
    "row": interval_no_op, # selecting row of matrix
    "rep_array": lambda x, _: x,
    "append_array": interval_union,
    "dims": StaticRangeOp(Interval(0, float('inf'))),
    "int_step": StaticRangeOp(Interval(0,1)),
    "fma": lambda x, y, z: interval_add(interval_mul(x,y),z), # fused multiply add
    "pi": StaticRangeOp(Interval(math.pi, math.pi)),

    "mean": interval_no_op,
    "sd": interval_pos,

    # no need to specify:
    'cholesky_decompose': interval_real,
    'L_cov_exp_quad_ARD': interval_real,
    'gp_exp_quad_cov': interval_real,
    'integrate_ode_rk45': interval_real,
    'integrate_ode_bdf': interval_real,
    'ode_bdf_tol': interval_real,
    'ode_rk45_tol': interval_real,

    # user defined functions
    # /Users/markus/Documents/stan-example-models/knitr/soil-carbon/soil_incubation.stan
    'evolved_CO2': interval_real,
    # /Users/markus/Documents/stan-example-models/BPA/Ch.07/cjs_group_raneff.stan
    'first_capture': interval_real,
    'last_capture': interval_real,
    'prob_uncaptured': interval_real,
    # /Users/markus/Documents/stan-example-models/BPA/Ch.08/mr_ss.stan
    'cell_prob': interval_real,
}

class StanExpression(Expression):
    def __init__(self, syntaxnodes: List[StanSyntaxNode], sexpr_to_node: Dict[int,StanSyntaxNode]) -> None:
        super().__init__()
        for syntaxnode in syntaxnodes:
            assert isinstance(syntaxnode, StanSyntaxNode)
        self.syntaxnodes = syntaxnodes
        self.sexpr_to_node = sexpr_to_node

    def __eq__(self, value: object) -> bool:
        if isinstance(value, StanExpression):
            return self.syntaxnodes == value.syntaxnodes
        else:
            return False
    def __hash__(self) -> int:
        return hash(self.syntaxnodes[0])
    
    def get_source_location(self) -> SourceLocation:
        first_byte = min(syntaxnode.position for syntaxnode in self.syntaxnodes)
        last_byte = max(syntaxnode.end_position for syntaxnode in self.syntaxnodes)
        return SourceLocation(self.syntaxnodes[0].source[first_byte:last_byte], first_byte, last_byte)

    def get_free_variables(self) -> List[Variable]:
        def is_variable(syntaxnode: StanSyntaxNode) -> bool:
            match syntaxnode.sexpr:
                # would have to modify here to also return variable names for user-defined functions
                case ['Variable', *_]:
                    return True
                case _:
                    return False
        name_finder = NodeFinder(
            is_variable,
            lambda node: StanVariable(node))
        for syntaxnode in self.syntaxnodes:
            name_finder.visit(syntaxnode)
        return name_finder.result
    
    def get_function_calls(self, fdef: FunctionDefinition) -> List[FunctionCall]:
        assert isinstance(fdef, StanFunctionDefinition)
        def is_function_call(syntaxnode: StanSyntaxNode) -> bool:
            match syntaxnode.sexpr:
                case ['FunApp' | 'CondDistApp' | 'NRFunApp', _, [['name', name], ['id_loc', _]], args]:
                    return fdef.name == name or fdef.name == name + "_lpdf" or fdef.name == name + "_lpmf"
                case _:
                    return False
            
        call_finder = NodeFinder(
            is_function_call,
            lambda node: StanFunctionCall([node], self.sexpr_to_node))
        for syntaxnode in self.syntaxnodes:
            call_finder.visit(syntaxnode)
        return call_finder.result
    
    def _estimate_value_range_rec(self, sexpr, variable_mask: Dict[Variable,Interval], tab="") -> Interval:
        # print(tab, "    _estimate_value_range_rec", hide_loc_data(sexpr))
        match sexpr:
            case ['VarDecl', ['decl_type', type], ['transformation', trafo], _, variable]:
                interval = self._estimate_value_range_rec(variable, variable_mask, tab=tab+"  ")
            case ['Variable', *_]:
                interval = variable_mask[StanVariable(self.sexpr_to_node[id(sexpr)])]
            case ['Indexed', expr, index]:
                # get variable, estimate all elements with same interval
                interval = self._estimate_value_range_rec(expr, variable_mask, tab=tab+"  ")
            case ['expr', expr, *_]:
                interval = self._estimate_value_range_rec(expr, variable_mask, tab=tab+"  ")
            case ['assign_rhs', expr, *_]:
                interval = self._estimate_value_range_rec(expr, variable_mask, tab=tab+"  ")
            case ['IntNumeral' | 'RealNumeral', value]:
                interval =  Interval(float(value))
            case ['BinOp', arg1, op, arg2]:
                interval = STAN_OP_TO_FUNC[op](self._estimate_value_range_rec(arg1, variable_mask, tab=tab+"  "), self._estimate_value_range_rec(arg2, variable_mask, tab=tab+"  "))
            case ['PrefixOp', op, arg]:
                interval = STAN_OP_TO_FUNC[op](self._estimate_value_range_rec(arg, variable_mask, tab=tab+"  "))
            case ['PostfixOp', arg, op]:
                interval = STAN_OP_TO_FUNC[op](self._estimate_value_range_rec(arg, variable_mask, tab=tab+"  "))
            case ['CondDistApp', [], [['name', name], _], [arg, *args]]:
                interval = Interval(float('-inf'),0)
            case ['FunApp' | 'NRFunApp', [], [['name', name], _], [*args]]:
                # if we want to mask functions we have to look up naeme in variable_mask here
                interval = STAN_OP_TO_FUNC[name](*[self._estimate_value_range_rec(arg, variable_mask, tab=tab+" ") for arg in args])
            case ['Paren', expr]:
                interval = self._estimate_value_range_rec(expr, variable_mask, tab=tab+"  ") 
            case ['RowVectorExpr' | 'ArrayExpr', [*args]]:
                intervals = [self._estimate_value_range_rec(arg, variable_mask, tab=tab+"  ") for arg in args]
                interval = reduce(interval_union, intervals) if len(intervals) > 0 else Interval(float('-inf'),float('inf'))
            case ['TernaryIf', test, then, orelse]:
                interval = interval_union(self._estimate_value_range_rec(then, variable_mask, tab=tab+"  "), self._estimate_value_range_rec(orelse, variable_mask, tab=tab+"  "))
            case _:
                raise Exception(f"Unknown sexpr {hide_loc_data(sexpr)}")
        # print(tab, "    ->", interval)
        return interval
            
    def estimate_value_range(self, variable_mask: Dict[Variable,Interval]) -> Interval:
        # print("    estimate_value_range", variable_mask)
        if len(self.syntaxnodes) > 1:
            assert self.syntaxnodes[0].head == "lower_bound" and self.syntaxnodes[1].head == "upper_bound" # LoopIterNode
            low = self._estimate_value_range_rec(self.syntaxnodes[0][0].sexpr, variable_mask)
            up = self._estimate_value_range_rec(self.syntaxnodes[1][0].sexpr, variable_mask)
            return Interval(low.low, up.high)
        assert len(self.syntaxnodes) == 1, f"Cannot estimate value range for expression with multiple nodes {self.syntaxnodes}"
        return self._estimate_value_range_rec(self.syntaxnodes[0].sexpr, variable_mask)


    def __repr__(self) -> str:
        return "".join([unparse(syntaxnode.sexpr) for syntaxnode in self.syntaxnodes])
    
    
class StanFunctionCall(StanExpression, FunctionCall):
    def __init__(self, syntaxnodes: List[StanSyntaxNode], sexpr_to_node: Dict[int,StanSyntaxNode]) -> None:
        super().__init__(syntaxnodes, sexpr_to_node)
    def get_expr_for_func_arg(self, node: FuncArgNode) -> Expression:
        match self.syntaxnodes[0].sexpr:
            case ['FunApp' | 'CondDistApp' | 'NRFunApp', _, [['name', _], ['id_loc', _]], args]:
                # print(args)
                args_syntaxnode = self.syntaxnodes[0][1] # FIXME
                assert args_syntaxnode.sexpr == args
                return StanExpression([args_syntaxnode[node.index]], self.sexpr_to_node)
            case _:
                raise Exception(f"Unknown function fall {hide_loc_data(self.syntaxnodes[0].sexpr)}")
        

    
class EmptyStanExpression(StanExpression):
    def __init__(self) -> None:
        pass
    def __eq__(self, value: object) -> bool:
        return isinstance(value, EmptyStanExpression)
    def __hash__(self) -> int:
        return 0
    def get_free_variables(self) -> List[Variable]:
        return list()
    def get_function_calls(self, fdef: FunctionDefinition) -> List[FunctionCall]:
        return list()
    def estimate_value_range(self, variable_mask: Dict[Variable,Interval]) -> Interval:
        return Interval(float('-inf'),float('inf'))
    def __repr__(self) -> str:
        return "<>"
    
class VarDeclStanExpression(StanExpression):
    def __init__(self, range: Optional[Interval]) -> None:
        self.range = range
    def __eq__(self, value: object) -> bool:
        if isinstance(value, VarDeclStanExpression):
            return self.range == value.range
        return False
    def __hash__(self) -> int:
        return hash(self.range)
    def get_free_variables(self) -> List[Variable]:
        return list()
    def get_function_calls(self, fdef: FunctionDefinition) -> List[FunctionCall]:
        return list()
    def estimate_value_range(self, variable_mask: Dict[Variable,Interval]) -> Interval:
        if self.range is not None:
            return self.range
        return Interval(float('-inf'),float('inf'))
    def __repr__(self) -> str:
        return f"<{self.range}>"
    
def get_only_elem(s: Set[CFGNode]) -> CFGNode:
    assert len(s) == 1
    return list(s)[0]

class StanFunctionDefinition(FunctionDefinition):
    def __init__(self, syntaxnode: StanSyntaxNode, name: str | None = None) -> None:
        super().__init__()
        self.syntaxnode = syntaxnode
        self.name: str = ""
        if name is None:
            match syntaxnode.sexpr:
                case ['FunDef', _, ['funname', [['name', funname], _]], *_]:
                    self.name = funname
                case _:
                    raise Exception(f"Cannot find name for func: {hide_loc_data(syntaxnode.sexpr)}")
        else:
            self.name = name # not scope aware

    def is_equal(self, variable: Variable) -> bool:
        assert isinstance(variable, StanVariable)
        return self.name == variable.name
        
    def __repr__(self) -> str:
        return f"StanFunctionDefinition({self.name})"

class StanSampleNode(SampleNode):
    def __init__(self, id: str, target: AssignTarget, value: Expression, syntaxnode: StanSyntaxNode, sexpr_to_node: Dict[int,StanSyntaxNode]) -> None:
        super().__init__(id, target, value)
        self.syntaxnode = syntaxnode
        self.sexpr_to_node = sexpr_to_node
    def get_distribution_expr(self) -> Expression:
        value_expr = self.get_value_expr()
        return value_expr
    
    def get_address_expr(self) -> Expression:
        # target = self.get_target()
        # assert isinstance(target, StanAssignTarget)
        # return StanExpression([target.syntaxnode])
        return EmptyStanExpression() # no address expr
    
    def get_distribution(self) -> Distribution:
        # this class is only usede for the parameter block if we unsugar tilde
        if isinstance(self.get_address_expr(), EmptyStanExpression):
            match self.syntaxnode.sexpr:
                case ['stmt', ['VarDecl', ['decl_type', type], ['transformation', trafo], *_], *_]:
                    match trafo:
                        case 'Identity' | ['OffsetMultiplier' | 'Multiplier' | 'Offset', *_]:
                            return Distribution("ImproperUniform", {})
                        case 'Correlation' | 'Covariance' | 'CholeskyCorr' | 'Simplex' | 'Ordered' | 'PositiveOrdered':
                            return Distribution(f"Improper{trafo}", {})
                        case ['Lower', low]:
                            return Distribution("ImproperUniformRO", {'lower': StanExpression([self.sexpr_to_node[id(low)]], self.sexpr_to_node)})
                        case ['Upper', up]:
                            return Distribution("ImproperUniformLO", {'upper': StanExpression([self.sexpr_to_node[id(up)]], self.sexpr_to_node)})
                        case ['LowerUpper', low, up]:
                            return Distribution("Uniform", {'a': StanExpression([self.sexpr_to_node[id(low)]], self.sexpr_to_node), 'b': StanExpression([self.sexpr_to_node[id(up)]], self.sexpr_to_node)})
            raise Exception(f"Unkown parameter sexpr: {hide_loc_data(self.syntaxnode.sexpr)}")
        else:
            raise NotImplementedError
        
    def get_source_location(self) -> SourceLocation:
        return SourceLocation(self.syntaxnode.sourcetext(), self.syntaxnode.position, self.syntaxnode.end_position)
    
class StanFactorNode(FactorNode):
    def __init__(self, id: str, factor_expression: Expression, syntaxnode: StanSyntaxNode, sexpr_to_node: Dict[int,StanSyntaxNode]) -> None:
        super().__init__(id, factor_expression)
        self.syntaxnode = syntaxnode
        self.sexpr_to_node = sexpr_to_node
    def get_source_location(self) -> SourceLocation:
        return SourceLocation(self.syntaxnode.sourcetext(), self.syntaxnode.position, self.syntaxnode.position)
    def get_distribution(self) -> Distribution:
        match self.syntaxnode.sexpr:
            case ['stmt', ['TargetPE', ['expr', ['CondDistApp', [], [['name', name], _], [_, *args]], _]], *_]:
                distname = ""
                distparams = []
                match name[:-5]: # suffixes _lpdf, _lpmf
                    # Unbounded Continuous Distributions
                    case 'normal':
                        distparams = ['location', 'scale']
                        distname = 'Normal'
                    case 'std_normal':
                        distparams = []
                        distname = 'Normal'
                    case 'normal_id_glm':
                        distparams = ['data', 'slope', 'intercept', 'sigma']
                        distname = 'NormalGLM'
                    case 'exp_mod_normal':
                        pass
                    case 'skew_normal':
                        pass
                    case 'student_t':
                        distparams = ['df', 'location', 'scale']
                        distname = 'StudentT'
                    case 'cauchy':
                        distparams = ['location', 'scale']
                        distname = 'Cauchy'
                    case 'double_exponential':
                        distparams = ['location', 'scale']
                        distname = 'Laplace'
                    case 'logistic':
                        distparams = ['location', 'scale']
                        distname = 'Logistic'
                    case 'gumbel':
                        pass
                    case 'skew_double_exponential':
                        pass
                    # Positive Continuous Distributions
                    case 'lognormal':
                        distparams = ['location', 'scale']
                        distname = 'LogNormal'
                    case 'chi_square':
                        distparams = ['df']
                        distname = 'ChiSquare'
                    case 'inv_chi_square':
                        pass
                    case 'scaled_inv_chi_square':
                        pass
                    case 'exponential':
                        distparams = ['scale']
                        distname = 'Exponential'
                    case 'gamma':
                        distparams = ['shape', 'rate']
                        distname = 'Gamma'
                    case 'inv_gamma':
                        distparams = ['shape', 'rate']
                        distname = 'InverseGamma'
                    case 'weibull':
                        pass
                    case 'frechet':
                        pass
                    case 'rayleigh':
                        pass
                    case 'loglogistic':
                        pass
                    # Positive Lower-Bounded Distributions
                    case 'pareto':
                        pass
                    case 'pareto_type_2':
                        pass
                    case 'wiener':
                        pass
                    # Continuous Distributions on [0, 1]
                    case 'beta':
                        distparams = ['alpha', 'beta']
                        distname = 'Beta'
                    case 'beta_proportion':
                        pass
                    # Circular Distributions
                    case 'von_mises':
                        pass
                    # Bounded Continuous Distributions
                    case 'uniform':
                        distparams = ['a', 'b']
                        distname = 'Uniform'
                    # Multivariate normal distribution
                    case 'multi_normal':
                        distparams = ['location', 'covariance']
                        distname = 'MultivariateNormal'
                    case 'multi_normal_prec':
                        distparams = ['location', 'precision']
                        distname = 'MultivariateNormal'
                    case 'multi_normal_cholesky':
                        pass
                    case 'multi_gp':
                        pass
                    case 'multi_gp_cholesky':
                        pass
                    case 'multi_student_t':
                        pass
                    case 'multi_student_t_cholesky':
                        pass
                    case 'gaussian_dlm_obs':
                        pass
                    # Simplex Distributions
                    case 'dirichlet':
                        distparams = ['alpha']
                        distname = 'Dirichlet'
                    # Correlation Matrix Distributions
                    case 'lkj_corr':
                        pass
                    case 'lkj_corr_cholesky':
                        pass
                    # Covariance Matrix Distributions
                    case 'wishart':
                        pass
                    case 'wishart_cholesky':
                        pass
                    case 'inv_wishart':
                        pass
                    case 'inv_wishart_cholesky':
                        pass
                    # Binary Distributions
                    case 'bernoulli':
                        distparams = ['p']
                        distname = 'Bernoulli'
                    case 'bernoulli_logit':
                        pass
                    case 'bernoulli_logit_glm':
                        pass
                    # Bounded Discrete Distributions
                    case 'binomial':
                        distparams = ['n', 'p']
                        distname = 'Binomial'
                    case 'binomial_logit':
                        pass
                    case 'binomial_logit_glm':
                        pass
                    case 'beta_binomial':
                        pass
                    case 'hypergeometric':
                        pass
                    case 'categorical':
                        distparams = ['p']
                        distname = 'Categorical'
                    case 'categorical_logit':
                        pass
                    case 'categorical_logit_glm':
                        pass
                    case 'discrete_range':
                        distparams = ['a', 'b']
                        distname = 'DiscreteUniform'
                    case 'ordered_logistic':
                        pass
                    case 'ordered_logistic_glm':
                        pass
                    case 'ordered_probit':
                        pass
                    # Unbounded Discrete Distributions
                    case 'neg_binomial':
                        pass
                    case 'neg_binomial_2':
                        pass
                    case 'neg_binomial_2_log':
                        pass
                    case 'neg_binomial_2_log_glm':
                        pass
                    case 'poisson':
                        distparams = ['rate']
                        distname = 'Poisson'
                    case 'poisson_log':
                        pass
                    case 'poisson_log_glm':
                        pass
                    # Multivariate Discrete Distributions
                    case 'multinomial':
                        distparams = ['p']
                        distname = 'Multinomial'
                    case 'multinomial_logit':
                        pass
                    case 'dirichlet_multinomial':
                        pass
                    case _:
                        print(f"Warning: Unknown distribution name: {name}") # has to be defined as function
            
                # print(distname, distparams, hide_loc_data(args))
                if distname != "" and len(args) == len(distparams):
                    return Distribution(distname, {argname: StanExpression([self.sexpr_to_node[id(expr)]], self.sexpr_to_node) for argname, expr in zip(distparams, args)})
                else:
                    return Distribution(f"Unknown", {})
        raise Exception(f"Unkown distribution sexpr: {hide_loc_data(self.syntaxnode.sexpr)}")

from pprint import pprint
class StanCFGBuilder(AbstractCFGBuilder):
    def __init__(self, node_to_id: Dict[StanSyntaxNode,str], sexpr_to_node: Dict[int,StanSyntaxNode]) -> None:
        self.node_to_id = node_to_id
        self.sexpr_to_node = sexpr_to_node
        self.cfgs: Dict[FunctionDefinition,CFG] = dict() # toplevel -> CFG, functiondef -> CFG

    def get_cfg(self, node: StanSyntaxNode, breaknode:Optional[JoinNode], continuenode:Optional[JoinNode], returnnode:Optional[JoinNode]) -> CFG: # type:ignore
        node_id = self.node_to_id[node]

        startnode = StartNode(node_id)
        nodes: Set[CFGNode] = set()
        endnode = EndNode(node_id)

        # node.pprint()
        # pprint(node.sexpr)
        # print(node)

        if node.head in ("functionblock", "datablock", "transformeddatablock", "parametersblock", "transformedparametersblock", "modelblock"):
            if len(node.children) > 0:
                return self.get_cfg(node[0], breaknode, continuenode, returnnode)
            else:
                self.build_empty_cfg(startnode, nodes, endnode, node)
        elif node.head in ("generatedquantitiesblock", "comments"):
            self.build_empty_cfg(startnode, nodes, endnode, node)
        elif node.head == "block":
            self.build_block_cfg(startnode, nodes, endnode, node.children, breaknode, continuenode, returnnode)
        elif node.head == "stmt":
            return self.get_cfg(node[0], breaknode, continuenode, returnnode)
        elif node.head == "FunDef":
            function_cfg = self.get_function_cfg(node)
            self.cfgs[StanFunctionDefinition(node)] = function_cfg
            self.build_empty_cfg(startnode, nodes, endnode, node)
        elif node.head == "VarDecl":
            assert node[3].head == "variables"

            is_parameter = False
            is_data = False
            parent_node = node.parent
            while parent_node is not None:
                if parent_node.head == "parametersblock":
                    is_parameter = True
                    break
                if parent_node.head == "datablock":
                    is_data = True
                    break
                parent_node = parent_node.parent
            if is_parameter:
                assert node.parent is not None and node.parent.head == "stmt"
                cfgnode = StanSampleNode(node_id, StanAssignTarget(node[3],self.sexpr_to_node), EmptyStanExpression(), node.parent, self.sexpr_to_node)
            else:
                range = None
                match node.sexpr:
                    case ['VarDecl', ['decl_type', _], ['transformation', trafo], _, ['variables', [[_, ['initial_value', value]]]]]:
                        if value != []:
                            assert len(value) == 1
                            # constrain (non-data) variable with initial value
                            cfgnode = AssignNode(node_id, StanAssignTarget(node[3],self.sexpr_to_node), StanExpression([self.sexpr_to_node[id(value[0])]], self.sexpr_to_node))
                        elif is_data:
                            match trafo:
                                case 'Identity' | ['OffsetMultiplier' | 'Multiplier' | 'Offset', *_]:
                                    range = Interval(float('-inf'),float('inf'))
                                case 'Correlation' | 'Covariance' | 'CholeskyCorr' | 'Simplex' | 'Ordered' | 'PositiveOrdered':
                                    range = None
                                case ['Lower', ['expr', ['IntNumeral' | 'RealNumeral', low], _]]:
                                    range = Interval(low,float('inf'))
                                case ['Upper', ['expr', ['IntNumeral' | 'RealNumeral', up], _]]:
                                    range = Interval(float('-inf'),up)
                                case ['LowerUpper', ['expr', ['IntNumeral' | 'RealNumeral', low], _], ['expr', ['IntNumeral' | 'RealNumeral', up], _]]:
                                    range = Interval(low,up)
                                case _:
                                    range = None
                                    # print("Warning: Unknown transformation: {hide_loc_data(trafo)}")
                                    # raise Exception(f"Unknown transformation: {hide_loc_data(trafo)}")
                             # we constrain data variable
                            cfgnode = AssignNode(node_id, StanAssignTarget(node[3],self.sexpr_to_node), VarDeclStanExpression(range))
                        else:
                            # we do not constrain non-data variable without initial value and we do not consider it an assignment
                            cfgnode = SkipNode(node_id)
                            # cfgnode = AssignNode(node_id, StanAssignTarget(node[3],self.sexpr_to_node), EmptyStanExpression())
                    case _:
                        raise Exception(f"Unknown vardecl: {hide_loc_data(node.sexpr)}")

                
            nodes.add(cfgnode)
            add_edge(startnode, cfgnode)
            add_edge(cfgnode, endnode)
        elif node.head == "Assignment":
            assert node[0].head == "assign_lhs"
            assert node[1].head == "assign_op"
            assert node[2].head == "assign_rhs"
            assert node[1][0].value == "Assign", hide_loc_data(node[1][0].sexpr)
            cfgnode = AssignNode(node_id, StanAssignTarget(node[0],self.sexpr_to_node), StanExpression([node[2]], self.sexpr_to_node))
            nodes.add(cfgnode)
            add_edge(startnode, cfgnode)
            add_edge(cfgnode, endnode)
        elif node.head == "Tilde":
            assert node.parent is not None and node.parent.head == "stmt"
            assert node[0].head == "arg"
            assert node[1].head == "distribution"
            assert node[2].head == "args"
            try:
                target = StanAssignTarget(node[0],self.sexpr_to_node)
                cfgnode = StanSampleNode(node_id, target, StanExpression([node[1],node[2]], self.sexpr_to_node), node.parent, self.sexpr_to_node)
            except Exception as e:
                print("Warning:", e)
                # raise e
                # TODO: verify that we have observe statement
                # e.g. 1 ~ ..., func(...) ~ (should only depend on data variables)
                cfgnode = StanFactorNode(node_id, StanExpression([node[0]], self.sexpr_to_node), node.parent, self.sexpr_to_node)

            nodes.add(cfgnode)
            add_edge(startnode, cfgnode)
            add_edge(cfgnode, endnode)
        elif node.head == "TargetPE" or node.head == "Reject":
            # target += ...
            assert node.parent is not None and node.parent.head == "stmt"
            cfgnode = StanFactorNode(node_id, StanExpression([node[0]], self.sexpr_to_node), node.parent, self.sexpr_to_node)
            nodes.add(cfgnode)
            add_edge(startnode, cfgnode)
            add_edge(cfgnode, endnode)

        elif node.head == "IfThenElse":

            test_node = node[0]
            consequent_node = node[1]
            alternative_node = node[2] if len(node.children) > 2 else None
            
            branch_cfgnode = BranchNode(node_id + "_if_start", StanExpression([test_node], self.sexpr_to_node))
            branch_join_cfgnode = JoinNode(node_id + "_if_end")
            self.build_if_cfg(startnode, nodes, endnode, branch_cfgnode, branch_join_cfgnode, consequent_node, alternative_node, breaknode, continuenode, returnnode)


        elif node.head == "For":
            loop_var = node[0]
            assert loop_var.head == "loop_variable"
            assert node[1].head == "lower_bound"
            assert node[2].head == "upper_bound"

            body = node[3]
            assert body.head == "loop_body"
            assert body.fields() == ["stmt"]
            body = body[0]
            for_start_join_cfgnode = JoinNode(node_id + "_for_start")
            for_branch_cfgnode = BranchNode(node_id + "_for_iter", StanExpression([loop_var], self.sexpr_to_node))
            for_end_join_cfgnode = JoinNode(node_id + "_for_end")

            loop_var_cfgnode = LoopIterNode(
                node_id, 
                StanAssignTarget(loop_var,self.sexpr_to_node),
                StanExpression([node[1],node[2]], self.sexpr_to_node)
            )
            self.build_for_cfg(startnode, nodes, endnode, for_start_join_cfgnode, for_branch_cfgnode, for_end_join_cfgnode, loop_var_cfgnode, body, returnnode)
        
        elif node.head == "While":
            while_start_join_cfgnode = JoinNode(node_id + "_while_start")
            while_branch_cfgnode = BranchNode(node_id + "_while_test", StanExpression([node[0]], self.sexpr_to_node))
            while_end_join_cfgnode = JoinNode(node_id + "_while_end")
            body = node[1]
            self.build_while_cfg(startnode, nodes, endnode, while_start_join_cfgnode, while_branch_cfgnode, while_end_join_cfgnode, body, returnnode)

        elif node.head in ("Print", "Return", "NRFunApp"):
            cfgnode = ExprNode(node_id, StanExpression([node], self.sexpr_to_node))
            nodes.add(cfgnode)
            add_edge(startnode, cfgnode)
            add_edge(cfgnode, endnode)
        
        else:
            pprint(hide_loc_data(node.sexpr))
            raise Exception(f"Unsupported node {node}")

        cfg = CFG(startnode, nodes, endnode)
        try:
            verify_cfg(cfg)
        except Exception:
            print_cfg_dot(cfg)
            raise

        if node.parent is None:
            # toplevel
            self.cfgs[StanFunctionDefinition(node, "__MAIN__")] = cfg

        return cfg
    
    def build_block_cfg(self, startnode: StartNode, nodes: Set[CFGNode], endnode: EndNode,
                        children: List[StanSyntaxNode],
                        breaknode: Optional[JoinNode], continuenode: Optional[JoinNode], returnnode: Optional[JoinNode]):
        # concatentate all children if they are not functions
        # S_i -> CFG_i -> E_i
        # => S -> CFG_1 -> ... CFG_n -> E
        current_node: CFGNode = startnode
        for child in children:
            child_cfg = self.get_cfg(child, breaknode, continuenode, returnnode)
            nodes.update(child_cfg.nodes)

            N1 = get_only_elem(child_cfg.startnode.children) # node after start node
            N2 = get_only_elem(child_cfg.endnode.parents)    # node before end node

            delete_edge(child_cfg.startnode, N1)
            add_edge(current_node, N1)
            delete_edge(N2, child_cfg.endnode)
            
            # parents come from sub-cfg
            current_node = N2

        add_edge(current_node, endnode)

    def get_function_cfg(self, node: StanSyntaxNode): # type: ignore
        node_id = self.node_to_id[node]
        match node.sexpr:
            case ['FunDef', ['returntype', _], ['funname', [['name', name], _]], ['arguments', *_], ['body', *_]]:
                funcarg_nodes: List[FuncArgNode] = list()
                if len(node[2].children) > 0:
                    args = node[2][0]
                    for i, arg in enumerate(args.children):
                        match arg.sexpr:
                            case ['AutoDiffable' | 'DataOnly', _, [['name', argname], ['id_loc', _]]]:
                                arg_id = self.node_to_id[arg]
                                funcarg_node = FuncArgNode(arg_id, StanAssignTarget(arg,self.sexpr_to_node), EmptyStanExpression(), argname, i)
                                funcarg_nodes.append(funcarg_node)
                            case _:
                                raise Exception(f"Unkown function argument: {hide_loc_data(arg.sexpr)}")
                            
                assert node[3].head == "body" and len(node[3].children) == 1
                func_body = node[3][0]
                cfg = self.build_function_cfg(node_id, name, func_body, funcarg_nodes)
                return cfg
            case _:
                raise Exception(f"Unkown function definition: {hide_loc_data(node.sexpr)}")
        
    
    

class NodeIdAssigner(NodeVisitor):
    def __init__(self) -> None:
        self.node_to_id: Dict[StanSyntaxNode, str] = {}
        self.id_to_node: Dict[str, StanSyntaxNode] = {}
        self.sexpr_to_node : Dict[Any, StanSyntaxNode] = {}

    def visit(self, node: StanSyntaxNode):
        i = f"node_{len(self.node_to_id) + 1}"
        self.node_to_id[node] = i
        self.id_to_node[i] = node
        self.sexpr_to_node[id(node.sexpr)] = node

        self.generic_visit(node)


import subprocess
import sexpdata
from .unsugar_tilde import preproc_unsugar_tilde

# TODO:
# check for target
# add improper priors
def get_IR_for_stan(filename: str, unsugar_tilde: bool = True, stanc="stanc"):
    line_offsets = get_line_offsets(filename)
    file_content = get_file_content(filename)

    res = subprocess.run([stanc, "--debug-ast", filename], capture_output=True)
    stan_ast = res.stdout.decode("utf-8")
    if stan_ast == "":
        err = res.stderr.decode("utf-8")
        raise Exception(f"Parsing Stan AST failed for {filename}:\n{err}")
    sexpr = sexpdata.loads(stan_ast, true=None)
    sexpr = sym_to_str(sexpr)

    if unsugar_tilde:
        sexpr = preproc_unsugar_tilde(sexpr)
    # pprint(hide_loc_data(sexpr))
    # print(unparse(sexpr))

    syntaxtree = make_stan_syntaxtree(sexpr, line_offsets, file_content)
    # print(unparse(syntaxtree.sexpr))

    node_id_assigner = NodeIdAssigner()
    node_id_assigner.visit(syntaxtree)
    node_to_id = node_id_assigner.node_to_id
    id_to_node = node_id_assigner.id_to_node
    sexpr_to_node = node_id_assigner.sexpr_to_node

    cfgbuilder = StanCFGBuilder(node_to_id, sexpr_to_node)
    cfgbuilder.get_cfg(syntaxtree, None, None, None)
    for fdef, cfg in cfgbuilder.cfgs.items():
        assert verify_cfg(cfg)
        # print_cfg_dot(cfg)
        # assert isinstance(fdef, StanFunctionDefinition)
        # plot_cfg(cfg, fdef.name)

    return PPL_IR(
        cfgbuilder.cfgs,
        model_cfg=next(
            cfg for fdef, cfg in cfgbuilder.cfgs.items()
            if isinstance(fdef, StanFunctionDefinition) and fdef.name == "__MAIN__"
        )) # no guide for stan
