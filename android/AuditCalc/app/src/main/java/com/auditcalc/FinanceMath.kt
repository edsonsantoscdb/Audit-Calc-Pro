package com.auditcalc

import kotlin.math.abs
import kotlin.math.pow

/**
 * Paridade com numpy_financial: [rate] e [pmt] no mesmo sentido usados em motor_auditoria.py
 * (rate com fv=0; pmt com convenção de sinal do Excel/numpy).
 */
object FinanceMath {

    /**
     * Taxa por período que zera: fv + pv*(1+r)^n + pmt*((1+r)^n - 1)/r
     * (quando `end`; mesma convenção do numpy_financial.rate).
     */
    fun rate(
        nper: Int,
        pmt: Double,
        pv: Double,
        fv: Double = 0.0,
        tol: Double = 1e-10,
        maxIter: Int = 200
    ): Double? {
        if (nper <= 0) return null

        fun f(r: Double): Double {
            if (abs(r) < 1e-15) return fv + pv + pmt * nper
            val rn = (1.0 + r).pow(nper)
            return fv + pv * rn + pmt * (rn - 1.0) / r
        }

        var lo = 1e-12
        var hi = 1.0
        var flo = f(lo)
        var fhi = f(hi)
        var expand = 0
        while (flo * fhi > 0 && expand < 40) {
            hi *= 1.5
            fhi = f(hi)
            expand++
        }
        if (flo * fhi > 0) return null

        var a = lo
        var b = hi
        var fa = flo
        var fb = fhi
        repeat(maxIter) {
            val mid = (a + b) / 2.0
            val fm = f(mid)
            if (abs(fm) < tol) return mid
            if (fa * fm <= 0) {
                b = mid
                fb = fm
            } else {
                a = mid
                fa = fm
            }
            if (abs(b - a) < tol) return (a + b) / 2.0
        }
        return (a + b) / 2.0
    }

    /**
     * Parcela por período (final do período), alinhada a numpy_financial.pmt.
     */
    fun pmt(rate: Double, nper: Int, pv: Double, fv: Double = 0.0): Double? {
        if (nper <= 0) return null
        if (abs(rate) < 1e-15) return -(pv + fv) / nper
        val rn = (1.0 + rate).pow(nper)
        return -rate * (pv * rn + fv) / (rn - 1.0)
    }
}
