package com.auditcalc

/**
 * Mesma regra de negócio que [motor_auditoria.auditar_financiamento] (Python).
 */
object AuditEngine {

    enum class Status { OK, ALERTA, ERRO }

    sealed class Result {
        data class Success(
            val cetPercentAm: Double,
            val status: Status,
            val mensagem: String,
            val diferencaMensal: Double?
        ) : Result()

        data class Error(val mensagem: String) : Result()
    }

    fun auditar(
        valorVeiculo: Double,
        entrada: Double,
        taxaPrometidaPctAm: Double,
        parcelaCobrada: Double,
        prazoMeses: Int,
        taxaVistoria: Double,
        taxaRegistro: Double
    ): Result {
        if (valorVeiculo <= 0) return Result.Error("VALOR INVÁLIDO")

        val valorFinanciado = valorVeiculo - entrada
        if (valorFinanciado <= 0) return Result.Error("ENTRADA > VEÍCULO")

        val taxaMes = FinanceMath.rate(prazoMeses, parcelaCobrada, -valorFinanciado, 0.0)
            ?: return Result.Error("DADOS INCONSISTENTES")

        val cetPct = taxaMes * 100.0
        val dif = cetPct - taxaPrometidaPctAm

        val (status, msg) = when {
            dif <= 0.15 -> Status.OK to "NEGÓCIO DENTRO DA MÉDIA"
            dif <= 0.40 -> Status.ALERTA to "TAXAS ACIMA DO ESPERADO"
            else -> Status.ERRO to "TAXA MENTIROSA (Art. 39 CDC)"
        }

        val vComTaxas = valorFinanciado + taxaVistoria + taxaRegistro
        val parcelaJusta = FinanceMath.pmt(taxaPrometidaPctAm / 100.0, prazoMeses, -vComTaxas, 0.0)

        val diffMensal = parcelaJusta?.let { maxOf(0.0, parcelaCobrada - it) }

        return Result.Success(
            cetPercentAm = cetPct,
            status = status,
            mensagem = msg,
            diferencaMensal = diffMensal
        )
    }
}
