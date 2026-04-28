# Audit Calc — Android

Projeto **Kotlin + Jetpack Compose** com a mesma lógica financeira do desktop (`motor_auditoria.py`).

## O que foi criado

| Arquivo | Função |
|---------|--------|
| `AuditCalc/app/.../FinanceMath.kt` | `rate` e `pmt` (paridade com `numpy_financial`) |
| `AuditCalc/app/.../AuditEngine.kt` | Regras de negócio (CET, veredito, diferença mensal) |
| `AuditCalc/app/.../MainActivity.kt` | Tela principal (entrada de valores + resultado) |

A tela de **parâmetros** (vistoria/registro), **histórico** e **calculadora** ainda não foram portadas; os valores fixos estão como **750 / 350** no `MainActivity.kt` (igual ao padrão da sessão no PC).

## Como abrir

1. Instale [Android Studio](https://developer.android.com/studio) (Hedgehog ou mais recente).
2. **File → Open** e escolha a pasta `android/AuditCalc`.
3. Aceite o download do **Gradle** / **SDK** se o assistente pedir.
4. Com um emulador ou celular em modo desenvolvedor: **Run** ▶.

Se o Gradle Wrapper não existir, o Android Studio costuma oferecer **“Create Gradle Wrapper”** ou use **File → New → Import** e deixe o IDE gerar o wrapper.

## Build do APK (Release)

No Android Studio: **Build → Generate Signed Bundle / APK** (defina uma keystore para distribuição).

## Projeto Python

A lógica partilhada está em **`core/motor_auditoria.py`** (usada pelo desktop e pelo Flet). O ficheiro Kotlin espelha as mesmas regras em `AuditEngine.kt` / `FinanceMath.kt`.
