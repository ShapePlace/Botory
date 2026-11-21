package dev.botory.android.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.GenericShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.MaterialExpressiveTheme
import androidx.compose.material3.MotionScheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.expressiveLightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * Custom expressive polygon/organic shapes for differentiating Bots, IoT, AI, and Tools.
 */
object BotoryShapes {
    fun polygonShape(sides: Int, wobble: Float = 0.0f): Shape = GenericShape { size, _ ->
        val cx = size.width / 2f
        val cy = size.height / 2f
        val radius = minOf(cx, cy)
        val steps = sides * 8
        for (i in 0..steps) {
            val angle = (2.0 * PI * i / steps).toFloat()
            val mod = 1f - wobble * (0.5f + 0.5f * cos(sides * angle))
            val r = radius * mod
            val x = cx + r * cos(angle)
            val y = cy + r * sin(angle)
            if (i == 0) moveTo(x, y) else lineTo(x, y)
        }
        close()
    }

    val BotCookie: Shape = polygonShape(sides = 8, wobble = 0.14f)
    val AiBurst: Shape = polygonShape(sides = 10, wobble = 0.24f)
    val IotSquircle: Shape = RoundedCornerShape(16.dp)
    val ToolClover: Shape = polygonShape(sides = 4, wobble = 0.22f)

    fun forKind(kind: String): Shape = when (kind.lowercase()) {
        "ai" -> AiBurst
        "iot" -> IotSquircle
        "tool" -> ToolClover
        else -> BotCookie
    }
}

@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun BotoryTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = true,
    content: @Composable () -> Unit
) {
    val context = LocalContext.current
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> darkColorScheme()
        else -> expressiveLightColorScheme()
    }

    val shapes = Shapes(
        small = RoundedCornerShape(12.dp),
        medium = RoundedCornerShape(20.dp),
        large = RoundedCornerShape(26.dp),
        extraLarge = RoundedCornerShape(32.dp)
    )

    MaterialExpressiveTheme(
        colorScheme = colorScheme,
        motionScheme = MotionScheme.expressive(),
        shapes = shapes,
        content = content
    )
}
