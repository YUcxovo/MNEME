@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.home

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import com.mneme.app.ui.theme.MnemeTheme
import org.junit.Rule
import org.junit.Test

class HomeScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun emptyState_showsGuidanceAndBottomNavigation() {
        composeRule.setContent {
            MnemeTheme {
                HomeScreen(
                    state = HomeUiState.Empty,
                    onRetry = {},
                    onPaperClick = {},
                    onDestinationSelected = {},
                )
            }
        }

        composeRule.onNodeWithTag("home-empty-state").assertIsDisplayed()
        composeRule
            .onNodeWithText("Choose topics in Settings to personalize future digests.")
            .assertIsDisplayed()
        composeRule.onNodeWithText("Digest").assertIsDisplayed()
    }
}
