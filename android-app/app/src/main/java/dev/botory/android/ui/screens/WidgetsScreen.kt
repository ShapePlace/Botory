package dev.botory.android.ui.screens

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearWavyProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.ProgressIndicatorDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import dev.botory.android.data.BotoryUiState
import dev.botory.android.data.EntityDescriptor
import dev.botory.android.data.ToolDefinition
import dev.botory.android.data.WidgetCardUi
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun WidgetsScreen(
    uiState: BotoryUiState,
    onRefreshDemo: () -> Unit,
    onToggleWidget: (entityId: String, widgetId: String, checked: Boolean) -> Unit,
    onSliderChange: (entityId: String, widgetId: String, value: Float) -> Unit,
    onRunTool: (entityId: String, toolId: String, args: Map<String, Any>) -> Unit,
    onDismissToolResult: () -> Unit,
    modifier: Modifier = Modifier
) {
    var activeToolPair by remember { mutableStateOf<Pair<EntityDescriptor, ToolDefinition>?>(null) }

    val allTools = remember(uiState.entities) {
        uiState.entities.flatMap { ent -> ent.tools.map { t -> ent to t } }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp)
    ) {
        Spacer(Modifier.height(12.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text("Widgets & Tools", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.ExtraBold)
                Text(
                    "Live telemetry, IoT controls & Python RPC tools",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            IconButton(onClick = onRefreshDemo) {
                Icon(Icons.Filled.Refresh, contentDescription = "Refresh")
            }
        }

        Spacer(Modifier.height(12.dp))

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(bottom = 110.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            items(uiState.widgets, key = { "${it.entityId}_${it.widgetId}" }) { card ->
                WidgetBentoCard(
                    card = card,
                    onToggle = { wid, checked -> onToggleWidget(card.entityId, wid, checked) },
                    onSlider = { wid, value -> onSliderChange(card.entityId, wid, value) }
                )
            }

            if (allTools.isNotEmpty()) {
                item {
                    Text(
                        text = "Python Tools (@app.tool)",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(top = 6.dp)
                    )
                }
                items(allTools, key = { "${it.first.id}_${it.second.toolId}" }) { (entity, tool) ->
                    Card(
                        shape = RoundedCornerShape(24.dp),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(tool.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                                Text(
                                    "${entity.name} • ${tool.toolId}",
                                    style = MaterialTheme.typography.labelSmall,
                                    fontFamily = FontFamily.Monospace,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                if (tool.description.isNotBlank()) {
                                    Text(
                                        tool.description,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                            FilledTonalButton(onClick = { activeToolPair = entity to tool }) {
                                Icon(Icons.Filled.Bolt, contentDescription = null)
                                Text("Run")
                            }
                        }
                    }
                }
            }

            uiState.lastToolResult?.let { resText ->
                item {
                    Surface(
                        shape = RoundedCornerShape(20.dp),
                        color = MaterialTheme.colorScheme.tertiaryContainer,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(14.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text("Tool Output", fontWeight = FontWeight.Bold)
                                FilledTonalButton(onClick = onDismissToolResult) { Text("OK") }
                            }
                            Text(resText, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }
    }

    activeToolPair?.let { (entity, tool) ->
        ToolRunnerBottomSheet(
            entity = entity,
            tool = tool,
            onDismiss = { activeToolPair = null },
            onSubmit = { args ->
                onRunTool(entity.id, tool.toolId, args)
                activeToolPair = null
            }
        )
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
private fun WidgetBentoCard(
    card: WidgetCardUi,
    onToggle: (String, Boolean) -> Unit,
    onSlider: (String, Float) -> Unit
) {
    Card(
        shape = RoundedCornerShape(26.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Column {
                Text(card.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text(card.subtitle, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            card.blocks.forEach { block ->
                when (block.kind) {
                    "wavy_progress" -> {
                        val animated by animateFloatAsState(
                            targetValue = block.value.coerceIn(0f, 1f),
                            animationSpec = ProgressIndicatorDefaults.ProgressAnimationSpec,
                            label = "bentoWavy"
                        )
                        Column {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(block.label, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                                Text(block.display, style = MaterialTheme.typography.labelMedium, fontFamily = FontFamily.Monospace)
                            }
                            Spacer(Modifier.height(6.dp))
                            LinearWavyProgressIndicator(
                                progress = { animated },
                                modifier = Modifier.fillMaxWidth()
                            )
                        }
                    }

                    "toggle_row" -> {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(block.label, style = MaterialTheme.typography.bodyMedium)
                            Switch(
                                checked = block.checked,
                                onCheckedChange = { onToggle(block.id, it) }
                            )
                        }
                    }

                    "slider" -> {
                        Column {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(block.label, style = MaterialTheme.typography.bodyMedium)
                                Text(block.display.ifBlank { "${block.value.toInt()}%" }, fontFamily = FontFamily.Monospace)
                            }
                            Slider(
                                value = block.value.coerceIn(0f, 100f),
                                onValueChange = { onSlider(block.id, it) },
                                valueRange = 0f..100f
                            )
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ToolRunnerBottomSheet(
    entity: EntityDescriptor,
    tool: ToolDefinition,
    onDismiss: () -> Unit,
    onSubmit: (Map<String, Any>) -> Unit
) {
    val formValues = remember(tool) {
        mutableStateMapOf<String, Any>().apply {
            tool.params.forEach { p ->
                when (p.type) {
                    "boolean" -> put(p.name, p.default?.jsonPrimitive?.booleanOrNull ?: false)
                    "select" -> put(
                        p.name,
                        p.default?.jsonPrimitive?.contentOrNull
                            ?: p.options?.firstOrNull()?.jsonPrimitive?.contentOrNull
                            ?: ""
                    )
                    else -> put(p.name, p.default?.jsonPrimitive?.contentOrNull ?: "")
                }
            }
        }
    }

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(tool.title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(
                "${entity.name} • ${tool.toolId}",
                style = MaterialTheme.typography.labelMedium,
                fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            tool.params.forEach { param ->
                when (param.type) {
                    "boolean" -> {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(param.label)
                            Switch(
                                checked = (formValues[param.name] as? Boolean) ?: false,
                                onCheckedChange = { formValues[param.name] = it }
                            )
                        }
                    }

                    "select" -> {
                        Column {
                            Text(param.label, style = MaterialTheme.typography.labelMedium)
                            Spacer(Modifier.height(6.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                param.options?.forEach { opt ->
                                    val optStr = opt.jsonPrimitive.contentOrNull ?: ""
                                    FilterChip(
                                        selected = formValues[param.name] == optStr,
                                        onClick = { formValues[param.name] = optStr },
                                        label = { Text(optStr) }
                                    )
                                }
                            }
                        }
                    }

                    else -> {
                        OutlinedTextField(
                            value = formValues[param.name]?.toString() ?: "",
                            onValueChange = { formValues[param.name] = it },
                            label = { Text(param.label) },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true
                        )
                    }
                }
            }

            Button(
                onClick = { onSubmit(formValues.toMap()) },
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(999.dp)
            ) {
                Text("Run Python Tool")
            }
            Spacer(Modifier.height(16.dp))
        }
    }
}
