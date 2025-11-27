import sys
sys.path.insert(0, 'lasapp/src/static')

import argparse
import lasapp
import analysis.constraint_verification as constraint_verification
import json

if __name__ == '__main__':
    file_content = sys.stdin.read()
        
    # print(json.dumps([{"Hello": "world", "source": file_content}]))
    
    # parser = argparse.ArgumentParser()
    # parser.add_argument("filename", help="path to probabilistic program")
    # args = parser.parse_args()

    # filename = args.filename
    
    program = lasapp.ProbabilisticProgram("filename.py", file_content=file_content, n_unroll_loops=0)
    
    violations = constraint_verification.validate_distribution_arg_constraints(program)
    
    out = []
    for violation in violations:
        out.append({
            "start_index": violation.parameter.node.first_byte,
            "end_index": violation.parameter.node.last_byte,
            "description": violation.message(),
            # "info": {"file_content": file_content, "slice": file_content[10:25]}
        })

    print(json.dumps(out))