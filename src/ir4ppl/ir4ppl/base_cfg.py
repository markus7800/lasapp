from .cfg import *
from copy import copy

def get_only_elem(s: Set[CFGNode]) -> CFGNode:
    assert len(s) == 1
    return list(s)[0]

class AbstractSyntaxNode:
    pass

class AbstractCFGBuilder():
    
    def __init__(self, node_to_id: Dict[AbstractSyntaxNode,str]) -> None:
        self.node_to_id = node_to_id
        self.cfgs: Dict[FunctionDefinition,CFG] = dict() # toplevel -> CFG, functiondef -> CFG

    def get_cfg(self, node: AbstractSyntaxNode, breaknode:Optional[JoinNode], continuenode:Optional[JoinNode], returnnode:Optional[JoinNode]) -> CFG:
        raise NotImplementedError
        
    def get_function_cfg(self, node: AbstractSyntaxNode) -> CFG:
        raise NotImplementedError

    def fix_break_continue(self, nodes: Set[CFGNode], breaknode: CFGNode, continuenode: CFGNode):
        for node in nodes:
            if isinstance(node, BreakNode):
                discard = [child for child in node.children if child != breaknode]
                for child in discard:
                    delete_edge(node, child)
            if isinstance(node, ContinueNode):
                discard = [child for child in node.children if child != continuenode]
                for child in discard:
                    delete_edge(node, child)
    
    def build_for_cfg(self, startnode: StartNode, nodes: Set[CFGNode], endnode: EndNode,
                      for_start_join_cfgnode: JoinNode, for_branch_cfgnode: BranchNode, for_end_join_cfgnode: JoinNode, loop_var_cfgnode: LoopIterNode,
                      body: AbstractSyntaxNode,
                      returnnode: Optional[JoinNode]):
            
        for_branch_cfgnode.join_nodes.add(for_start_join_cfgnode)
        for_branch_cfgnode.join_nodes.add(for_end_join_cfgnode)

        # return stms in while body may flow to different join node
        if returnnode is not None:
            for_branch_cfgnode.join_nodes.add(returnnode)

        nodes.update([for_branch_cfgnode, for_start_join_cfgnode, for_end_join_cfgnode, loop_var_cfgnode])
        add_edge(startnode, for_start_join_cfgnode)
        add_edge(for_start_join_cfgnode, for_branch_cfgnode)
        add_edge(for_branch_cfgnode, for_end_join_cfgnode)
        add_edge(for_end_join_cfgnode, endnode)

        # continue stmts go to branch_cfgnode, break stmts go to join_cfgnode -> endnode
        body_cfg = self.get_cfg(body, for_end_join_cfgnode, for_start_join_cfgnode, returnnode)
        nodes.update(body_cfg.nodes)

        N1 = get_only_elem(body_cfg.startnode.children) # node after start node
        N2 = get_only_elem(body_cfg.endnode.parents)   # node before end node

        delete_edge(body_cfg.startnode, N1)
        delete_edge(N2, body_cfg.endnode)

        add_edge(for_branch_cfgnode, loop_var_cfgnode)
        add_edge(loop_var_cfgnode, N1)
        add_edge(N2, for_start_join_cfgnode)

        for_branch_cfgnode.then = loop_var_cfgnode
        for_branch_cfgnode.orelse = for_end_join_cfgnode

        self.fix_break_continue(nodes, for_end_join_cfgnode, for_start_join_cfgnode)


    def build_while_cfg(self, startnode: StartNode, nodes: Set[CFGNode], endnode: EndNode,
                      while_start_join_cfgnode: JoinNode, while_branch_cfgnode: BranchNode, while_end_join_cfgnode: JoinNode,
                      body: AbstractSyntaxNode,
                      returnnode: Optional[JoinNode]):
        

        # return stms in while body may flow to different join node
        if returnnode is not None:
            while_branch_cfgnode.join_nodes.add(returnnode)

        nodes.update([while_branch_cfgnode, while_start_join_cfgnode, while_end_join_cfgnode])
        add_edge(startnode, while_start_join_cfgnode)
        add_edge(while_start_join_cfgnode, while_branch_cfgnode)
        add_edge(while_branch_cfgnode, while_end_join_cfgnode)
        add_edge(while_end_join_cfgnode, endnode)

        # continue stmts go to branch_cfgnode, break stmts go to join_cfgnode -> endnode
        body_cfg = self.get_cfg(body, while_end_join_cfgnode, while_start_join_cfgnode, returnnode)
        nodes.update(body_cfg.nodes)

        N1 = get_only_elem(body_cfg.startnode.children) # node after start node
        N2 = get_only_elem(body_cfg.endnode.parents)    # node before end node

        delete_edge(body_cfg.startnode, N1)
        delete_edge(N2, body_cfg.endnode)

        add_edge(while_branch_cfgnode, N1)
        add_edge(N2, while_start_join_cfgnode)

        while_branch_cfgnode.then = N1
        while_branch_cfgnode.orelse = while_end_join_cfgnode

        self.fix_break_continue(nodes, while_end_join_cfgnode, while_start_join_cfgnode)

    def build_empty_cfg(self, startnode: StartNode, nodes: Set[CFGNode], endnode: EndNode, node: AbstractSyntaxNode):
        node_id = self.node_to_id[node]
        cfgnode= SkipNode(f"{node_id}_{node}")
        nodes.add(cfgnode)
        add_edge(startnode, cfgnode)
        add_edge(cfgnode, endnode)

    def build_if_cfg(self, startnode: StartNode, nodes: Set[CFGNode], endnode: EndNode,
                     branch_cfgnode: BranchNode, branch_join_cfgnode: JoinNode,
                     consequent: AbstractSyntaxNode, alternative: Optional[AbstractSyntaxNode],
                     breaknode: Optional[JoinNode], continuenode: Optional[JoinNode], returnnode: Optional[JoinNode]):
        # S_true -> CFG_true -> E_true
        # S_false -> CFG_false -> E_false
        # CFG_false can be empty
        # =>
        # S -> Branch -> CFG_true -> Join -> E
        #             \> CFG_false /

        branch_cfgnode.join_nodes.add(branch_join_cfgnode)

        # break, continue, and return stmts in branch can flow to different join nodes
        if breaknode is not None:
            branch_cfgnode.join_nodes.add(breaknode)
        if continuenode is not None:
            branch_cfgnode.join_nodes.add(continuenode)
        if returnnode is not None:
            branch_cfgnode.join_nodes.add(returnnode)


        nodes.update([branch_cfgnode, branch_join_cfgnode])
        add_edge(startnode, branch_cfgnode)
        add_edge(branch_join_cfgnode, endnode)

        has_else_branch = alternative is not None
        
        branch_nodes = [consequent, alternative] if has_else_branch else [consequent]
        next_nodes = []
        for branch_node in branch_nodes:
            # inherits breaknode and continuenode
            branch_cfg = self.get_cfg(branch_node, breaknode, continuenode, returnnode)
            nodes.update(branch_cfg.nodes)

            N1 = get_only_elem(branch_cfg.startnode.children) # node after start node
            N2 = get_only_elem(branch_cfg.endnode.parents)    # node before end node

            delete_edge(branch_cfg.startnode, N1)
            delete_edge(N2, branch_cfg.endnode)

            add_edge(branch_cfgnode, N1)
            add_edge(N2, branch_join_cfgnode)
            next_nodes.append(N1)

        branch_cfgnode.then = next_nodes[0]
        if not has_else_branch:
            # no alternate
            # skipnode = SkipNode(branch_cfgnode.id + "_skip")
            # nodes.add(skipnode)
            # add_edge(branch_cfgnode, skipnode)
            # add_edge(skipnode, branch_join_cfgnode)
            add_edge(branch_cfgnode, branch_join_cfgnode)
            branch_cfgnode.orelse = branch_join_cfgnode
        else:
            branch_cfgnode.orelse = next_nodes[1]


    def fix_return(self, nodes: Set[CFGNode], func_join_node: CFGNode):
        for node in nodes:
            if isinstance(node, ReturnNode):
                discard = [child for child in node.children if child != func_join_node]
                for child in discard:
                    delete_edge(node, child)
        

    def build_function_cfg(self, node_id: str, func_signature: str, func_body: AbstractSyntaxNode, funcarg_nodes: List[FuncArgNode]):
        func_join_cfgnode = JoinNode(node_id + "_func")

        # return stmts "break" to join_node, no continuenode
        body_cfg = self.get_cfg(func_body, None, None, func_join_cfgnode)

        nodes = copy(body_cfg.nodes)
        nodes.add(func_join_cfgnode)

        # # FUNCSTART -> FUNCARG1 -> FUNCARG2 ...
        startnode = FuncStartNode(node_id, func_signature)
        current_node = startnode
        for funcarg_node in funcarg_nodes:
            add_edge(current_node, funcarg_node)
            nodes.add(funcarg_node)
            current_node = funcarg_node
        endnode = EndNode(node_id)

        N1 = get_only_elem(body_cfg.startnode.children) # node after start node
        N2 = get_only_elem(body_cfg.endnode.parents)    # node before end node

        delete_edge(N2, body_cfg.endnode)
        delete_edge(body_cfg.startnode, N1)
        
        # FUNCARGS -> BODY
        add_edge(current_node, N1)
        # BODY -> JOIN_NODE -> END
        add_edge(N2, func_join_cfgnode)
        add_edge(func_join_cfgnode, endnode)

        self.fix_return(nodes, func_join_cfgnode)

        cfg =  CFG(startnode, nodes, endnode)
        try:
            verify_cfg(cfg)
        except Exception:
            print_cfg_dot(cfg)
            raise
        return cfg
