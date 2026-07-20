@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.theme

import android.app.Activity
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat

private val MnemeColors =
    darkColorScheme(
        primary = MnemeGold,
        onPrimary = MnemeBackground,
        primaryContainer = MnemeGoldSoft,
        onPrimaryContainer = MnemeBackground,
        secondary = MnemeAqua,
        onSecondary = MnemeBackground,
        secondaryContainer = MnemeSurfaceStrong,
        onSecondaryContainer = MnemeTextSoft,
        tertiary = MnemeSage,
        onTertiary = MnemeBackground,
        tertiaryContainer = MnemeSurfaceRaised,
        onTertiaryContainer = MnemeTextSoft,
        background = MnemeBackground,
        onBackground = MnemeText,
        surface = MnemeSurface,
        onSurface = MnemeText,
        surfaceVariant = MnemeSurfaceRaised,
        onSurfaceVariant = MnemeMuted,
        outline = MnemeOutline,
        outlineVariant = MnemeFaint,
        error = MnemeRose,
        onError = MnemeBackground,
        scrim = Color.Black,
    )

private val MnemeTypography =
    Typography(
        displayLarge =
            TextStyle(
                fontFamily = FontFamily.Serif,
                fontWeight = FontWeight.SemiBold,
                fontSize = 42.sp,
                lineHeight = 48.sp,
            ),
        headlineLarge =
            TextStyle(
                fontFamily = FontFamily.Serif,
                fontWeight = FontWeight.SemiBold,
                fontSize = 30.sp,
                lineHeight = 36.sp,
            ),
        headlineMedium =
            TextStyle(
                fontFamily = FontFamily.Serif,
                fontWeight = FontWeight.SemiBold,
                fontSize = 25.sp,
                lineHeight = 30.sp,
            ),
        headlineSmall =
            TextStyle(
                fontFamily = FontFamily.Serif,
                fontWeight = FontWeight.SemiBold,
                fontSize = 22.sp,
                lineHeight = 28.sp,
            ),
        titleLarge =
            TextStyle(
                fontFamily = FontFamily.Serif,
                fontWeight = FontWeight.SemiBold,
                fontSize = 22.sp,
                lineHeight = 28.sp,
            ),
        titleMedium =
            TextStyle(
                fontFamily = FontFamily.Serif,
                fontWeight = FontWeight.SemiBold,
                fontSize = 18.sp,
                lineHeight = 24.sp,
            ),
        titleSmall =
            TextStyle(
                fontFamily = FontFamily.SansSerif,
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp,
                lineHeight = 20.sp,
            ),
        bodyLarge =
            TextStyle(
                fontFamily = FontFamily.SansSerif,
                fontWeight = FontWeight.Normal,
                fontSize = 16.sp,
                lineHeight = 24.sp,
            ),
        bodyMedium =
            TextStyle(
                fontFamily = FontFamily.SansSerif,
                fontWeight = FontWeight.Normal,
                fontSize = 14.sp,
                lineHeight = 21.sp,
            ),
        bodySmall =
            TextStyle(
                fontFamily = FontFamily.SansSerif,
                fontWeight = FontWeight.Normal,
                fontSize = 12.sp,
                lineHeight = 18.sp,
            ),
        labelLarge =
            TextStyle(
                fontFamily = FontFamily.SansSerif,
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp,
                lineHeight = 20.sp,
            ),
        labelMedium =
            TextStyle(
                fontFamily = FontFamily.SansSerif,
                fontWeight = FontWeight.SemiBold,
                fontSize = 12.sp,
                lineHeight = 17.sp,
            ),
        labelSmall =
            TextStyle(
                fontFamily = FontFamily.SansSerif,
                fontWeight = FontWeight.Bold,
                fontSize = 10.sp,
                lineHeight = 14.sp,
                letterSpacing = 1.2.sp,
            ),
    )

private val MnemeShapes =
    Shapes(
        extraSmall = RoundedCornerShape(8.dp),
        small = RoundedCornerShape(10.dp),
        medium = RoundedCornerShape(12.dp),
        large = RoundedCornerShape(18.dp),
        extraLarge = RoundedCornerShape(24.dp),
    )

@Composable
fun MnemeTheme(content: @Composable () -> Unit) {
    val view = LocalView.current
    if (!view.isInEditMode) {
        val controller = WindowCompat.getInsetsController((view.context as Activity).window, view)
        controller.isAppearanceLightStatusBars = false
        controller.isAppearanceLightNavigationBars = false
    }

    MaterialTheme(
        colorScheme = MnemeColors,
        typography = MnemeTypography,
        shapes = MnemeShapes,
        content = content,
    )
}
