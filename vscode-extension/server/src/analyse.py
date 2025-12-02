import sys
sys.path.insert(0, 'lasapp/src/static')

import argparse
import lasapp
import analysis.constraint_verification as constraint_verification
import analysis.guide_validation as guide_validation
import analysis.hmc_assumptions_checker as hmc_assumptions_checker
import analysis.funnel_detection as funnel_detection
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

def byte_index_to_char_index(utf8_s: bytes, byte_pos: int) -> int:
    byte_pos = min(max(byte_pos, 0), len(utf8_s))
    return len(utf8_s[:byte_pos].decode("utf-8", errors="ignore"))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Analyse a Lasapp probabilistic program.")
    parser.add_argument("--constraint", action="store_true")
    parser.add_argument("--guide", action="store_true")
    parser.add_argument("--hmc", action="store_true")
    parser.add_argument("--funnel", action="store_true")
    args = parser.parse_args()
    
    file_content = sys.stdin.read()
    utf8_s = file_content.encode("utf8")
    
    program = lasapp.ProbabilisticProgram("", file_content=file_content, n_unroll_loops=0)
    
    warnings = []
    
    if args.guide:
        try:
            warnings += guide_validation.check_proposal(program)
        except: pass
    
    if args.constraint:
        try:
            warnings += constraint_verification.validate_distribution_arg_constraints(program)
        except: pass
        
    if args.hmc:
        try:
            warnings += hmc_assumptions_checker.check_hmc_assumptions(program)
        except: pass
        
    if args.funnel:
        try:
            model = program.get_model()
            warnings += funnel_detection.get_funnel_relationships(program, model)
        except: pass
        
    
    out = []
    for warning in warnings:
        for range in warning.get_diagnostic_ranges():
            out.append({
                "start_index": byte_index_to_char_index(utf8_s, range[0]),
                "end_index": byte_index_to_char_index(utf8_s, range[1]),
                "description": strip_ansi(str(warning)),
            })

    print(json.dumps(out))