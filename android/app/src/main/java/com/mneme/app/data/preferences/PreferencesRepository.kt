package com.mneme.app.data.preferences

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.mnemePreferencesDataStore by preferencesDataStore(name = "mneme_preferences")

class PreferencesRepository(
    private val dataStore: DataStore<Preferences>,
) {
    constructor(context: Context) : this(context.applicationContext.mnemePreferencesDataStore)

    val preferences: Flow<LocalPreferences> =
        dataStore.data.map { values ->
            LocalPreferences(
                topics = values[Keys.TOPICS].orEmpty(),
                keywords = values[Keys.KEYWORDS].orEmpty(),
                notificationsEnabled = values[Keys.NOTIFICATIONS_ENABLED] ?: true,
                digestRefreshHours =
                    values[Keys.DIGEST_REFRESH_HOURS] ?: LocalPreferences.DEFAULT_REFRESH_HOURS,
            )
        }

    suspend fun setTopics(topics: Set<String>) {
        dataStore.edit { it[Keys.TOPICS] = normalizePreferenceValues(topics) }
    }

    suspend fun setKeywords(keywords: Set<String>) {
        dataStore.edit { it[Keys.KEYWORDS] = normalizePreferenceValues(keywords) }
    }

    suspend fun setNotificationsEnabled(enabled: Boolean) {
        dataStore.edit { it[Keys.NOTIFICATIONS_ENABLED] = enabled }
    }

    suspend fun setDigestRefreshHours(hours: Int) {
        require(hours >= MIN_REFRESH_HOURS) { "Refresh interval must be at least 15 hours" }
        dataStore.edit { it[Keys.DIGEST_REFRESH_HOURS] = hours }
    }

    private object Keys {
        val TOPICS = stringSetPreferencesKey("topics")
        val KEYWORDS = stringSetPreferencesKey("keywords")
        val NOTIFICATIONS_ENABLED = booleanPreferencesKey("notifications_enabled")
        val DIGEST_REFRESH_HOURS = intPreferencesKey("digest_refresh_hours")
    }

    companion object {
        const val MIN_REFRESH_HOURS = 15
    }
}
