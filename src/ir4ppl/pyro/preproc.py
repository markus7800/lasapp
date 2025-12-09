#%%
from typing import Callable
import ast
import uuid
from copy import deepcopy
import ast_scope

# x = y = 1 -> [x = 1, y = 1]
# x, y = value -> [tmp = value, x = tmp[0], y = tmp[1]]
# Called before BlockNodeTransformer
class MultitargetTransformer(ast.NodeVisitor):
    def visit(self, node: ast.AST):
        if hasattr(node, "body") and isinstance(node.body, list):
            new_body = []
            for stmt in node.body:
                position_args = {"lineno": stmt.lineno, "col_offset": stmt.col_offset, "end_lineno": stmt.end_lineno, "end_col_offset": stmt.end_col_offset}
                match stmt:
                    case ast.Assign(targets=[_, _, *_]): # x = y = 1
                        for name in stmt.targets:
                            new_stmt = deepcopy(stmt)
                            new_stmt.targets = [deepcopy(name)]
                            # new_stmt = ast.Assign(targets=[name], value=deepcopy(stmt.value), **position_args)
                            new_body.append(new_stmt)
                    case ast.Assign(targets=[ast.Tuple()], value=value): # x, y = 1
                        uuid4 = str(uuid.uuid4())[:5]
                        tmp_name_store = ast.Name(id=f'__TMP__{uuid4}', ctx=ast.Store())
                        tmp_name_load = ast.Name(id=tmp_name_store.id, ctx=ast.Load())
                        assign = ast.Assign(targets=[tmp_name_store], value=value, lineno=stmt.lineno, col_offset=stmt.col_offset, end_lineno=stmt.end_lineno, end_col_offset=stmt.col_offset)
                        new_body.append(assign)
                        tuple_target = stmt.targets[0]
                        for i, name in enumerate(tuple_target.elts):
                            assign = ast.Assign(targets=[name], value=ast.Subscript(value=tmp_name_load, slice=ast.Constant(value=i), ctx=ast.Load()), **position_args)
                            new_body.append(assign)

                    case _:
                        new_body.append(stmt)
                        # print(ast.unparse(stmt))
            node.body = new_body

        match node:
            case ast.For(target=ast.Tuple(elts=_elts), body=_body):
                        uuid4 = str(uuid.uuid4())[:5]
                        tmp_name_store = ast.Name(id=f'__TMP__{uuid4}', ctx=ast.Store())
                        tmp_name_load = ast.Name(id=tmp_name_store.id, ctx=ast.Load())
                        node.target = tmp_name_load
                        for i, name in enumerate(_elts):
                            assign = ast.Assign(targets=[name], value=ast.Subscript(value=tmp_name_load, slice=ast.Constant(value=i), ctx=ast.Load()), **position_args)
                            _body.insert(i, assign)
            
        return self.generic_visit(node)
    

class NameReplacer(ast.NodeTransformer):
    def __init__(self, id, replace_with):
        self.id = id
        self.replace_with = replace_with
    def visit_Name(self, node: ast.Name):
        if node.id == self.id:
            return deepcopy(self.replace_with)
        return self.generic_visit(node)
    
# call after BlockTransformer, before PositionParentAdder
class LoopUnroller(ast.NodeTransformer):
    def __init__(self, N) -> None:
        self.N = N

    def unroll_loops_in_body(self, body: list[ast.stmt]):
        # print("LoopUnroller Block", node)
        new_block_body = []
        for stmt in body:
            match stmt:
                case ast.For(target=ast.Name(), iter=ast.Call(func=ast.Name(id=_func_id), args=_args)) if _func_id == 'range':
                    # print("LoopUnroller For:", ast.dump(stmt.target), ast.dump(stmt.iter))
                    iter_range = range(self.N)
                    match _args:
                        case [ast.Constant(value=value)]:
                            iter_range = range(value)
                        case [ast.Constant(value=value1), ast.Constant(value=value2)]:
                            iter_range = range(value1, value2)
                    for i in iter_range:
                        assert isinstance(stmt.target, ast.Name)
                        for forbody_stmt in stmt.body:
                            forbody_stmt_copy = deepcopy(forbody_stmt)
                            NameReplacer(stmt.target.id, ast.Constant(value=i)).visit(forbody_stmt_copy)
                            new_block_body.append(forbody_stmt_copy)
                case _:
                    new_block_body.append(stmt)

        return new_block_body


    def visit(self, node: ast.AST):
        node = self.generic_visit(node)
        if hasattr(node, "body"):
            node.body = self.unroll_loops_in_body(node.body)
        if hasattr(node, "orelse"):
            node.orelse = self.unroll_loops_in_body(node.orelse)
        return node
    


class ASTNodeFinder(ast.NodeVisitor):
    def __init__(self, predicate, map, visit_matched_nodes=False, visit_predicate=None):
        super().__init__()
        self.predicate = predicate
        self.map = map
        if visit_predicate is None:
            if visit_matched_nodes:
                visit_predicate = lambda _: True
            else:
                visit_predicate = lambda node: not predicate(node)
        self.visit_predicate = visit_predicate
        self.result = []

    def visit(self, node):
        if self.predicate(node):
            self.result.append(self.map(node))
        if self.visit_predicate(node):
            self.generic_visit(node)
            
        return self.result
    
