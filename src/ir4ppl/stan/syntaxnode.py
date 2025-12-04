
import sexpdata
from typing import Optional, Dict, Tuple, List, Any
from utils import *
from ir4ppl.base_cfg import AbstractSyntaxNode

def sym_to_str(sexpr):
    if isinstance(sexpr, sexpdata.Symbol):
        return sexpr.value()
    elif isinstance(sexpr, list):
        return [sym_to_str(el) for el in sexpr]
    elif isinstance(sexpr, (bool,int,float,str)):
        return sexpr
    else:
        assert False, (sexpr, type(sexpr))

from pprint import pprint
class StanSyntaxNode(AbstractSyntaxNode):
    def __init__(self, sexpr, head: str, value: Any = None) -> None:
        self.sexpr = sexpr
        self.head = head
        self.value = value
        self.parent: Optional[StanSyntaxNode] = None
        self.children: List[StanSyntaxNode] = list()

    def set_loc(self, loc_data, line_offsets: list[int], file_content: FileContent):
        start, end = get_first_last_byte(loc_data, line_offsets) # type:ignore
        self.position: int = start
        self.end_position: int = end
        self.span: int = self.end_position - self.position
        self.source = file_content
        # print(file_content[start:end])

    def has_loc(self):
        return hasattr(self, "position")
    
    def sourcetext(self):
        return self.source[self.position : self.end_position]

    def __getitem__(self, i: int):
        return self.children[i]
    
    def append(self, child):
        assert isinstance(child, StanSyntaxNode), child
        child.parent = self
        self.children.append(child)

    def fields(self) -> List[str]:
        return [child.head for child in self.children]
    def __repr__(self) -> str:
        if self.head == "constant":
            return f"constant({self.value})"
        return f"{self.head}({self.fields()}))"
    
    def pprint(self):
        print(self.head, end=" ")
        pprint({i: child for i, child in enumerate(self.children)})

class EmptyStanSyntaxNode(StanSyntaxNode):
    pass

def get_first_last_byte(loc_data, line_offsets: List[int]):
    # print(loc_data)
    match loc_data:
        case [_, [['begin_loc', [['line_num', start_line_num], ['col_num', start_col_num]]], ['end_loc', [['line_num', end_line_num], ['col_num', end_col_num]]]]]:
            start = line_offsets[start_line_num-1] + start_col_num
            end = line_offsets[end_line_num-1] + end_col_num
            return start, end
        case [_, '<opaque>']:
            return 0,0
        case _:
            raise Exception(f"Unknown loc data: {loc_data}")


# def make_stan_syntaxtree(sexpr, line_offsets: List[int], file_content: FileContent):
#     if isinstance(sexpr, list):
#         if len(sexpr) == 0:
#             return []
#         if isinstance(sexpr[0], str):
#             return {sexpr[0]: [make_stan_syntaxtree(child, line_offsets, file_content) for child in sexpr[1:]]}
#         else:
#             return [make_stan_syntaxtree(child, line_offsets, file_content) for child in sexpr]
#     else:
#         return sexpr
    
def preproc_nested_stmts(sexpr):
    if isinstance(sexpr, list) and len(sexpr) == 1 and isinstance(sexpr[0], list) and sexpr[0][0] == "stmts":
        return preproc_nested_stmts(sexpr[0])
    if isinstance(sexpr, list):
        return [preproc_nested_stmts(child) for child in sexpr]
    else:
        return sexpr

def preproc_smeta_emeta(sexpr):
    if isinstance(sexpr, list):
        if len(sexpr) == 2 and isinstance(sexpr[0], list) and isinstance(sexpr[1], list) and len(sexpr[0]) > 0 and len(sexpr[1]) > 0:
            if ((sexpr[0][0] == "expr" and sexpr[1][0] == "emeta") or 
                (sexpr[0][0] == "stmt" and sexpr[1][0] == "smeta") or (
                (sexpr[0][0] == "stmts" and sexpr[1][0] == "xloc")
                )):
                if sexpr[1][0] == "xloc":
                    sexpr[1][0] = "loc"
                    sexpr[0].append(["bmeta", sexpr[1]])
                else:
                    # sexpr[0].append(sexpr[1])
                    sexpr[0].append([sexpr[1][0], sexpr[1][1][0]])
                return preproc_smeta_emeta(sexpr[0])
        return [preproc_smeta_emeta(child) for child in sexpr]
    else:
        return sexpr
    
def preproc_locdata(sexpr):
    if isinstance(sexpr, list):
        if len(sexpr) > 0 and sexpr[0] in ("filename", "included_from"):
            return None
        new_list = []
        for child in sexpr:
            new_child = preproc_locdata(child) 
            if new_child is not None:
                new_list.append(new_child)
        return new_list
    else:
        return sexpr

