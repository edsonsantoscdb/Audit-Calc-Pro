package com.auditcalc.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Fundo = Color(0xFF0C1017)
private val Card = Color(0xFF151B26)
private val Acento = Color(0xFF2563EB)
private val Sucesso = Color(0xFF22C55E)
private val Alerta = Color(0xFFEAB308)
private val Erro = Color(0xFFEF4444)
private val Texto = Color(0xFFF1F5F9)
private val TextoSec = Color(0xFF94A3B8)

private val scheme = darkColorScheme(
    primary = Acento,
    onPrimary = Color.White,
    surface = Fundo,
    onSurface = Texto,
    surfaceVariant = Card,
    onSurfaceVariant = TextoSec,
    error = Erro,
    tertiary = Sucesso
)

@Composable
fun AuditCalcTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = scheme,
        content = content
    )
}

object AuditColors {
    val acento = Acento
    val fundo = Fundo
    val card = Card
    val texto = Texto
    val textoSec = TextoSec
    val sucesso = Sucesso
    val alerta = Alerta
    val erro = Erro
}
