import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.motor_auditoria import ErroAuditoria, StatusVeredito, auditar_financiamento

# --- 1. PALETA (slate + índigo, contraste suave) ---
ctk.set_appearance_mode("dark")
COR_FUNDO = "#0f172a"           # slate-900
COR_INPUT = "#0c1424"           # campos um pouco mais profundos
COR_CARD = "#1e293b"            # slate-800
COR_SUPERIOR = "#1e293b"        # painel alinhado ao cartão
COR_ACENTO = "#3b82f6"          # azul um pouco mais claro (leitura)
COR_ACENTO_HOVER = "#2563eb"
COR_ACENTO_MUTED = "#60a5fa"
COR_SUCESSO = "#22c55e"
COR_ALERTA = "#eab308"
COR_ERRO = "#f87171"
COR_TEXTO = "#f8fafc"
COR_TEXTO_SEC = "#94a3b8"
BORDA_COR = "#475569"
BORDA_FOCO = "#64748b"
COR_HEADER = "#1e1b4b"          # índigo escuro

ctk.set_default_color_theme("dark-blue")
ctk.set_widget_scaling(1.0)

# Memória Global
sessao = {
    "loja": "", "vendedor": "", "ano": "", "modelo": "",
    "avaliacao": 750.00, "registro": 350.00
}

# --- RAIZ DO PROJETO (imagens e CSV ficam na pasta CALCULADORA) ---
if getattr(sys, 'frozen', False):
    diretorio_script = os.path.dirname(sys.executable)
else:
    diretorio_script = str(_ROOT)

CAMINHO_FOTO_CARRO = os.path.join(diretorio_script, "carro.png")
CAMINHO_FOTO_MOTO = os.path.join(diretorio_script, "moto.png")

# --- FUNÇÕES DE UTILIDADE ---

def formatar_brl(valor):
    try:
        return f"R$ {valor:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    except:
        return "R$ 0,00"

class MoedaEntry(ctk.CTkEntry):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.bind("<KeyRelease>", self.aplicar_mascara)
        self.bind("<FocusOut>", self.aplicar_mascara_completa)
        self.valor_float = 0.0
        
    def aplicar_mascara(self, event=None):
        texto_bruto = self.get().replace("R$ ", "").replace(".", "").replace(",", "")
        texto_bruto = ''.join(filter(str.isdigit, texto_bruto))
        
        if texto_bruto:
            self.valor_float = float(texto_bruto) / 100
            self._atualizar_texto()
        else:
            self.valor_float = 0.0
            self.delete(0, "end")
            self.insert(0, "R$ 0,00")
    
    def aplicar_mascara_completa(self, event=None):
        self._atualizar_texto()
    
    def _atualizar_texto(self):
        self.delete(0, "end")
        self.insert(0, formatar_brl(self.valor_float))
    
    def get_float(self):
        return self.valor_float

def caminho_historico_csv():
    return os.path.join(diretorio_script, "historico_auditoria.csv")

def obter_proximo_id():
    arquivo = caminho_historico_csv()
    if not os.path.exists(arquivo):
        return 1
    try:
        with open(arquivo, "r", encoding="utf-8") as f:
            return len(f.readlines()) + 1
    except Exception:
        return 1

def _avaliar_expressao_calc(s):
    """Apenas dígitos e operadores básicos; evita eval arbitrário."""
    s = "".join(s.split()).replace(",", ".")
    if not s:
        return None
    permitido = set("0123456789+-*/.()")
    if not all(c in permitido for c in s):
        return None
    try:
        return eval(s, {"__builtins__": {}}, {})
    except Exception:
        return None

def _limpar_overlay(overlay):
    for w in overlay.winfo_children():
        w.destroy()

