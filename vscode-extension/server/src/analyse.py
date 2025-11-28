import sys
sys.path.insert(0, 'lasapp/src/static')

import argparse
import lasapp
import analysis.constraint_verification as constraint_verification
import analysis.guide_validation as guide_validation
import analysis.hmc_assumptions_checker as hmc_assumptions_checker
import analysis.model_graph as model_graph
import json

import re
def strip_ansi(text):
    ansi_escape = re.compile(r'''
        \x1B  # ESC
        \[    # literal [
        [0-?]*  # Parameter bytes
        [ -/]*  # Intermediate bytes
        [@-~]   # Final byte
    ''', re.VERBOSE)
    return ansi_escape.sub('', text)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Analyse a Lasapp probabilistic program.")
    parser.add_argument("--constraint", action="store_true")
    parser.add_argument("--guide", action="store_true")
    parser.add_argument("--hmc", action="store_true")
    parser.add_argument("--graph", action="store_true")
    args = parser.parse_args()
    
    file_content = sys.stdin.read()
    
    program = lasapp.ProbabilisticProgram("filename.py", file_content=file_content, n_unroll_loops=0)
    
    out = []
    
    if args.guide:
        try:
            violations = guide_validation.check_proposal(program)
            for violation in violations:
                for range in violation.get_diagnostic_ranges():
                    out.append({
                        "start_index": range[0],
                        "end_index": range[1],
                        "description": strip_ansi(str(violation)),
                    })
        except: pass
    
    if args.constraint:
        try:
            violations = constraint_verification.validate_distribution_arg_constraints(program)
            for violation in violations:
                for range in violation.get_diagnostic_ranges():
                    out.append({
                        "start_index": range[0],
                        "end_index": range[1],
                        "description": strip_ansi(str(violation)),
                    })
        except: pass
        
    if args.hmc:
        try:
            violations = hmc_assumptions_checker.check_hmc_assumptions(program)
            for violation in violations:
                for range in violation.get_diagnostic_ranges():
                    out.append({
                        "start_index": range[0],
                        "end_index": range[1],
                        "description": strip_ansi(str(violation)),
                    })
        except: pass

    print(json.dumps(out))