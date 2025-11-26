from server import *
import sys
from jsonrpc import dispatcher
import os
from pathlib import Path
from jsonrpc_server import *


def run_server(socket_name, dispatcher):
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_name)
    try:
        while True:
            server.listen(1)
            sock, addr = server.accept()
            print("Hello", sock)
            reader = sock.makefile(mode='rb') # binary
            writer = sock.makefile(mode='wb') # binary
            handle_client(reader, writer, dispatcher)
            reader.close()
            writer.close()
            sock.close()
            clear_session()
            print("Bye", sock)
    except KeyboardInterrupt:
        print("Interrupt server.")
    finally:
        print("Close server.")
        server.close()
        os.remove(socket_name)
        

if __name__ == '__main__':
    # socket_name = sys.argv[1]
    Path("./.pipe").mkdir(exist_ok=True)
    socket_name = "./.pipe/python_rpc_socket"

    if os.path.exists(socket_name):
        os.remove(socket_name)

    print("Started Python Language Server", socket_name)

    dispatcher["build_ast"] = build_ast
    dispatcher["get_random_variables"] = get_random_variables
    dispatcher["get_model"] = get_model
    dispatcher["get_guide"] = get_guide
    dispatcher["get_data_dependencies"] = get_data_dependencies
    dispatcher["get_control_dependencies"] = get_control_dependencies
    dispatcher["estimate_value_range"] = estimate_value_range
    dispatcher["get_call_graph"] = get_call_graph
    dispatcher["get_path_conditions"] = get_path_conditions

    run_server(socket_name, dispatcher)