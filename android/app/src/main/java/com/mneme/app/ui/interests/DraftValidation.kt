package com.mneme.app.ui.interests

import androidx.annotation.StringRes
import com.mneme.app.R

internal data class DraftValidation(
    val trimmedTopics: List<String>,
    val normalizedTopics: List<String>,
    @StringRes val messageResource: Int?,
)

internal fun validateDraft(topics: List<String>): DraftValidation {
    val trimmedTopics = topics.map(String::trim)
    val messageResource =
        when {
            trimmedTopics.any(String::isEmpty) -> R.string.interests_blank_error
            trimmedTopics.map(String::lowercase).distinct().size != trimmedTopics.size ->
                R.string.interests_duplicate_error
            else -> null
        }
    return DraftValidation(
        trimmedTopics = trimmedTopics,
        normalizedTopics = trimmedTopics.filter(String::isNotEmpty),
        messageResource = messageResource,
    )
}

internal fun List<String>.replacing(
    index: Int,
    value: String,
): List<String> =
    if (value.length > MAX_TOPIC_LENGTH) {
        this
    } else {
        toMutableList().also { it[index] = value }
    }

internal fun List<String>.removing(index: Int): List<String> = toMutableList().also { it.removeAt(index) }
