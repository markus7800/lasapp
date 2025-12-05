from pprint import pprint
from copy import deepcopy

def preproc_unsugar_tilde(sexpr):
    match sexpr:
        case [['stmt', ['Tilde', ['arg', samplearg], ['distribution', [['name', dist], idloc]], ['args', args], ['truncation', truncate]]], ['smeta', smeta]]:
            # print("arg", hide_loc_data(arg))
            # print(hide_loc_data(dist))
            # print("args", hide_loc_data(args))
            # print("truncate", hide_loc_data(truncate))

            sample = [['stmt', ['TargetPE',
                [['expr',
                    ['CondDistApp',
                    [],
                    [['name', f'{dist}_lpdf'], idloc],
                    [samplearg, *args]]],
                    ['emeta', [['loc', '<opaque>']]]
                ]]],
            ['smeta', smeta]
            ]
            
            trunc_args = []
            match truncate:
                case ['TruncateBetween', arg1, arg2]:
                    # print("truncate arg1", hide_loc_data(arg1))
                    # print("truncate arg2", hide_loc_data(arg2))
                    trunc_args = [arg1, arg2]
                case ['TruncateDownFrom', arg2]:
                    # print("truncate arg2", hide_loc_data(arg2))
                    trunc_args = [arg2]
                case ['TruncateUpFrom', arg1]:
                    # print("truncate arg2", hide_loc_data(arg1))
                    trunc_args = [arg1]

            # print(hide_loc_data(samplearg))
            # print([hide_loc_data(arg) for arg in trunc_args])
            if len(trunc_args) > 0:
                trunc = [['stmt', ['IfThenElse',
                    [['expr',
                        ['FunApp',
                            [],
                            [['name', 'outofbounds'], ['id_loc', '<opaque>']],
                            [deepcopy(samplearg), *trunc_args
                        ]]],
                        ['emeta', [['loc', '<opaque>']]]],
                    [['stmt', ['TargetPE', [['expr', ['FunApp', [], [['name', 'negative_infinity'], ['id_loc', '<opaque>']], []]], ['emeta', [['loc', '<opaque>']]]]]], ['smeta', [['loc', '<opaque>']]]],
                    []
                    ]],
                    ['smeta', [['loc', '<opaque>']]]
                ]
                ret = ['stmts', [sample, trunc]]
            else:
                ret = sample
            
            return ret

    if isinstance(sexpr, list):
        return [preproc_unsugar_tilde(child) for child in sexpr]
    else:
        return sexpr