package com.auditcalc

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.auditcalc.ui.theme.AuditCalcTheme
import com.auditcalc.ui.theme.AuditColors
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AuditCalcTheme {
                AuditCalcApp()
            }
        }
    }
}

private fun parseMoneyBR(s: String): Double {
    val t = s.trim().replace("R$", "", ignoreCase = true).trim()
        .replace(".", "").replace(",", ".")
    return t.toDoubleOrNull() ?: 0.0
}

private fun parsePercent(s: String): Double {
    return s.trim().replace(",", ".").toDoubleOrNull() ?: 0.0
}

private fun formatBRL(v: Double): String {
    return String.format(Locale("pt", "BR"), "R$ %,.2f", v)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AuditCalcApp() {
    var valorVeiculoTxt by remember { mutableStateOf("") }
    var entradaTxt by remember { mutableStateOf("") }
    var taxaTxt by remember { mutableStateOf("") }
    var parcelaTxt by remember { mutableStateOf("") }
    var prazo by remember { mutableFloatStateOf(48f) }

    // Mesmos padrões da sessão desktop (interface.py)
    val taxaVistoria = 750.0
    val taxaRegistro = 350.0

    var cetResult by remember { mutableStateOf("--.--%") }
    var msgResult by remember { mutableStateOf("AGUARDANDO ANÁLISE") }
    var diffResult by remember { mutableStateOf("Diferença mensal: --") }
    var borderAccent by remember { mutableStateOf(AuditColors.textoSec) }

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("AUDIT CALC", fontWeight = FontWeight.Bold)
                        Text("Financial Audit System", fontSize = 12.sp, color = AuditColors.textoSec)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        }
    ) { inner ->
        Column(
            Modifier
                .padding(inner)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
                .fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            OutlinedTextField(
                value = valorVeiculoTxt,
                onValueChange = { valorVeiculoTxt = it },
                label = { Text("Valor do veículo (ex: 75000 ou 75.000,00)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            OutlinedTextField(
                value = entradaTxt,
                onValueChange = { entradaTxt = it },
                label = { Text("Valor da entrada") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            OutlinedTextField(
                value = taxaTxt,
                onValueChange = { taxaTxt = it },
                label = { Text("Taxa prometida (% a.m.)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            OutlinedTextField(
                value = parcelaTxt,
                onValueChange = { parcelaTxt = it },
                label = { Text("Parcela do contrato") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )

            Text("Prazo: ${prazo.toInt()} meses", color = AuditColors.textoSec)
            Slider(
                value = prazo,
                onValueChange = { prazo = it },
                valueRange = 12f..72f,
                steps = 59,
                modifier = Modifier.fillMaxWidth()
            )

            Text(
                "Taxas fixas (vistoria/registro): ${formatBRL(taxaVistoria)} / ${formatBRL(taxaRegistro)} — ajuste no app desktop por enquanto.",
                fontSize = 11.sp,
                color = AuditColors.textoSec
            )

            Button(
                onClick = {
                    val vv = parseMoneyBR(valorVeiculoTxt)
                    val ent = parseMoneyBR(entradaTxt)
                    val taxa = parsePercent(taxaTxt)
                    val parc = parseMoneyBR(parcelaTxt)
                    val n = prazo.toInt()

                    when (val r = AuditEngine.auditar(
                        valorVeiculo = vv,
                        entrada = ent,
                        taxaPrometidaPctAm = taxa,
                        parcelaCobrada = parc,
                        prazoMeses = n,
                        taxaVistoria = taxaVistoria,
                        taxaRegistro = taxaRegistro
                    )) {
                        is AuditEngine.Result.Error -> {
                            cetResult = "--.--%"
                            msgResult = r.mensagem
                            diffResult = "Diferença mensal: --"
                            borderAccent = AuditColors.erro
                        }
                        is AuditEngine.Result.Success -> {
                            cetResult = String.format(Locale.US, "%.2f%% a.m.", r.cetPercentAm)
                            msgResult = r.mensagem
                            val d = r.diferencaMensal
                            diffResult = if (d != null) "Diferença: ${formatBRL(d)}" else "Diferença: não calculável"
                            borderAccent = when (r.status) {
                                AuditEngine.Status.OK -> AuditColors.sucesso
                                AuditEngine.Status.ALERTA -> AuditColors.alerta
                                AuditEngine.Status.ERRO -> AuditColors.erro
                            }
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("EXECUTAR AUDITORIA")
            }

            Spacer(Modifier.height(8.dp))

            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, borderAccent, RoundedCornerShape(16.dp)),
                colors = CardDefaults.cardColors(containerColor = AuditColors.card),
                shape = RoundedCornerShape(16.dp)
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text(msgResult, fontWeight = FontWeight.Bold, color = AuditColors.textoSec)
                    Spacer(Modifier.height(8.dp))
                    Text(cetResult, fontSize = 36.sp, fontWeight = FontWeight.Bold, color = AuditColors.acento)
                    Spacer(Modifier.height(8.dp))
                    Text(diffResult, color = AuditColors.textoSec, fontSize = 14.sp)
                }
            }

            Text("© Audit Calc", fontSize = 11.sp, color = AuditColors.textoSec)
        }
    }
}
