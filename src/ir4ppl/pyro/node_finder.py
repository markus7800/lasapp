from .syntaxnode import SyntaxNode
from typing import Any, Callable, List, Optional

class NodeVisitor:
    # override this method:
    def visit(self, node: SyntaxNode) -> Any:
        self.generic_visit(node)

    def generic_visit(self, node: SyntaxNode):
        for _, child in node.children.items():
            self.visit(child)

class NodeFinder(NodeVisitor):
    def __init__(self,
                 predicate: Callable[[SyntaxNode], bool],
                 map: Callable[[SyntaxNode], Any],
                 visit_matched_nodes: bool = False,
                 visit_predicate: Optional[Callable[[SyntaxNode],bool]]=None):
        
        super().__init__()
        self.predicate = predicate
        self.map = map
        if visit_predicate is None:
            if visit_matched_nodes:
                visit_predicate = lambda _: True
            else:
                visit_predicate = lambda node: not predicate(node)
        self.visit_predicate: Callable[[SyntaxNode],bool] = visit_predicate
        self.result: List[Any] = []

    def visit(self, node):
        if self.predicate(node):
            self.result.append(self.map(node))
        if self.visit_predicate(node):
            self.generic_visit(node)
            
        return self.result