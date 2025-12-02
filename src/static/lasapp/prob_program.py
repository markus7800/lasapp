import os

from .server_interface import *
from .jsonrpc_client import get_jsonrpc_client


class ProbabilisticProgram:
    def __init__(self, file_name: str, file_content: str | None = None, n_unroll_loops: int = 0) -> None:
        file_content_provided = file_content is not None
        if file_content is None:
            with open(file_name, encoding="utf-8") as f:
                file_content = f.read()
            
        if 'pyro' in file_content:
            ppl = 'pyro'
            socket_name = "./.pipe/python_rpc_socket"
        elif 'pymc' in file_content:
            ppl = 'pymc'
            socket_name = "./.pipe/python_rpc_socket"
        elif 'Turing' in file_content:
            ppl = 'turing'
            socket_name = "./.pipe/julia_rpc_socket"
        elif 'beanmachine' in file_content:
            ppl = 'beanmachine'
            socket_name = "./.pipe/python_rpc_socket"
        elif 'Gen' in file_content:
            ppl = 'gen'
            socket_name = "./.pipe/julia_rpc_socket"
        else:
            raise ValueError("No probabilistic framework found.")

        self.client = get_jsonrpc_client(socket_name)
        self.file_name = file_name
        self.ppl = ppl


        if file_content_provided:
            response = self.client.build_ast_for_file_content(file_content=file_content, ppl=ppl, n_unroll_loops=n_unroll_loops)
        else:
            response = self.client.build_ast(file_name=file_name, ppl=ppl, n_unroll_loops=n_unroll_loops)
            
        tree_id = response["result"]
        self.tree_id = tree_id

    def close(self):
        self.client.close()

    def get_model(self) -> Model:
        return self.client.get_model(
            tree_id=self.tree_id, object_hook=Model.from_dict
        )
    
    def get_guide(self) -> Model:
        return self.client.get_guide(
            tree_id=self.tree_id, object_hook=Model.from_dict
        )

    def get_random_variables(self) -> list[RandomVariable]:
        return self.client.get_random_variables(
            tree_id=self.tree_id, object_hook=RandomVariable.from_dict
        )
        
    def get_data_dependencies(self, node: SyntaxNode) -> list[SyntaxNode]:
        return self.client.get_data_dependencies(
            node=node, tree_id=self.tree_id, object_hook=SyntaxNode.from_dict
        )

    def get_control_dependencies(self, node: SyntaxNode) -> list[ControlDependency]:
        return self.client.get_control_dependencies(
            node=node, tree_id=self.tree_id, object_hook=ControlDependency.from_dict
        )
    
    def estimate_value_range(self, expr: SyntaxNode, mask: dict[SyntaxNode,Interval]) -> Interval: 
        mask = list(mask.items())
        return self.client.estimate_value_range(
            expr=expr,
            tree_id=self.tree_id,
            mask=mask,
            object_hook=Interval.from_dict
        )
    
    def get_call_graph(self, node: SyntaxNode) -> list[CallGraphNode]:
        return self.client.get_call_graph(
            tree_id=self.tree_id,
            node=node,
            object_hook=CallGraphNode.from_dict
        )
    
    def get_path_condition(self, node: SyntaxNode, root: SyntaxNode, mask: dict[SyntaxNode, SymbolicExpression]) -> SymbolicExpression:
        mask = list(mask.items())
        return self.client.get_path_conditions(
            tree_id=self.tree_id,
            root=root,
            nodes=[node],
            mask=mask,
            object_hook=SymbolicExpression.from_dict
        )[0]
    
    # batched version of get_path_condition
    def get_path_conditions(self, nodes: list[SyntaxNode], root: SyntaxNode, mask: dict[SyntaxNode, SymbolicExpression]) -> list[SymbolicExpression]:
        mask = list(mask.items())
        return self.client.get_path_conditions(
            tree_id=self.tree_id,
            root=root,
            nodes=nodes,
            mask=mask,
            object_hook=SymbolicExpression.from_dict
        )