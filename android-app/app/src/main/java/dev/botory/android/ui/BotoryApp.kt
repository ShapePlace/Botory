package dev.botory.android.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ChatBubble
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Hub
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.FloatingToolbarDefaults
import androidx.compose.material3.HorizontalFloatingToolbar
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import dev.botory.android.data.BotoryClient
import dev.botory.android.ui.screens.ChatRoomScreen
import dev.botory.android.ui.screens.ChatsScreen
import dev.botory.android.ui.screens.HubScreen
import dev.botory.android.ui.screens.SetupScreen
import dev.botory.android.ui.screens.WidgetsScreen

enum class BotoryTab {
    CHATS, WIDGETS, HUB
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun BotoryApp(client: BotoryClient) {
    val uiState by client.state.collectAsState()
    var activeTab by remember { mutableStateOf(BotoryTab.CHATS) }
    var activeEntityId by remember { mutableStateOf<String?>(null) }
    var fabMenuOpen by remember { mutableStateOf(false) }

    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(uiState.snackbarMessage) {
        val msg = uiState.snackbarMessage
        if (!msg.isNullOrBlank()) {
            snackbarHostState.showSnackbar(msg)
            client.clearSnackbar()
        }
    }

    val activeEntity = uiState.entities.find { it.id == activeEntityId }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
        ) {
            if (!uiState.setupCompleted) {
                SetupScreen(
                    initialHubInput = uiState.lanUrl,
                    onConnectTermux = { client.connectWithPairingInput("ws://127.0.0.1:8765", false) },
                    onConnectCustom = { addr -> client.connectWithPairingInput(addr, false) },
                    onExploreDemo = { client.completeSetupWithDemo() }
                )
            } else if (activeEntity != null) {
                ChatRoomScreen(
                    entity = activeEntity,
                    messages = uiState.messagesByEntity[activeEntity.id].orEmpty(),
                    onBack = { activeEntityId = null },
                    onSendMessage = { text -> client.sendMessage(activeEntity.id, text) },
                    onCallback = { cb -> client.sendCallback(activeEntity.id, cb) }
                )
            } else {
                when (activeTab) {
                    BotoryTab.CHATS -> ChatsScreen(
                        uiState = uiState,
                        onOpenEntity = { id ->
                            client.markRead(id)
                            activeEntityId = id
                        },
                        onOpenHubTab = { activeTab = BotoryTab.HUB }
                    )

                    BotoryTab.WIDGETS -> WidgetsScreen(
                        uiState = uiState,
                        onRefreshDemo = { client.refreshDemoTelemetry() },
                        onToggleWidget = { eid, wid, checked -> client.toggleWidget(eid, wid, checked) },
                        onSliderChange = { eid, wid, v -> client.changeWidgetSlider(eid, wid, v) },
                        onRunTool = { eid, tid, args -> client.callTool(eid, tid, args) },
                        onDismissToolResult = { client.clearToolResult() }
                    )

                    BotoryTab.HUB -> HubScreen(
                        uiState = uiState,
                        onConnectPairingUri = { uri, relay -> client.connectWithPairingInput(uri, relay) },
                        onSwitchTransport = { mode -> client.switchTransport(mode) },
                        onImportZip = { bytes, name -> client.importProjectZip(bytes, name) },
                        onToggleProject = { proj -> client.toggleProjectRunning(proj) },
                        onOpenSetup = { client.openSetupWizard() }
                    )
                }

                Box(
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(bottom = 14.dp)
                ) {
                    HorizontalFloatingToolbar(
                        expanded = true,
                        floatingActionButton = {
                            FloatingToolbarDefaults.VibrantFloatingActionButton(
                                onClick = { fabMenuOpen = !fabMenuOpen }
                            ) {
                                Icon(Icons.Filled.Add, contentDescription = "Quick Actions")
                            }
                        },
                        colors = FloatingToolbarDefaults.vibrantFloatingToolbarColors()
                    ) {
                        IconButton(onClick = { activeTab = BotoryTab.CHATS }) {
                            Icon(
                                Icons.Filled.ChatBubble,
                                contentDescription = "Chats",
                                tint = if (activeTab == BotoryTab.CHATS) {
                                    MaterialTheme.colorScheme.primary
                                } else {
                                    MaterialTheme.colorScheme.onSurfaceVariant
                                }
                            )
                        }
                        Spacer(Modifier.width(4.dp))
                        IconButton(onClick = { activeTab = BotoryTab.WIDGETS }) {
                            Icon(
                                Icons.Filled.Dashboard,
                                contentDescription = "Widgets",
                                tint = if (activeTab == BotoryTab.WIDGETS) {
                                    MaterialTheme.colorScheme.primary
                                } else {
                                    MaterialTheme.colorScheme.onSurfaceVariant
                                }
                            )
                        }
                        Spacer(Modifier.width(4.dp))
                        IconButton(onClick = { activeTab = BotoryTab.HUB }) {
                            Icon(
                                Icons.Filled.Hub,
                                contentDescription = "Hub",
                                tint = if (activeTab == BotoryTab.HUB) {
                                    MaterialTheme.colorScheme.primary
                                } else {
                                    MaterialTheme.colorScheme.onSurfaceVariant
                                }
                            )
                        }
                    }

                    DropdownMenu(
                        expanded = fabMenuOpen,
                        onDismissRequest = { fabMenuOpen = false }
                    ) {
                        DropdownMenuItem(
                            text = { Text("Setup Wizard") },
                            onClick = {
                                fabMenuOpen = false
                                client.openSetupWizard()
                            }
                        )
                        DropdownMenuItem(
                            text = { Text("Hub & ZIP Import") },
                            onClick = {
                                fabMenuOpen = false
                                activeTab = BotoryTab.HUB
                            }
                        )
                        DropdownMenuItem(
                            text = { Text("Widgets & Tools") },
                            onClick = {
                                fabMenuOpen = false
                                activeTab = BotoryTab.WIDGETS
                            }
                        )
                    }
                }
            }
        }
    }
}
