import sys
sys.path.insert(0, 'lasapp/src/ir4ppl')

import argparse
from stan.stan_cfg import *
from analysis.absolute_continuity_checker import check_ac, check_ac_guide
from analysis.funnel_detection import get_funnel_relationships
from analysis.constraint_verification import verify_constraints
from analysis.random_control_flow import check_for_random_control_flow
import json
import uuid
import pathlib
import os

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
    parser = argparse.ArgumentParser(description="Analyse a Stan probabilistic program.")
    parser.add_argument("stanc")
    parser.add_argument("--constraint", action="store_true")
    parser.add_argument("--guide", action="store_true")
    parser.add_argument("--hmc", action="store_true")
    parser.add_argument("--funnel", action="store_true")
    args = parser.parse_args()
    
    file_content = sys.stdin.read()
    utf8_s = file_content.encode("utf8")
    

    pathlib.Path(".pipe", "tmp").mkdir(exist_ok=True)
    uid = str(uuid.uuid4())[:8]
    filename = pathlib.Path(".pipe", "tmp", f"{uid}.stan")
    hppname = pathlib.Path(".pipe", "tmp", f"{uid}.hpp")
    with open(filename, "w") as f:
        f.write(file_content)
    
    try:
        # currently only stan
        ir = get_IR_for_stan(filename, stanc=args.stanc)
    finally:
        if filename.exists():
            os.remove(filename)
        if hppname.exists():
            os.remove(hppname)
        
    warnings = []
    
    if args.guide:
        pass # not supported for stan
    
    if args.constraint:
        try:
            result, can_be_analyzed = verify_constraints(ir)
            if can_be_analyzed:
                warnings += result
        except: pass
        
    if args.hmc:
        try:
            warnings += check_for_random_control_flow(ir)
        except: pass
        
    if args.funnel:
        try:
            warnings += get_funnel_relationships(ir)
        except:
            pass
        
    
    out = []
    for warning in warnings:
        for range in warning.get_diagnostic_ranges():
            out.append({
                "start_index": byte_index_to_char_index(utf8_s, range[0]),
                "end_index": byte_index_to_char_index(utf8_s, range[1]),
                "description": strip_ansi(str(warning)),
            })

    print(json.dumps(out))