def montar_calculadora_no_overlay(overlay, ao_voltar):
    """Calculadora sobre o painel de parâmetros (mesma janela)."""
    _limpar_overlay(overlay)

    estado = {"expr": ""}

    topo = ctk.CTkFrame(overlay, fg_color=COR_HEADER, corner_radius=0, height=48)
    topo.pack(fill="x")
    topo_inner = ctk.CTkFrame(topo, fg_color="transparent")
    topo_inner.pack(fill="x", padx=8, pady=8)
    ctk.CTkButton(
        topo_inner, text="← Voltar", width=88, height=32, corner_radius=8,
        fg_color=COR_CARD, hover_color=BORDA_FOCO, text_color=COR_TEXTO,
        font=("Segoe UI", 12), command=ao_voltar
    ).pack(side="left")
    ctk.CTkLabel(
        topo_inner, text="Calculadora", font=("Segoe UI", 15, "bold"), text_color=COR_TEXTO
    ).pack(side="left", padx=12)

    display = ctk.CTkLabel(
        overlay, text="0", font=("Segoe UI", 26), anchor="e",
        fg_color=COR_CARD, corner_radius=12, height=56,
        text_color=COR_TEXTO, padx=14
    )
    display.pack(fill="x", padx=14, pady=(12, 10))

    def atualizar():
        t = estado["expr"]
        display.configure(text=t if t else "0")

    def digito(ch):
        estado["expr"] += ch
        atualizar()

    def limpar():
        estado["expr"] = ""
        atualizar()

    def back():
        estado["expr"] = estado["expr"][:-1]
        atualizar()

    def igual():
        r = _avaliar_expressao_calc(estado["expr"])
        if r is None:
            estado["expr"] = ""
            display.configure(text="Erro")
            return
        if isinstance(r, float) and r == int(r):
            estado["expr"] = str(int(r))
        else:
            estado["expr"] = str(round(r, 8)).rstrip("0").rstrip(".")
        atualizar()

    grade = ctk.CTkFrame(overlay, fg_color="transparent")
    grade.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    estilo_num = {"fg_color": COR_CARD, "hover_color": BORDA_FOCO, "text_color": COR_TEXTO,
                  "font": ("Segoe UI", 16), "corner_radius": 10, "height": 44}
    estilo_op = {"fg_color": "#1e293b", "hover_color": BORDA_FOCO, "text_color": COR_ACENTO_MUTED,
                 "font": ("Segoe UI", 16, "bold"), "corner_radius": 10, "height": 44}
    estilo_igual = {"fg_color": COR_ACENTO, "hover_color": COR_ACENTO_HOVER, "text_color": "#fff",
                    "font": ("Segoe UI", 16, "bold"), "corner_radius": 10, "height": 44}

    linhas = [
        [("C", limpar, estilo_op), ("⌫", back, estilo_op), ("(", lambda: digito("("), estilo_op), (")", lambda: digito(")"), estilo_op)],
        [("7", lambda: digito("7"), estilo_num), ("8", lambda: digito("8"), estilo_num), ("9", lambda: digito("9"), estilo_num), ("/", lambda: digito("/"), estilo_op)],
        [("4", lambda: digito("4"), estilo_num), ("5", lambda: digito("5"), estilo_num), ("6", lambda: digito("6"), estilo_num), ("*", lambda: digito("*"), estilo_op)],
        [("1", lambda: digito("1"), estilo_num), ("2", lambda: digito("2"), estilo_num), ("3", lambda: digito("3"), estilo_num), ("-", lambda: digito("-"), estilo_op)],
        [("0", lambda: digito("0"), estilo_num), (".", lambda: digito("."), estilo_num), ("=", igual, estilo_igual), ("+", lambda: digito("+"), estilo_op)],
    ]

    for r, row in enumerate(linhas):
        for c, (txt, cmd, est) in enumerate(row):
            b = ctk.CTkButton(grade, text=txt, command=cmd, **est)
            b.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
    for i in range(4):
        grade.grid_columnconfigure(i, weight=1)

