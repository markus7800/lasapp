import lasapp
from collections import deque

def is_descendant(parent: lasapp.SyntaxNode, child: lasapp.SyntaxNode):
    return parent.first_byte <= child.first_byte and child.last_byte <= parent.last_byte

class FunnelWarning:
    def __init__(self, funnel_rv: lasapp.RandomVariable, scale_rv: lasapp.RandomVariable):
        self.funnel_rv = funnel_rv
        self.scale_rv = scale_rv

    def __str__(self):
        return f"Funnel detected: Scale parameter of '{self.funnel_rv.name}' depends on variable '{self.scale_rv.name}', which may lead to poor inference performance."

    def get_diagnostic_ranges(self) -> list[tuple[int,int]]:
        return [(self.funnel_rv.node.first_byte, self.funnel_rv.node.last_byte), (self.scale_rv.node.first_byte, self.scale_rv.node.last_byte)]
    

def get_funnel_relationships(program: lasapp.ProbabilisticProgram, model: lasapp.Model):
    call_graph = program.get_call_graph(model.node)
    call_graph_nodes = {n.caller for n in call_graph}
    all_variables = program.get_random_variables()
    random_variables = {rv.node.node_id: rv for rv in all_variables if any(is_descendant(call_graph_node, rv.node) for call_graph_node in call_graph_nodes)}

    funnel_warnings: list[FunnelWarning] = []    

    for _, rv in random_variables.items():
        for param in rv.distribution.params:

            if param.name == 'scale':
                marked = set()
                queue = deque([param.node])
                while len(queue) > 0:
                    node = queue.popleft()
                    data_deps = program.get_data_dependencies(node)
                    for dep in data_deps:
                        if dep.node_id not in marked:
                            if dep.node_id in random_variables:
                                # if node is random variable, we do not continue recursion and add edge to graph
                                dep_rv = random_variables[dep.node_id]
                                funnel_warnings.append(FunnelWarning(rv,dep_rv))
                            else:
                                queue.append(dep)
                            marked.add(dep.node_id)


    return funnel_warnings
                

                