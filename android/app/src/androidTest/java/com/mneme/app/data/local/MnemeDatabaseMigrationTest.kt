package com.mneme.app.data.local

import androidx.room.testing.MigrationTestHelper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MnemeDatabaseMigrationTest {
    @get:Rule
    @Suppress("DEPRECATION")
    val migrationHelper =
        MigrationTestHelper(
            InstrumentationRegistry.getInstrumentation(),
            MnemeDatabase::class.java,
        )

    @Test
    fun migrate3To4_createsValidatedBehavioralEventQueue() {
        migrationHelper.createDatabase(TEST_DATABASE, 3).close()

        migrationHelper
            .runMigrationsAndValidate(
                TEST_DATABASE,
                4,
                true,
                MnemeDatabase.MIGRATION_3_4,
            ).use { database ->
                database.execSQL(
                    "INSERT INTO behavioral_events " +
                        "(id, event_type, paper_id, occurred_at, duration_millis, sync_state, " +
                        "sync_attempt_count, last_sync_attempt_at, last_sync_error) VALUES " +
                        "('8f0a1d3b-cc41-43f0-97c2-c175341ef07c', 'paper_opened', " +
                        "'2d3f275d-2f4f-4144-a9fd-a2cbe8f12c88', 20, 500, 'pending', 0, NULL, NULL)",
                )
                database
                    .query("SELECT event_type, duration_millis FROM behavioral_events")
                    .use { cursor ->
                        cursor.moveToFirst()
                        assertEquals("paper_opened", cursor.getString(0))
                        assertEquals(500L, cursor.getLong(1))
                    }
            }
    }

    companion object {
        private const val TEST_DATABASE = "mneme-migration-test"
    }
}
