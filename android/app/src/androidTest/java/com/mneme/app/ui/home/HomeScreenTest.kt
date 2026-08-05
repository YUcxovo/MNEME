@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui.home

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.ui.theme.MnemeTheme
import org.junit.Rule
import org.junit.Test

class HomeScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun content_showsControlledBriefingAndPaper() {
        composeRule.setContent {
            MnemeTheme {
                HomeScreen(
                    state = HomeUiState.Content(SeededSkeletalContentRepository.briefing()),
                    onRetry = {},
                    onPaperClick = {},
                )
            }
        }

        composeRule.onNodeWithText("Attention Is All You Need").assertIsDisplayed()
        composeRule.onNodeWithText("Natural language processing").assertIsDisplayed()
        composeRule.onNodeWithText("SAMPLE CONTENT").assertIsDisplayed()
    }
}
