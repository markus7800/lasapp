
class SymbolicExpression:
    pass

class SymOperation(SymbolicExpression):
    def __init__(self, op, *args) -> None:
        self.op = op
        self.args = args
    def __repr__(self) -> str:
        # if len(self.args) == 1:
        #     return f"{self.op}{self.args[0]}"
        # if len(self.args) == 2:
        #     return f"({self.args[0]} {self.op} {self.args[1]})"
        s = ", ".join([str(arg) for arg in self.args])
        return f"{self.op}({s})"
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SymOperation):
            return False
        return (self.op == other.op and 
                len(self.args) == len(other.args) and 
                all(a == b for (a,b) in zip(self.args, other.args))
                )
def SymNot(sexpr: SymbolicExpression):
    if isinstance(sexpr, SymOperation):
        if sexpr.op == "!":
            return sexpr.args[0]
    return SymOperation("!", sexpr)

class Symbol(SymbolicExpression):
    def __init__(self, name, type="Real") -> None:
        self.name = name
        self.type = type
    def __repr__(self) -> str:
        return self.name
        # return f"{self.type}({self.name})"
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Symbol):
            return False
        return self.name == other.name and self.type == other.type

# s = Type(Name)
def Symbol_from_str(s: str) -> Symbol:
    t, _, n = s[:-1].partition("(")
    return Symbol(n, t)
    
class SymConstant(SymbolicExpression):
    def __init__(self, value) -> None:
        if value == None:
            value = 0 # we do not model None
        self.value = value
    def __repr__(self) -> str:
        return f"{self.value}"
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SymConstant):
            return False
        return self.value == other.value
    
def path_condition_to_str(expr: SymbolicExpression):
    if isinstance(expr, SymConstant):
        return f"SymConstant({expr.value})"
    elif isinstance(expr, Symbol):
        return f"{expr.type}({expr.name})"
    else:
        assert isinstance(expr, SymOperation)
        s = ",".join([path_condition_to_str(arg) for arg in expr.args])
        return f"{expr.op}({s})"