def CallFinder(func_syntaxnode: ast.FunctionDef, call_unquifier):
    assert isinstance(func_syntaxnode, ast.FunctionDef)
    if func_syntaxnode not in call_unquifier.scope_info:
        # if we deepcopy a function foo which defines a nested function,
        # we have to find scope for the nested function (deepcopied foo)
        call_unquifier.scope_info = ast_scope.annotate(call_unquifier.root_node)

    scope_info = call_unquifier.scope_info
    return ASTNodeFinder(
        lambda node: (isinstance(node, ast.Call) and
                      isinstance(node.func, ast.Name) and
                      node.func.id == func_syntaxnode.name and
                      node.func in scope_info and
                      scope_info[node.func] == scope_info[func_syntaxnode]),
        lambda node: node
    )

class CallUniquifier(ast.NodeVisitor):
    def __init__(self, root_node, scope_info) -> None:
        self.root_node = root_node
        self.scope_info = scope_info
        # scope_info must be updated after transforming ast

    def visit(self, node: ast.AST):
        if hasattr(node, "body") and isinstance(node.body, list):
            new_body = []
            for stmt in node.body:
                new_body.append(stmt)
                match stmt:
                    case ast.FunctionDef(name=_name):
                        call_finder = CallFinder(stmt, self)
                        calls = call_finder.visit(self.root_node)
                        if len(calls) > 1:
                            for i, call in enumerate(calls):
                                new_name = f"{_name}_{i}"
                                call.func.id = new_name
                                new_func = deepcopy(stmt)
                                new_func.name = new_name
                                new_body.append(new_func)
            node.body = new_body

        return self.generic_visit(node)

def get_pos_args(stmt):
    return {
        "lineno": stmt.lineno,
        "col_offset": stmt.col_offset,
        "end_lineno": stmt.end_lineno,
        "end_col_offset": stmt.end_col_offset,
    }

# replaces rogue pyro.sample(...) nodes with proper assignments x = pyro.sample(...)
class PyroPreprocessor(ast.NodeTransformer):
        def __init__(self) -> None:
            self.tmp_cnt = 0
            self.block_insertions_stack = []

        def generic_visit(self, node: ast.AST):
            for field, value in ast.iter_fields(node):
                if field in ('body', 'orelse'):
                    assert isinstance(value, list)
                    block_insertions = []
                    self.block_insertions_stack.append(block_insertions)

                    new_list = list()
                    for item in value:
                        if isinstance(item, ast.AST):
                            transformed_item = self.visit(item)
                            if len(block_insertions) > 0:
                                new_list.extend(block_insertions)
                                block_insertions.clear()
                            new_list.append(transformed_item)
                        else:
                            new_list.append(item)

                    self.block_insertions_stack.pop()
                    setattr(node, field, new_list)

                elif isinstance(value, list):
                    new_list = list()
                    for item in value:
                        if isinstance(item, ast.AST):
                            transformed_item = self.visit(item)
                            new_list.append(transformed_item)
                        else:
                            new_list.append(item)
                    setattr(node, field, new_list)

                elif isinstance(value, ast.AST):
                    transformed_item = self.visit(value)
                    setattr(node, field, transformed_item)

            return node

        def visit_Assign(self, node: ast.Assign):
            match node:
                case ast.Assign(value=ast.Call(func=ast.Attribute(value=ast.Name(id=_id), attr=_attr))) if _id == "pyro" and _attr == "sample":
                    return node
                case ast.Assign(value=ast.Call(func=ast.Name(id=_id))) if _id == "sample":
                    return node
            return self.generic_visit(node)

        def visit_Call(self, node: ast.Call):
            node = self.generic_visit(node)
            found = False
            match node:
                case ast.Call(func=ast.Attribute(value=ast.Name(id=_id), attr=_attr)) if _id == "pyro" and _attr == "sample":
                    found = True
                case ast.Call(func=ast.Name(id=_id)) if _id == "sample":
                    found = True

            if found:
                self.tmp_cnt += 1
                name = ast.Name(id=f"__TMP__{self.tmp_cnt}", ctx=ast.Store())
                assign = ast.Assign(targets=[name], value=node, **get_pos_args(node))
                name_load = ast.Name(id=name.id, ctx=ast.Load())
                self.block_insertions_stack[-1].append(assign)
                return name_load

            return node
# %%
# s = """
# x = pyro.sample("x", dist.Normal(0,1))

# pyro.sample("x", dist.Normal(0,1))


# pyro.sample("x", dist.Normal(
#     pyro.sample("y", dist.Normal(0, 1)),
# 1))


# pyro.sample("x", dist.Normal(
#     pyro.sample("y", dist.Normal(
#         pyro.sample("z", dist.Normal(0,1)),
#     1)),
# 1))

# """
# a = ast.parse(s)
# b = PyroPreprocessor().visit(a)
# # %%
# print(ast.unparse(b))
# %%


#%%

# s = """
# x = [0,1,2]
# for i in range(3):
#     x[i] = x[i] + i
# """
# s = """
# x = something()
# for i in range(3):
#     for j in range(2):
#         x[i, j] = x[i] + j
# """
# syntax_tree = ast.parse(s)
# LoopUnroller(4).visit(syntax_tree)
# print(ast.unparse(syntax_tree))

# %%
