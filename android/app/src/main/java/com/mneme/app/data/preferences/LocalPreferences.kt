package com.mneme.app.data.preferences

data class LocalPreferences(
    val topics: Set<String> = emptySet(),
    val keywords: Set<String> = emptySet(),
    val notificationsEnabled: Boolean = true,
    val digestRefreshHours: Int = DEFAULT_REFRESH_HOURS,
) {
    companion object {
        const val DEFAULT_REFRESH_HOURS = 24
    }
}

internal fun normalizePreferenceValues(values: Set<String>): Set<String> =
    values
        .map(String::trim)
        .filter(String::isNotEmpty)
        .toSortedSet(String.CASE_INSENSITIVE_ORDER)
