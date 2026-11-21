package dev.botory.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Lightbulb
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Badge
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import dev.botory.android.data.BotoryUiState
import dev.botory.android.data.EntityDescriptor
import dev.botory.android.data.TransportMode
import dev.botory.android.ui.theme.BotoryShapes

@Composable
fun ChatsScreen(
    uiState: BotoryUiState,
    onOpenEntity: (String) -> Unit,
    onOpenHubTab: () -> Unit,
    modifier: Modifier = Modifier
) {
    var search by remember { mutableStateOf("") }
    var filter by remember { mutableStateOf("all") }

    val filtered = remember(uiState.entities, search, filter) {
        uiState.entities.filter { ent ->
            val matchKind = filter == "all" || ent.kind.equals(filter, ignoreCase = true)
            val matchSearch = search.isBlank() ||
                ent.name.contains(search, ignoreCase = true) ||
                ent.description.contains(search, ignoreCase = true)
            matchKind && matchSearch
        }
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
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "Botory",
                    style = MaterialTheme.typography.headlineLarge,
                    fontWeight = FontWeight.ExtraBold
                )
                Text(
                    text = "${uiState.hubName} • ${uiState.entities.size} services",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            TransportStatusChip(
                mode = uiState.transport,
                onClick = onOpenHubTab
            )
        }

        Spacer(Modifier.height(12.dp))

        OutlinedTextField(
            value = search,
            onValueChange = { search = it },
            placeholder = { Text("Search bots, IoT, AI, Tools...") },
            leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null) },
            singleLine = true,
            shape = RoundedCornerShape(28.dp),
            modifier = Modifier.fillMaxWidth()
        )

        Spacer(Modifier.height(8.dp))

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            listOf(
                "all" to "All",
                "bot" to "Bots",
                "iot" to "IoT",
                "ai" to "Local AI",
                "tool" to "Tools"
            ).forEach { (key, label) ->
                FilterChip(
                    selected = filter == key,
                    onClick = { filter = key },
                    label = { Text(label) }
                )
            }
        }

        Spacer(Modifier.height(6.dp))

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(bottom = 110.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            items(filtered, key = { it.id }) { entity ->
                val lastMsg = uiState.messagesByEntity[entity.id]?.lastOrNull()
                val unread = uiState.unreadByEntity[entity.id] ?: 0
                EntityCard(
                    entity = entity,
                    preview = lastMsg?.text ?: entity.description.ifBlank { "Tap to open" },
                    time = lastMsg?.time ?: "",
                    unreadCount = unread,
                    onClick = { onOpenEntity(entity.id) }
                )
            }
        }
    }
}

@Composable
fun TransportStatusChip(mode: TransportMode, onClick: () -> Unit) {
    val (label, dotColor) = when (mode) {
        TransportMode.DEMO -> "Demo" to MaterialTheme.colorScheme.tertiary
        TransportMode.LAN -> "LAN" to Color(0xFF34D399)
        TransportMode.RELAY -> "Relay" to Color(0xFFFBBF24)
        TransportMode.OFFLINE -> "Offline" to MaterialTheme.colorScheme.error
    }

    AssistChip(
        onClick = onClick,
        label = { Text(label, fontWeight = FontWeight.Bold) },
        leadingIcon = {
            Box(
                modifier = Modifier
                    .size(9.dp)
                    .clip(CircleShape)
                    .background(dotColor)
            )
        }
    )
}

@Composable
private fun EntityCard(
    entity: EntityDescriptor,
    preview: String,
    time: String,
    unreadCount: Int,
    onClick: () -> Unit
) {
    val shape = BotoryShapes.forKind(entity.kind)
    val icon = when (entity.kind.lowercase()) {
        "ai" -> Icons.Filled.AutoAwesome
        "iot" -> Icons.Filled.Lightbulb
        "tool" -> Icons.Filled.Build
        else -> Icons.Filled.SmartToy
    }
    val containerColor = when (entity.kind.lowercase()) {
        "ai" -> MaterialTheme.colorScheme.secondaryContainer
        "iot" -> MaterialTheme.colorScheme.tertiaryContainer
        "tool" -> MaterialTheme.colorScheme.primary
        else -> MaterialTheme.colorScheme.primaryContainer
    }
    val iconTint = when (entity.kind.lowercase()) {
        "ai" -> MaterialTheme.colorScheme.onSecondaryContainer
        "iot" -> MaterialTheme.colorScheme.onTertiaryContainer
        "tool" -> MaterialTheme.colorScheme.onPrimary
        else -> MaterialTheme.colorScheme.onPrimaryContainer
    }

    Card(
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(50.dp)
                    .clip(shape)
                    .background(containerColor),
                contentAlignment = Alignment.Center
            ) {
                Icon(icon, contentDescription = null, tint = iconTint, modifier = Modifier.size(24.dp))
            }

            Spacer(Modifier.width(12.dp))

            Column(modifier = Modifier.weight(1f)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = entity.name,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f)
                    )
                    if (time.isNotBlank()) {
                        Text(
                            text = time,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                Spacer(Modifier.height(2.dp))
                Text(
                    text = preview,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Spacer(Modifier.height(6.dp))
                Surface(
                    shape = RoundedCornerShape(999.dp),
                    color = MaterialTheme.colorScheme.surfaceContainerHighest
                ) {
                    Text(
                        text = entity.kind.uppercase(),
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
                    )
                }
            }

            if (unreadCount > 0) {
                Spacer(Modifier.width(8.dp))
                Badge { Text(unreadCount.toString()) }
            }
        }
    }
}
