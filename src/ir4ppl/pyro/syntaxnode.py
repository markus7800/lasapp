
#%%
import ast
from typing import List, Tuple, Dict, Optional, Iterator
from utils import *
from ir4ppl.base_cfg import AbstractSyntaxNode

def has_position_info(node: ast.AST):
    return hasattr(node, "lineno") and hasattr(node, "col_offset") and hasattr(node, "end_lineno") and hasattr(node, "end_col_offset")

# returns the indices of source text of node in utf8 source code
def get_first_last_byte(node: ast.AST, line_offsets: List[int]) -> Tuple[int, int]:
    start = line_offsets[node.lineno-1] + node.col_offset       # type: ignore
    end = line_offsets[node.end_lineno-1] + node.end_col_offset # type: ignore
    return start, end

from copy import deepcopy
class Block(ast.AST):
    def __init__(self, stmts: List[ast.stmt]) -> None:
        super().__init__()
        self.stmts = stmts
        if len(stmts) > 0:
            self.lineno = stmts[0].lineno
            self.col_offset = stmts[0].col_offset
            self.end_lineno = stmts[-1].end_lineno
            self.end_col_offset = stmts[-1].end_col_offset
        
    def __len__(self):
        return len(self.stmts)
    
    def __getitem__(self, key):
        # return getattr(self, f"stmt_{key}") 
        return self.stmts[key]    
    
    def __iter__(self):
        return (self.stmts[i] for i in range(len(self)))
    
    def __deepcopy__(self, memo):
        if id(self) in memo:
            return memo[id(self)]
        new_body = [deepcopy(stmt, memo) for stmt in self]
        return Block(new_body)
    
def _unparse_Block(self: ast._Unparser, node: Block): # type: ignore
    for item in node:
        self.traverse(item)
ast._Unparser.visit_Block = _unparse_Block # type: ignore

class SyntaxNode(AbstractSyntaxNode):
    def __init__(self, node: ast.AST, line_offsets: List[int], file_content: FileContent) -> None:
        self.ast_node = node
        self.parent: Optional[SyntaxNode] = None
        self.fields: List[str] = list()
        self.children: Dict[str, SyntaxNode] = dict()
        if has_position_info(node):
            start, end = get_first_last_byte(node, line_offsets)
            self.position: int = start
            self.end_position: int = end
            self.span: int = self.end_position - self.position
            self.source = file_content

    def is_kind(self, kind: type | Tuple[type, ...]) -> bool:
        return isinstance(self.ast_node, kind)
    
    def kind(self) -> type:
        return type(self.ast_node)
    
    def __getitem__(self, field: str):
        return self.children[field]
    
    def __setitem__(self, field: str, child):
        if isinstance(child, SyntaxNode):
            child.parent = self
        self.fields.append(field)
        self.children[field] = child
    
    def get_children(self, prefix: str) -> Iterator['SyntaxNode']:
        i = 0
        while True:
            field = f"{prefix}_{i}"
            if field in self.children:
                yield self.children[field]
            else:
                break
            i += 1

    def __repr__(self) -> str:
        return f"{type(self.ast_node).__name__}({self.fields})"




def make_syntaxtree(node: ast.AST, line_offsets: List[int], file_content: FileContent) -> SyntaxNode:
    syntaxnode = SyntaxNode(node, line_offsets, file_content)
    node.syntaxnode = syntaxnode # type: ignore this is a bit ugly

    for name, field in ast.iter_fields(node):
        if isinstance(field, ast.AST):
            childnode = make_syntaxtree(field, line_offsets, file_content)
            syntaxnode[name] = childnode

        elif isinstance(field, list):
            if name == "body" or name == "orelse":
                childnode = SyntaxNode(Block(field), line_offsets, file_content)
                syntaxnode[name] = childnode

                for i, item in enumerate(field):
                    if isinstance(item, ast.AST):
                        stmtnode = make_syntaxtree(item, line_offsets, file_content)
                        childnode[f"stmt_{i}"] = stmtnode
            else:
                for i, item in enumerate(field):
                    if isinstance(item, ast.AST):
                        childnode = make_syntaxtree(item, line_offsets, file_content)
                        syntaxnode[f"{name}_{i}"] = childnode

    return syntaxnode

def get_syntaxnode(node: ast.AST) -> SyntaxNode:
    return node.syntaxnode # type: ignore

#%%
# s = """
# import c
# x = 1
# y[i] = 2
# a.b = 3
# e, f = 4, 5
# g = h = 1
# (x, y[i], a.b, c.d())
# """
# s = """
# a = A()
# b = a.b
# b.c = 1
# a.b.c
# """
# s = """
# if test1:
#     1
# if test2:
#     2
# else:
#     3
#     4
# """
# line_offsets = get_line_offsets_for_str(s)

# node = ast.parse(s)
# print(ast.dump(node, indent=2))
# # %%
# sn = make_syntaxtree(node, line_offsets, FileContent(s))
# n = sn["body"]["stmt_0"]
# n
# # %%
# import ast_scope
# scope_info = ast_scope.annotate(node)
# for n, scope in scope_info._node_to_containing_scope.items():
#     print(ast.dump(n), scope)
# # %%
# ab = node.body[3].value.elts[2]
# print(ast.dump(ab))

# # %%
# scope_info[ab]

# # %%
