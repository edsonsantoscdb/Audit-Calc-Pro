import numpy_financial as npf

def motor_dedo_duro(valor_veiculo, entrada, prazo, taxa_prometida, parcela_cobrada):
    valor_financiado = valor_veiculo - entrada
    taxa_decimal = taxa_prometida / 100

    # 1. Cálculos Base
    parcela_justa = npf.pmt(taxa_decimal, prazo, -valor_financiado)
    taxa_real_decimal = npf.rate(prazo, parcela_cobrada, -valor_financiado, 0)
    taxa_real = taxa_real_decimal * 100
    
    diferenca_mensal = parcela_cobrada - parcela_justa
    custo_oculto_total = diferenca_mensal * prazo
    diferenca_taxa = taxa_real - taxa_prometida

    # 2. O JUIZ
    print("=" * 60)
    if diferenca_taxa <= 0.05:
        print("✅ TUDO CERTO! Negócio Justo.")
    elif diferenca_taxa <= 0.30:
        print("⚠️ ATENÇÃO: Taxa Enganosa Detectada!")
    else:
        print("🚨 ALERTA: TAXA MENTIROSA! 🚨")
    print("=" * 60)
    print(f"Custo Efetivo Total (CET): {taxa_real:.2f}% a.m.")
    print(f"Diferença da Promessa:     + {diferenca_taxa:.2f}% a.m.")
    print(f"Total de Custos Ocultos:   R$ {custo_oculto_total:.2f}")
    
    # 3. DETALHAMENTO DA AMORTIZAÇÃO (Tabela Price)
    print("\n" + "=" * 60)
    print(" 📊 DETALHAMENTO: PARA ONDE VAI SEU DINHEIRO (5 PRIMEIROS MESES)")
    print("=" * 60)
    print(f"{'Mês':<5} | {'Juros Pagos':<15} | {'Amortização (Carro)':<20} | {'Saldo Devedor'}")
    print("-" * 60)
    
    saldo_devedor = valor_financiado
    
    # Loop que calcula mês a mês até acabar o prazo
    for mes in range(1, prazo + 1):
        juros_do_mes = saldo_devedor * taxa_real_decimal
        amortizacao_do_mes = parcela_cobrada - juros_do_mes
        saldo_devedor = saldo_devedor - amortizacao_do_mes
        
        # Imprime apenas os 5 primeiros meses para não inundar a tela
        if mes <= 5:
            print(f"{mes:<5} | R$ {juros_do_mes:<12.2f} | R$ {amortizacao_do_mes:<17.2f} | R$ {max(0, saldo_devedor):.2f}")
            
    print("=" * 60)

# Testando com os mesmos dados
motor_dedo_duro(75000, 15000, 48, 1.29, 2150.00)