def montar_historico_no_overlay(overlay, ao_voltar):
    """Lista o CSV de histórico sobre o painel de parâmetros."""
    _limpar_overlay(overlay)

    topo = ctk.CTkFrame(overlay, fg_color=COR_HEADER, corner_radius=0, height=48)
    topo.pack(fill="x")
    topo_inner = ctk.CTkFrame(topo, fg_color="transparent")
    topo_inner.pack(fill="x", padx=8, pady=8)
    ctk.CTkButton(
        topo_inner, text="← Voltar", width=88, height=32, corner_radius=8,
        fg_color=COR_CARD, hover_color=BORDA_FOCO, text_color=COR_TEXTO,
        font=("Segoe UI", 12), command=ao_voltar
    ).pack(side="left")
    ctk.CTkLabel(
        topo_inner, text="Histórico gravado", font=("Segoe UI", 15, "bold"), text_color=COR_TEXTO
    ).pack(side="left", padx=12)

    scroll = ctk.CTkScrollableFrame(overlay, fg_color=COR_CARD, corner_radius=12)
    scroll.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    arq = caminho_historico_csv()
    if not os.path.exists(arq) or os.path.getsize(arq) == 0:
        ctk.CTkLabel(
            scroll, text="Nenhum registro ainda.\nUse «Gravar histórico» após auditar na tela principal.",
            font=("Segoe UI", 12), text_color=COR_TEXTO_SEC, justify="left"
        ).pack(anchor="w", padx=12, pady=12)
        return

    try:
        with open(arq, "r", encoding="utf-8") as f:
            leitor = csv.reader(f)
            linhas = list(leitor)
    except Exception as e:
        ctk.CTkLabel(scroll, text=f"Erro ao ler arquivo: {e}", text_color=COR_ERRO).pack(padx=12, pady=12)
        return

    for i, cols in enumerate(linhas):
        texto = "  ·  ".join(cols) if cols else ""
        cor = COR_TEXTO if i == 0 else COR_TEXTO_SEC
        fonte = ("Segoe UI", 11, "bold") if i == 0 else ("Segoe UI", 11)
        ctk.CTkLabel(
            scroll, text=texto, font=fonte, text_color=cor,
            anchor="w", justify="left", wraplength=360
        ).pack(fill="x", padx=10, pady=4)

