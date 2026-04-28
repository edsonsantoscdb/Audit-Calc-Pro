"""
Gera uma chave aleatória e imprime o SQL para colar no Supabase (SQL Editor).

Uso (no PowerShell, na pasta do projeto):
  python scripts/gerar_chave_audit.py

Não precisa de internet — só copie o SQL gerado e rode no Supabase.
"""
from __future__ import annotations

import secrets
import string
import sys
from datetime import datetime, timedelta, timezone


def _gerar_chave() -> str:
    alfa = string.ascii_uppercase + string.digits
    a = "".join(secrets.choice(alfa) for _ in range(4))
    b = "".join(secrets.choice(alfa) for _ in range(4))
    c = "".join(secrets.choice(alfa) for _ in range(4))
    return f"AC-{a}-{b}-{c}"


def main():
    print("Audit Calc — gerador de chave para o Supabase\n")
    print("Escolha o tipo de passe:")
    print("  1 = Semanal (7 dias)")
    print("  2 = Mensal (30 dias)")
    print("  3 = Vitalício — só parceiros / propaganda (não anunciar ao público)")
    esc = input("\nDigite 1, 2 ou 3: ").strip()

    if esc not in ("1", "2", "3"):
        print("Opção inválida.")
        sys.exit(1)

    comprador = input("Nome ou telefone do comprador (para seu controle): ").strip()
    if not comprador:
        comprador = "N/I"

    comprador_sql = comprador.replace("'", "''")
    chave = _gerar_chave()

    if esc == "3":
        exp_sql = "NULL"
        tipo = "Vitalício"
    else:
        dias = 7 if esc == "1" else 30
        fim = datetime.now(timezone.utc) + timedelta(days=dias)
        fim = fim.replace(hour=23, minute=59, second=59, microsecond=0)
        exp_sql = f"'{fim.strftime('%Y-%m-%dT%H:%M:%S')}+00'"
        tipo = f"{dias} dias"

    sql = (
        f"INSERT INTO licencas (chave, ativo, expira_em, comprador) "
        f"VALUES ('{chave}', true, {exp_sql}, '{comprador_sql}');"
    )

    print("\n" + "=" * 60)
    print(f"Tipo: {tipo}")
    print(f"Chave (envie ao cliente): {chave}")
    print("=" * 60)
    print("\nCole o SQL abaixo no Supabase → SQL Editor → Run:\n")
    print(sql)
    print()


if __name__ == "__main__":
    main()
