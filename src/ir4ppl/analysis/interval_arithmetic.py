#%%
import math
from typing import Any, Optional
from collections import deque
from copy import copy

class Interval:
    def __init__(self, low: float, high: Optional[float] = None) -> None:
        self.low = low        
        self.high = high if high is not None else low
    def __repr__(self):
        return f"[{self.low}, {self.high}]"
    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, Interval):
            return False
        else:
            return self.low == __value.low and self.high == __value.high
    def __hash__(self) -> int:
        return hash((self.low, self.high))

def interval_add(x: Interval, y: Interval) -> Interval:
    return Interval(x.low + y.low, x.high + y.high)

def interval_sub(x: Interval, y: Interval) -> Interval:
    return Interval(x.low - y.high, x.high - y.low)

def interval_usub(x: Interval) -> Interval:
    return Interval(-x.high, -x.low)

def interval_mul(x: Interval, y: Interval) -> Interval:
    E = [x.low * y.low, x.low * y.high, x.high * y.low, x.high * y.high]
    E = [e for e in E if not math.isnan(e)]
    return Interval(min(E), max(E))

def interval_div(x: Interval, y: Interval) -> Interval:
    if y.low == -math.inf and y.high == math.inf:
        # 1/y.high, 1/y.low == 0, 0
        return Interval(-math.inf, math.inf)
    
    if y.low != 0 and y.high != 0:
        y = Interval(1/y.high, 1/y.low)
    elif y.low != 0:
        y = Interval(-math.inf, 1/y.low)
    elif y.high != 0:
        y = Interval(1/y.high, math.inf)
    else:
        raise ValueError("Division by zero.")
    
    return interval_mul(x, y)

def interval_pow(x: Interval, y: Interval) -> Interval:
    if isinstance(y, Interval):
        if y.low == y.high:
            n = y.low
        else:
            return Interval(-math.inf, math.inf)

    if n % 2 != 0:
        return Interval(x.low ** n, x.high ** n)
    else:
        if x.low >= 0:
            return Interval(x.low ** n, x.high ** n)
        else:
            return Interval(0., x.high ** n)

# monotone

def interval_minimum(*xs: Interval) -> Interval:
    return Interval(min([x.low for x in xs]), min([x.high for x in xs]))

def interval_maximum(*xs: Interval) -> Interval:
    return Interval(max([x.low for x in xs]), max([x.high for x in xs]))

def interval_sqrt(x: Interval) -> Interval:
    return Interval(math.sqrt(max(0,x.low)), math.sqrt(x.high))

def interval_square(x: Interval) -> Interval:
    return interval_pow(x, Interval(2,2))

def interval_log(x: Interval) -> Interval:
    low = math.log(x.low) if x.low > 0 else -math.inf
    high = math.log(x.high) if x.high > 0 else -math.inf

    return Interval(low, high)

class IntervalMonotoneOp:
    def __init__(self, op) -> None:
        self.op = op
    def __call__(self, *args) -> Interval:
        return Interval(self.op(*[arg.low for arg in args]), self.op(*[arg.high for arg in args]))

class StaticRangeOp:
    def __init__(self, range: Interval) -> None:
        self.range = range
    def __call__(self, *args) -> Interval:
        return self.range

def interval_exp(x: Interval) -> Interval:
    return Interval(math.exp(x.low), math.exp(x.high))

def interval_union(x: Interval, y: Interval) -> Interval:
    return Interval(min(x.low, y.low), max(x.high, y.high)) # over-approximate if disjoint

def interval_abs(x: Interval) -> Interval:
    return Interval(min(abs(x.low), abs(x.high)), max(abs(x.low), abs(x.high))) # over-approximate if disjoint
    
def interval_ifelse(test: Interval, x: Interval, y: Interval) -> Interval:
    return interval_union(x, y)

def interval_invlogit(x: Interval) -> Interval:
    return Interval(0, 1)

def interval_eq(x: Interval, y: Interval) -> Interval:
    return Interval(0, 1)

def interval_no_op(x: Interval, *args) -> Interval:
    return x

def interval_clip(x: Interval, a: Interval, b:Interval) -> Interval:
    return Interval(a.low, b.high)

def interval_erf(x: Interval) -> Interval:
    return Interval(-1, 1)

def interval_ones(*args) -> Interval:
    return Interval(1.,1.)

def interval_prod(x: Interval) -> Interval:
    # x is array
    if 0 <= x.low and x.high <= 1:
        return Interval(0.,1.) # product of aribtrary many 0<=x<=1 is in [0,1]
    return Interval(-math.inf,math.inf)

# Identity Matrix
def interval_eye(*args) -> Interval:
    return Interval(0.,1.)

def interval_real(*args) -> Interval:
    return Interval(float('-inf'),float('inf'))

def interval_pos(*args) -> Interval:
    return Interval(0,float('inf'))
# %%
