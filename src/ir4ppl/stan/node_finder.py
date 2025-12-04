from .syntaxnode import StanSyntaxNode, hide_loc_data
from typing import Any, Callable, List, Optional

class NodeVisitor:
    # override this method:
    def visit(self, node: StanSyntaxNode) -> Any:
        self.generic_visit(node)

    def generic_visit(self, node: StanSyntaxNode):
        for child in node.children:
            self.visit(child)

class NodeFinder(NodeVisitor):
    def __init__(self,
                 predicate: Callable[[StanSyntaxNode], bool],
                 map: Callable[[StanSyntaxNode], Any],
                 visit_matched_nodes: bool = False,
                 visit_predicate: Optional[Callable[[StanSyntaxNode],bool]]=None):
        
        super().__init__()
        self.predicate = predicate
        self.map = map
        if visit_predicate is None:
            if visit_matched_nodes:
                visit_predicate = lambda _: True
            else:
                visit_predicate = lambda node: not predicate(node)
        self.visit_predicate: Callable[[StanSyntaxNode],bool] = visit_predicate
        self.result: List[Any] = []

    def visit(self, node):
        if self.predicate(node):
            self.result.append(self.map(node))
        if self.visit_predicate(node):
            self.generic_visit(node)
            
        return self.result