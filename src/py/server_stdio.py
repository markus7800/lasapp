from server import *
import sys
from jsonrpc import dispatcher
import os
from pathlib import Path
from jsonrpc_server import *


def run_server(dispatcher):
    reader = sys.stdin.buffer
    writer = sys.stdout.buffer
    handle_client(reader, writer, dispatcher)
    reader.close()
    writer.close()
        

if __name__ == '__main__':

    print("Started Python Language Server stdio")

    dispatcher["build_ast"] = build_ast
    dispatcher["build_ast_for_file_content"] = build_ast_for_file_content
    dispatcher["get_random_variables"] = get_random_variables
    dispatcher["get_model"] = get_model
    dispatcher["get_guide"] = get_guide
    dispatcher["get_data_dependencies"] = get_data_dependencies
    dispatcher["get_control_dependencies"] = get_control_dependencies
    dispatcher["estimate_value_range"] = estimate_value_range
    dispatcher["get_call_graph"] = get_call_graph
    dispatcher["get_path_conditions"] = get_path_conditions
    
    dispatcher["ping"] = ping

    run_server(dispatcher)