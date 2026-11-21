package dev.botory.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import dev.botory.android.data.BotoryClient
import dev.botory.android.ui.BotoryApp
import dev.botory.android.ui.theme.BotoryTheme

class MainActivity : ComponentActivity() {
    private val client by lazy { BotoryClient() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            BotoryTheme {
                BotoryApp(client = client)
            }
        }
    }
}