from copy import deepcopy
# this works for now, but should be replaced with better logic to handle all assign_lhs (e.g. x[i][j])
def preproc_operatorassign(sexpr):
    match sexpr:
        case ['Assignment',
         ['assign_lhs',
          ['LValue',
           [['lval', ['LVariable', var]],
            ['lmeta', lmeta]]]],
         ['assign_op', ['OperatorAssign', op]],
         ['assign_rhs', rhs]]:
            
            return ['Assignment',
                ['assign_lhs',
                ['LValue',
                [['lval', ['LVariable', deepcopy(var)]],
                    ['lmeta', lmeta]]]],
                ['assign_op', 'Assign'],
                ['assign_rhs', [
                    ['expr', ['BinOp', [['expr', ['Variable', deepcopy(var)]], ['emeta', deepcopy(lmeta)]], op, rhs]],
                    ['emeta', [['loc', '<opaque>']]]
                    ]]
                ]
        
        case ['Assignment',
         ['assign_lhs',
          ['LValue',
           [['lval',
             ['LIndexed',
              [['lval', ['LVariable', var]],
               ['lmeta', lmeta1]],
              [*index]]],
            ['lmeta', lmeta2]]]],
         ['assign_op', ['OperatorAssign', op]],
         ['assign_rhs', rhs]]:
                        
            return ['Assignment',
                ['assign_lhs',
                ['LValue',
                [['lval',
                    ['LIndexed',
                    [['lval', ['LVariable', var]],
                    ['lmeta', lmeta1]],
                    [*index]]],
                    ['lmeta', lmeta2]]]],
                ['assign_op', 'Assign'],
                ['assign_rhs', [
                    ['expr', ['BinOp', [['expr', ['Indexed', [['expr', ['Variable', deepcopy(var)]],['emeta', deepcopy(lmeta1)]], [deepcopy(ix) for ix in index]]], ['emeta', deepcopy(lmeta2)]], op, rhs]],
                    ['emeta', [['loc', '<opaque>']]]
                    ]]
                ]
        
    if isinstance(sexpr, list):
        return [preproc_operatorassign(child) for child in sexpr]
    else:
        return sexpr
    
def hide_loc_data(sexpr):
    if isinstance(sexpr, list) and len(sexpr) > 0 and sexpr[0] in ("loc", "xloc", "id_loc"):
        return [sexpr[0], "..."]
    if isinstance(sexpr, list):
        return [hide_loc_data(child) for child in sexpr]
    else:
        return sexpr
    
    
def make_stan_syntaxtree(sexpr, line_offsets: List[int], file_content: FileContent):
    # pprint(hide_loc_data(sexpr))
    sexpr = preproc_operatorassign(sexpr)
    sexpr = preproc_smeta_emeta(sexpr)
    sexpr = preproc_nested_stmts(sexpr)
    sexpr = preproc_locdata(sexpr)
    # pprint(hide_loc_data(sexpr))
    # assert False
    return _make_stan_syntaxtree(sexpr, line_offsets, file_content)


def _make_stan_syntaxtree(sexpr, line_offsets: List[int], file_content: FileContent) -> StanSyntaxNode:
    if not isinstance(sexpr, list):
        return StanSyntaxNode(sexpr, "constant", value=sexpr)
    if len(sexpr) == 0:
        return EmptyStanSyntaxNode(sexpr, "")
    if isinstance(sexpr[0], str) and sexpr[0] not in ("stmts", "Block"):
        syntaxnode = StanSyntaxNode(sexpr, sexpr[0])
        for child in sexpr[1:]:
            if isinstance(child, list) and len(child) > 0 and child[0] in ("emeta", "smeta"):
                syntaxnode.set_loc(child[1], line_offsets, file_content)
                continue
                
            childnode = _make_stan_syntaxtree(child, line_offsets, file_content)
            if not isinstance(childnode, EmptyStanSyntaxNode):
                syntaxnode.append(childnode)
        return syntaxnode
    else:
        syntaxnode = StanSyntaxNode(sexpr, "block")
        i = 0
        for child in sexpr:
            if child in ("stmts", "Block"):
                continue
            if isinstance(child, list) and len(child) > 0 and child[0] == "bmeta":
                syntaxnode.set_loc(child[1], line_offsets, file_content)
                continue
            if isinstance(child, list) and len(child) > 0 and child[0] == "id_loc":
                syntaxnode.set_loc(child, line_offsets, file_content)
                continue
            childnode = _make_stan_syntaxtree(child, line_offsets, file_content)
            if not isinstance(childnode, EmptyStanSyntaxNode):
                if childnode.head == "block":
                    # flatten blocks
                    for child in childnode.children:
                        syntaxnode.append(child)
                        i += 1
                else:
                    syntaxnode.append(childnode)
                    i += 1

        # if len(syntaxnode.children) == 1:
        #     child = syntaxnode[0]
        #     if child.head in ("stmt", "expr"):
        #         syntaxnode.parent = None
        #         syntaxnode.children.clear()
        #         # syntaxnode.fields.clear()
        #         return child
        return syntaxnode