# --- 2. TELA DE CONFIGURAÇÕES ---
def abrir_configuracoes():
    global lbl_cet, lbl_alerta
    
    janela_config = ctk.CTkToplevel(janela)
    janela_config.title("Configurações - Audit Calc")
    janela_config.geometry("440x720")
    janela_config.attributes("-topmost", True)
    janela_config.configure(fg_color=COR_FUNDO)

    # Cabeçalho: Voltar | título | foto da moto
    header = ctk.CTkFrame(janela_config, fg_color=COR_HEADER, height=72, corner_radius=0)
    header.pack(fill="x")
    header_inner = ctk.CTkFrame(header, fg_color="transparent")
    header_inner.pack(fill="both", expand=True, padx=10, pady=10)
    header_inner.grid_columnconfigure(1, weight=1)

    ctk.CTkButton(
        header_inner, text="← Voltar", width=78, height=34, corner_radius=8,
        fg_color=COR_CARD, hover_color=BORDA_FOCO, text_color=COR_TEXTO,
        font=("Segoe UI", 12), command=janela_config.destroy
    ).grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 6))

    tit_wrap = ctk.CTkFrame(header_inner, fg_color="transparent")
    tit_wrap.grid(row=0, column=1, rowspan=2, sticky="w")
    ctk.CTkLabel(
        tit_wrap, text="Parâmetros da auditoria",
        font=("Segoe UI", 17, "bold"), text_color=COR_TEXTO
    ).pack(anchor="w")
    ctk.CTkLabel(
        tit_wrap, text="Dados do protocolo e taxas fixas",
        font=("Segoe UI", 11), text_color=COR_TEXTO_SEC
    ).pack(anchor="w")

    if os.path.exists(CAMINHO_FOTO_MOTO):
        try:
            img_moto_data = Image.open(CAMINHO_FOTO_MOTO)
            img_moto_data = img_moto_data.resize((88, 88), Image.Resampling.LANCZOS)
            img_moto = ctk.CTkImage(light_image=img_moto_data, dark_image=img_moto_data, size=(88, 88))
            janela_config._img_moto_ref = img_moto
            ctk.CTkLabel(header_inner, image=img_moto, text="", fg_color=COR_CARD, corner_radius=12).grid(
                row=0, column=2, rowspan=2, padx=(8, 0), sticky="e"
            )
        except Exception as e:
            print(f"Erro na imagem da moto: {e}")

    main_stack = ctk.CTkFrame(janela_config, fg_color=COR_FUNDO)
    main_stack.pack(fill="both", expand=True)

    corpo = ctk.CTkFrame(main_stack, fg_color="transparent")
    corpo.pack(pady=15, padx=24, fill="both", expand=True)

    overlay = ctk.CTkFrame(main_stack, fg_color=COR_FUNDO)

    def fechar_overlay():
        overlay.place_forget()
        _limpar_overlay(overlay)

    def abrir_overlay_calc():
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        montar_calculadora_no_overlay(overlay, fechar_overlay)

    def abrir_overlay_historico():
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        montar_historico_no_overlay(overlay, fechar_overlay)

    def criar_campo_texto(label, chave):
        ctk.CTkLabel(corpo, text=label, font=("Segoe UI", 11), text_color=COR_TEXTO_SEC).pack(anchor="w")
        ent = ctk.CTkEntry(corpo, height=38, corner_radius=8, border_color=BORDA_COR, fg_color=COR_CARD)
        ent.insert(0, str(sessao[chave]))
        ent.pack(pady=(5, 12), fill="x")
        return ent
    
    def criar_campo_moeda(label, chave):
        ctk.CTkLabel(corpo, text=label, font=("Segoe UI", 11), text_color=COR_TEXTO_SEC).pack(anchor="w")
        ent = MoedaEntry(corpo, height=38, corner_radius=8, border_color=BORDA_COR, fg_color=COR_CARD)
        ent.valor_float = sessao[chave]
        ent._atualizar_texto()
        ent.pack(pady=(5, 12), fill="x")
        return ent

    ent_loja = criar_campo_texto("Nome da Loja", "loja")
    ent_vendedor = criar_campo_texto("Nome do Vendedor", "vendedor")
    ent_ano = criar_campo_texto("Ano do Veículo", "ano")
    ent_modelo = criar_campo_texto("Modelo do Veículo", "modelo")
    ent_av = criar_campo_moeda("Taxa de Vistoria (R$)", "avaliacao")
    ent_reg = criar_campo_moeda("Taxa de Registro (R$)", "registro")

    def salvar_tudo():
        sessao.update({
            "loja": ent_loja.get(),
            "vendedor": ent_vendedor.get(),
            "ano": ent_ano.get(),
            "modelo": ent_modelo.get(),
            "avaliacao": ent_av.get_float(),
            "registro": ent_reg.get_float()
        })
        
        p_id = obter_proximo_id()
        arq = caminho_historico_csv()
        try:
            novo = not os.path.exists(arq) or os.path.getsize(arq) == 0
            with open(arq, "a", newline="", encoding="utf-8") as f:
                cet_texto = lbl_cet.cget("text")
                cet_limpo = cet_texto.replace("% a.m.", "").strip()
                escritor = csv.writer(f)
                if novo:
                    escritor.writerow(["ID", "Data", "Loja", "Modelo", "CET"])
                escritor.writerow([p_id, datetime.now().strftime("%d/%m/%Y %H:%M"),
                                 sessao["loja"], sessao["modelo"], cet_limpo])
        except Exception as e:
            print(f"Erro ao salvar: {e}")
            return

        lbl_alerta.configure(text=f"✅ PROTOCOLO {p_id} REGISTRADO", text_color=COR_SUCESSO)

    row_acoes = ctk.CTkFrame(corpo, fg_color="transparent")
    row_acoes.pack(pady=(10, 8), fill="x", side="bottom")
    row_acoes.grid_columnconfigure((0, 1, 2), weight=1, uniform="acoes")

    est_gravar = {"height": 52, "corner_radius": 10, "font": ("Segoe UI", 11, "bold"),
                  "fg_color": COR_ACENTO, "hover_color": COR_ACENTO_HOVER, "text_color": "#fff"}
    est_sec = {"height": 52, "corner_radius": 10, "font": ("Segoe UI", 11),
               "fg_color": COR_CARD, "hover_color": BORDA_FOCO, "text_color": COR_TEXTO,
               "border_width": 1, "border_color": BORDA_COR}

    ctk.CTkButton(row_acoes, text="Gravar\nhistórico", command=salvar_tudo, **est_gravar).grid(
        row=0, column=0, padx=(0, 4), sticky="nsew"
    )
    ctk.CTkButton(row_acoes, text="Abrir\nhistórico", command=abrir_overlay_historico, **est_sec).grid(
        row=0, column=1, padx=4, sticky="nsew"
    )
    ctk.CTkButton(row_acoes, text="Calculadora", command=abrir_overlay_calc, **est_sec).grid(
        row=0, column=2, padx=(4, 0), sticky="nsew"
    )

