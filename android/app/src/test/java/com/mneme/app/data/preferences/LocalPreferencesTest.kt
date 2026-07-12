package com.mneme.app.data.preferences

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalPreferencesTest {
    @Test
    fun normalizePreferenceValues_trimsDropsBlanksAndSorts() {
        val result = normalizePreferenceValues(setOf("  vision ", "", "Agents", "agents"))

        assertEquals(listOf("Agents", "vision"), result.toList())
    }

    @Test
    fun defaults_areReadyForFirstLaunch() {
        val preferences = LocalPreferences()

        assertTrue(preferences.notificationsEnabled)
        assertEquals(24, preferences.digestRefreshHours)
    }
}
