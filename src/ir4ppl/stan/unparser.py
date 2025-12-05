
def hide_loc_data(sexpr):
    if isinstance(sexpr, list) and len(sexpr) > 0 and sexpr[0] in ("loc", "xloc", "id_loc"):
        return [sexpr[0], "..."]
    if isinstance(sexpr, list):
        return [hide_loc_data(child) for child in sexpr]
    else:
        return sexpr
    
block_names = {
    'functionblock': 'functions',
    'datablock': 'data',
    'transformeddatablock': 'transformed data', 'parametersblock': 'parameters', 'transformedparametersblock': 'transformed parameters', 'modelblock': 'model', 'generatedquantitiesblock': 'generated quantiles'
}
ops = {
    'Times': '*',
    'Plus': '+',
    'Minus': '-',
    'Divide': '/',
    'IntDivide': '%/%',
    'Pow': '^',
    'PMinus': '-',
    'PNot': '!',
    'Transpose': "'",
    'EltTimes': '.*',
    "EltPlus": '.+',
    "EltDivide": './',
    'Less': '<',
    'Leq': '<=',
    'Geq': '>=',
    'Greater': '>',
    'Equals': '==',
    'NEquals': '!=',
    'Or': '||',
    'And': '&&',
}
def unparse(sexpr, indent="") -> str:
    s = ""
    if isinstance(sexpr, list):
        if len(sexpr) > 0 and isinstance(sexpr[0], str):
            match sexpr:
                case ['functionblock' | 'datablock' | 'transformeddatablock' | 'parametersblock' | 'transformedparametersblock' | 'modelblock' | 'generatedquantitiesblock', *children]:
                    s += block_names[sexpr[0]] + " {\n"
                    s += "".join([unparse(child, indent + "    ") for child in children])
                    s += "}\n"
                case ['comments', *_]:
                    s = ""
                case ["stmts" | "Block", *children]:
                    s += "".join([unparse(child, indent) for child in children])
                case ['emeta' | 'smeta' | 'lmeta'| 'bmeta' | 'xloc' | 'id_loc', *_]:
                    s = ""
                case ['stmt', ['Block', block]]:
                    s = unparse(block, indent)
                case ['stmt', *children]:
                    s += indent
                    s += "".join([unparse(child, indent) for child in children])
                    s += ";\n"
                case ['VarDecl', ['decl_type', type], ['transformation', trafo], _, ['variables', [[['identifier', [['name', name], _]], ['initial_value', value]]]]]:
                    # print(hide_loc_data(sexpr))
                    match trafo:
                        case ['Lower', low]:
                            s = f"{unparse(type)}<lower={unparse(low)}> {name}"
                        case ['Upper', up]:
                            s = f"{unparse(type)}<upper={unparse(up)}> {name}"
                        case ['LowerUpper', low, up]:
                            s = f"{unparse(type)}<lower={unparse(low)},upper={unparse(up)}> {name}"
                        case ['Offset', off]:
                            s = f"{unparse(type)}<offset={unparse(off)}> {name}"
                        case ['OffsetMultiplier', off, mult]:
                            s = f"{unparse(type)}<offset={unparse(off)}, multiplier={unparse(mult)}> {name}"
                        case _:
                            s = f"{unparse(type)} {name}"
                    if value != []:
                        s += " = " + unparse(value)
                case ['arg', arg]:
                    s = unparse(arg)
                case ['args', args]:
                    s = ", ".join([unparse(arg) for arg in args])
                case ['distribution', [['name', dist], _]]:
                    s = dist
                case ['Tilde', arg, dist, args, ['truncation', truncate]]:
                    s = f"{unparse(arg)} ~ {unparse(dist)}({unparse(args)})"
                    # TODO truncate
                case ['assign_lhs' | 'assign_rhs', hs]:
                    s = unparse(hs)
                case ['Assignment', lhs, ['assign_op', 'Assign'], rhs]:
                    s = f"{unparse(lhs)} = {unparse(rhs)}"
                case ['Assignment', lhs, ['assign_op', ['OperatorAssign', op]], rhs]:
                    s = f"{unparse(lhs)} {ops[op]}= {unparse(rhs)}"
                case ['LValue', [lval, _]]:
                    s = unparse(lval)
                case ['lval', lval]:
                    s = unparse(lval)
                case ['expr', expr, *_]:
                    s = unparse(expr)
                case ['IntNumeral' | 'RealNumeral', value]:
                    s = str(value)
                case ['SVector', 'AoS', index]:
                    s = f"vector[{unparse(index)}]"
                case ['SRowVector', 'AoS', index]:
                    s = f"row_vector[{unparse(index)}]"
                case ['SMatrix', 'AoS', index1, index2]:
                    s = f"matrix[{unparse(index1)},{unparse(index2)}]"
                case ['SArray', type, index]:
                    s = f"array[{unparse(index)}] {unparse(type)}"
                case ['UArray', type]:
                    s = f"UArray {unparse(type)}" # TODO
                case ['Variable' | 'LVariable' | 'loop_variable', [['name', name], _]]:
                    s = str(name)
                case ['Single', ix]:
                    s = unparse(ix)
                case ['Indexed' | 'LIndexed', var, [*ixs]]:
                    ixs_s = ", ".join([unparse(ix) for ix in ixs])
                    return f"{unparse(var)}[{ixs_s}]"
                case ['BinOp', arg1, op, arg2]:
                    s = f"({unparse(arg1)} {ops[op]} {unparse(arg2)})"
                case ['PrefixOp', op, arg]:
                    s = f"{ops[op]}{unparse(arg)}"
                case ['PostfixOp', arg, op]:
                    s = f"{unparse(arg)}{ops[op]}"
                case ['lower_bound' | 'upper_bound', bound]:
                    s = unparse(bound)
                case ['For', loop_var, low, up, ['loop_body', body]]:
                    s += f"for ({unparse(loop_var)} in  {unparse(low)}:{unparse(up)})" + " {\n"
                    s += unparse(body, indent + "    ")
                    s += indent + "}"
                case ["While", test, body]:
                    s += f"while ({unparse(test)})" + " {\n"
                    s += unparse(body, indent + "    ")
                    s += indent + "}"
                case ['TargetPE', arg]:
                    s = f"target += {unparse(arg)}"
                case ['CondDistApp', [], [['name', name], _], [arg, *args]]:
                    args_s = ", ".join([unparse(arg) for arg in args])
                    s = f"{name}({unparse(arg)} | {args_s})"
                case ['IfThenElse', test, then, []]:
                    s += f"if ({unparse(test)})" + " {\n"
                    s += unparse(then, indent + "    ")
                    s += indent + "}"
                case ['IfThenElse', test, then, orelse]:
                    s += f"if ({unparse(test)})" + " {\n"
                    s += unparse(then, indent + "    ")
                    s += indent + "else {\n"
                    s += unparse(orelse, indent + "    ")
                    s += indent + "}"
                case ['FunApp' | 'NRFunApp', [], [['name', name], _], [*args]]:
                    args_s = ", ".join([unparse(arg) for arg in args])
                    s = f"{name}({args_s})"
                case ['Paren', expr]:
                    match expr:
                        case [['expr', ['BinOp', *_]], _]:
                            s = f"{unparse(expr)}"
                        case _:
                            s = f"({unparse(expr)})"
                case ['RowVectorExpr', [*args]]:
                    args_s = ", ".join([unparse(arg) for arg in args])
                    s = f"[{args_s}]"
                case ['ArrayExpr', [*args]]:
                    args_s = ", ".join([unparse(arg) for arg in args])
                    s = "{" + args_s + "}"
                case ['FunDef', ['returntype', retype], ['funname', [['name', fname], _]], ['arguments', [*args]], ['body', body]]:
                    args_s = ", ".join([unparse(arg) for arg in args])
                    s = f"{unparse(retype)} {fname}({args_s})" + " {\n"
                    s += unparse(body, indent + "    ")
                    s += indent + "}"
                case ['ReturnType', retype]:
                    s = unparse(retype)
                case ['AutoDiffable' | 'DataOnly', type, [['name', name], _]]:
                    s = f"{unparse(type)} {name}"
                case ['Return', expr]:
                    s = f"return {unparse(expr)}"
                case ['Reject', [*args]]:
                    args_s = ", ".join([unparse(arg) for arg in args])
                    s = f"reject({args_s})"
                case ['Print', arg]:
                    s = f"print({unparse(arg)})"
                case ['PString', arg]:
                    s = unparse(arg)
                case ['PExpr', expr]:
                    s = unparse(expr)
                case ['Between', arg1, arg2]:
                    s = f"{unparse(arg1)} : {unparse(arg2)}"
                case ['Downfrom', expr]:
                    s = f" : {unparse(expr)}"
                case ['Upfrom', expr]:
                    s = f"{unparse(expr)} : "
                case ['TernaryIf', test, then, orelse]:
                    s = f"({unparse(test)}) ? {unparse(then)} : {unparse(orelse)}"
                case ['name', name]:
                    s = name
                case _:
                    raise Exception(f"Unknown sexpr {hide_loc_data(sexpr)}")
        else:
            s = "".join([unparse(child, indent) for child in sexpr])
    else:
        s = str(sexpr)
    return s