# --- 3. MOTOR DE CÁLCULO ---
def investigar():
    try:
        t_pro = float(input_taxa.get().replace(',', '.'))
        prazo = int(slider_prazo.get())
        out = auditar_financiamento(
            input_veiculo.get_float(),
            input_entrada.get_float(),
            t_pro,
            input_parcela.get_float(),
            prazo,
            sessao["avaliacao"],
            sessao["registro"],
        )
        if isinstance(out, ErroAuditoria):
            lbl_alerta.configure(text=out.mensagem, text_color=COR_ERRO)
            return

        cor_status = {
            StatusVeredito.OK: COR_SUCESSO,
            StatusVeredito.ALERTA: COR_ALERTA,
            StatusVeredito.ERRO: COR_ERRO,
        }[out.status]

        frame_veredito.configure(border_color=cor_status)
        lbl_alerta.configure(text=out.mensagem, text_color=cor_status)
        lbl_cet.configure(text=f"{out.cet_percent_am:.2f}% a.m.")

        if out.diferenca_mensal is not None:
            lbl_gordura.configure(text=f"Diferença: {formatar_brl(out.diferenca_mensal)}")
        else:
            lbl_gordura.configure(text="Diferença: não calculável")

    except Exception as e:
        print(f"Erro: {e}")
        lbl_alerta.configure(text="VERIFIQUE OS DADOS", text_color=COR_ERRO)

# --- 4. INTERFACE PRINCIPAL ---
janela = ctk.CTk()
janela.title("AUDIT CALC - Auditoria Financeira")
janela.geometry("460x880")
janela.configure(fg_color=COR_FUNDO)
janela.resizable(False, False)

# ========== CABEÇALHO (faixa índigo + ícone do carro à esquerda) ==========
header_frame = ctk.CTkFrame(janela, fg_color=COR_HEADER, height=78, corner_radius=0)
header_frame.pack(fill="x")
header_row = ctk.CTkFrame(header_frame, fg_color="transparent")
header_row.pack(fill="both", expand=True, padx=12, pady=10)
header_row.grid_columnconfigure(1, weight=1)

if os.path.exists(CAMINHO_FOTO_CARRO):
    try:
        img_carro_data = Image.open(CAMINHO_FOTO_CARRO)
        img_carro_data = img_carro_data.resize((52, 52), Image.Resampling.LANCZOS)
        img_carro = ctk.CTkImage(light_image=img_carro_data, dark_image=img_carro_data, size=(52, 52))
        janela._img_carro_ref = img_carro
        ctk.CTkLabel(header_row, image=img_carro, text="", fg_color=COR_CARD, corner_radius=10).grid(
            row=0, column=0, rowspan=2, padx=(0, 10)
        )
    except Exception as e:
        print(f"Erro na imagem do carro: {e}")

titulo_container = ctk.CTkFrame(header_row, fg_color="transparent")
titulo_container.grid(row=0, column=1, rowspan=2, sticky="w")

lbl_titulo = ctk.CTkLabel(titulo_container, text="AUDIT CALC",
                          font=("Segoe UI", 22, "bold"),
                          text_color=COR_TEXTO)
lbl_titulo.pack(anchor="w")

lbl_sub = ctk.CTkLabel(titulo_container, text="Financial Audit System",
                       font=("Segoe UI", 9, "italic"), text_color="#a5b4fc")
lbl_sub.pack(anchor="w")

btn_config = ctk.CTkButton(
    header_row, text="⚙", width=40, height=40,
    fg_color=COR_CARD, text_color=COR_TEXTO,
    hover_color=BORDA_FOCO, corner_radius=10,
    font=("Segoe UI", 18), command=abrir_configuracoes
)
btn_config.grid(row=0, column=2, rowspan=2, sticky="e")

# ========== CORPO PRINCIPAL ==========
body_frame = ctk.CTkFrame(
    janela, fg_color=COR_SUPERIOR, corner_radius=20,
    border_width=1, border_color="#334155"
)
body_frame.pack(pady=18, padx=22, fill="both", expand=True)

def criar_input_moeda(label):
    ctk.CTkLabel(body_frame, text=label, font=("Segoe UI", 11, "bold"), 
                 text_color=COR_TEXTO_SEC).pack(anchor="w", padx=20)
    ent = MoedaEntry(body_frame, height=44, corner_radius=12,
                     border_color=BORDA_COR, border_width=1,
                     fg_color=COR_INPUT, font=("Segoe UI", 13))
    ent.pack(pady=(3, 12), padx=20, fill="x")
    return ent

def criar_input_texto(label):
    ctk.CTkLabel(body_frame, text=label, font=("Segoe UI", 11, "bold"), 
                 text_color=COR_TEXTO_SEC).pack(anchor="w", padx=20)
    ent = ctk.CTkEntry(body_frame, height=44, corner_radius=12,
                       border_color=BORDA_COR, border_width=1,
                       fg_color=COR_INPUT, font=("Segoe UI", 13))
    ent.pack(pady=(3, 12), padx=20, fill="x")
    return ent

