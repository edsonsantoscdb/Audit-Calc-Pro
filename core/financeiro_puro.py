"""
Funções financeiras em Python puro (sem numpy / numpy-financial).
Compatíveis com o uso em motor_auditoria (PMT e RATE, pagamento no fim do período).
"""
from __future__ import annotations

import math
from typing import Optional


def _g_div_gp(r: float, n: float, p: float, x: float, y: float, w: float) -> float:
    """g/g' para Newton na RATE; when='end' → w=0 (numpy_financial)."""
    t1 = (r + 1) ** n
    t2 = (r + 1) ** (n - 1)
    g = y + t1 * x + p * (t1 - 1) * (r * w + 1) / r
    gp = (
        n * t2 * x
        - p * (t1 - 1) * (r * w + 1) / (r**2)
        + n * p * t2 * (r * w + 1) / r
        + p * (t1 - 1) * w / r
    )
    return g / gp


def rate(
    nper: float,
    pmt: float,
    pv: float,
    fv: float = 0,
    when: str = "end",
    guess: float = 0.1,
    tol: float = 1e-6,
    maxiter: int = 100,
) -> Optional[float]:
    """
    Taxa por período (equivalente a numpy_financial.rate, when='end', escalares).
    Devolve None se não convergir.
    """
    if when not in ("end", 0):
        raise NotImplementedError("only when='end' is supported")
    w = 0.0
    rn = float(guess)
    iterator = 0
    while iterator < maxiter:
        try:
            rnp1 = rn - _g_div_gp(rn, nper, pmt, pv, fv, w)
        except (ZeroDivisionError, OverflowError, ValueError):
            return None
        if not math.isfinite(rnp1):
            return None
        if abs(rnp1 - rn) < tol:
            return float(rnp1)
        rn = rnp1
        iterator += 1
    return None


def pmt(rate_per: float, nper: float, pv: float, fv: float = 0, when: str = "end") -> Optional[float]:
    """
    Prestação periódica (numpy_financial.pmt, when='end', escalares).
    """
    if when not in ("end", 0):
        raise NotImplementedError("only when='end' is supported")
    r = float(rate_per)
    n = float(nper)
    if n <= 0:
        return None
    if abs(r) < 1e-15:
        return -(fv + pv) / n
    temp = (1 + r) ** n
    fact = (temp - 1) / r
    if abs(fact) < 1e-15:
        return None
    return -(fv + pv * temp) / fact


def is_bad_rate(x: Optional[float]) -> bool:
    return x is None or (isinstance(x, float) and not math.isfinite(x))
