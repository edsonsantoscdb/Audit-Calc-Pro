"""
Motor de auditoria financeira (CET implícito, parcela justa, veredito).
Usado pela interface desktop e documentado para paridade com o app Android.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Union

from .financeiro_puro import is_bad_rate, pmt, rate


class StatusVeredito(Enum):
    OK = auto()
    ALERTA = auto()
    ERRO = auto()


@dataclass
class ResultadoAuditoria:
    cet_percent_am: float
    status: StatusVeredito
    mensagem: str
    diferenca_mensal: Optional[float]


@dataclass
class ErroAuditoria:
    mensagem: str


def auditar_financiamento(
    valor_veiculo: float,
    entrada: float,
    taxa_prometida_pct_am: float,
    parcela_cobrada: float,
    prazo_meses: int,
    taxa_vistoria: float,
    taxa_registro: float,
    seguro_prestamista: float = 0.0,
) -> Union[ResultadoAuditoria, ErroAuditoria]:
    """
    Replica a lógica de `investigar()` em interface.py.
    """
    if valor_veiculo <= 0:
        return ErroAuditoria("VALOR INVÁLIDO")

    valor_financiado = valor_veiculo - entrada
    if valor_financiado <= 0:
        return ErroAuditoria("ENTRADA > VEÍCULO")

    taxa_mes = rate(float(prazo_meses), float(parcela_cobrada), -valor_financiado, 0.0)
    if is_bad_rate(taxa_mes):
        return ErroAuditoria("DADOS INCONSISTENTES")

    cet_pct = taxa_mes * 100.0
    dif = cet_pct - taxa_prometida_pct_am

    if dif <= 0.15:
        status = StatusVeredito.OK
        msg = "NEGÓCIO DENTRO DA MÉDIA"
    elif dif <= 0.40:
        status = StatusVeredito.ALERTA
        msg = "TAXAS ACIMA DO ESPERADO"
    else:
        status = StatusVeredito.ERRO
        msg = "⚠️ TAXA MENTIROSA (Art. 39 CDC)"

    v_com_taxas = valor_financiado + taxa_vistoria + taxa_registro + seguro_prestamista
    parcela_justa = pmt(
        taxa_prometida_pct_am / 100.0, float(prazo_meses), -v_com_taxas, 0.0
    )

    if parcela_justa is None or is_bad_rate(parcela_justa):
        diff_mensal = None
    else:
        diff_mensal = max(0.0, parcela_cobrada - parcela_justa)

    return ResultadoAuditoria(
        cet_percent_am=cet_pct,
        status=status,
        mensagem=msg,
        diferenca_mensal=diff_mensal,
    )