input_veiculo = criar_input_moeda("Valor do Veículo")
input_entrada = criar_input_moeda("Valor da Entrada")
input_taxa = criar_input_texto("Taxa Prometida (% a.m.)")
input_parcela = criar_input_moeda("Parcela do Contrato")

# Slider de prazo
ctk.CTkLabel(body_frame, text="Prazo do Financiamento", font=("Segoe UI", 11, "bold"),
             text_color=COR_TEXTO_SEC).pack(anchor="w", padx=20)
lbl_prazo_v = ctk.CTkLabel(body_frame, text="48 MESES", font=("Segoe UI", 14, "bold"), 
                          text_color=COR_ACENTO)
lbl_prazo_v.pack(pady=(3, 0))

def atualizar_prazo(v):
    lbl_prazo_v.configure(text=f"{int(v)} MESES")

# 6 a 72 meses (66 intervalos)
slider_prazo = ctk.CTkSlider(
    body_frame, from_=6, to=72, number_of_steps=66,
    command=atualizar_prazo, button_color=COR_ACENTO,
    progress_color=COR_ACENTO, button_hover_color=COR_ACENTO_HOVER,
    fg_color="#334155", height=18
)
slider_prazo.set(48)
slider_prazo.pack(padx=20, pady=8, fill="x")

# Painel de resultado (criado antes dos botões para o reset poder atualizar os labels)
frame_veredito = ctk.CTkFrame(
    body_frame, fg_color="#162032", corner_radius=18,
    border_width=1, border_color=BORDA_FOCO
)

lbl_alerta = ctk.CTkLabel(frame_veredito, text="AGUARDANDO ANÁLISE",
                          font=("Segoe UI", 11, "bold"), text_color=COR_TEXTO_SEC)
lbl_alerta.pack(pady=(15, 5))

lbl_cet = ctk.CTkLabel(frame_veredito, text="--.--%",
                       font=("Segoe UI", 44, "bold"), text_color=COR_ACENTO_MUTED)
lbl_cet.pack()

lbl_gordura = ctk.CTkLabel(frame_veredito, text="Diferença mensal: --",
                           font=("Segoe UI", 11), text_color=COR_TEXTO_SEC)
lbl_gordura.pack(pady=(5, 15))


def resetar_pesquisa():
    """Limpa todos os campos da tela principal e o resultado, sem gravar nada."""
    input_veiculo.valor_float = 0.0
    input_veiculo._atualizar_texto()
    input_entrada.valor_float = 0.0
    input_entrada._atualizar_texto()
    input_taxa.delete(0, "end")
    input_parcela.valor_float = 0.0
    input_parcela._atualizar_texto()
    slider_prazo.set(48)
    lbl_prazo_v.configure(text="48 MESES")
    frame_veredito.configure(border_color=BORDA_FOCO)
    lbl_alerta.configure(text="AGUARDANDO ANÁLISE", text_color=COR_TEXTO_SEC)
    lbl_cet.configure(text="--.--%", text_color=COR_ACENTO_MUTED)
    lbl_gordura.configure(text="Diferença mensal: --", text_color=COR_TEXTO_SEC)


btn_limpar = ctk.CTkButton(
    body_frame, text="LIMPAR CAMPOS", height=42,
    font=("Segoe UI", 12), corner_radius=12,
    fg_color="transparent", border_width=1, border_color=BORDA_COR,
    text_color=COR_TEXTO_SEC, hover_color="#334155",
    command=resetar_pesquisa
)
btn_limpar.pack(pady=(12, 6), padx=20, fill="x")

btn_executar = ctk.CTkButton(body_frame, text="EXECUTAR AUDITORIA", height=50,
                              font=("Segoe UI", 14, "bold"), corner_radius=14,
                              fg_color=COR_ACENTO, hover_color=COR_ACENTO_HOVER,
                              command=investigar)
btn_executar.pack(pady=(6, 12), padx=20, fill="x")

janela.bind("<Return>", lambda event: investigar())

frame_veredito.pack(padx=20, pady=(5, 15), fill="both", expand=True)

# Rodapé
footer = ctk.CTkLabel(body_frame, text="© Audit Calc · Protegendo o consumidor",
                      font=("Segoe UI", 8), text_color="#64748b")
footer.pack(pady=(0, 8))

janela.mainloop()