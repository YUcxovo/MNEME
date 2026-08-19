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

    @Test
    fun migrate4To5_preservesLegacyPaperWithEmptySummaryCache() {
        migrationHelper
            .createDatabase(TEST_DATABASE, 4)
            .use { database ->
                database.execSQL(
                    "INSERT INTO papers " +
                        "(id, arxiv_id, title, authors_json, abstract_text, primary_category, " +
                        "pdf_url, processing_status, updated_at, last_synced_at, last_opened_at) " +
                        "VALUES ('paper-1', '2607.00001', 'Legacy paper', '[]', 'Abstract', " +
                        "'cs.IR', NULL, 'ready', 10, 20, 30)",
                )
            }

        migrationHelper
            .runMigrationsAndValidate(
                TEST_DATABASE,
                5,
                true,
                MnemeDatabase.MIGRATION_4_5,
            ).use { database ->
                database
                    .query("SELECT title, summary_json FROM papers WHERE id = 'paper-1'")
                    .use { cursor ->
                        cursor.moveToFirst()
                        assertEquals("Legacy paper", cursor.getString(0))
                        assertEquals(true, cursor.isNull(1))
                    }
            }
    }

    @Test
    fun migrate5To6_preservesEventsAndAddsSavedPaperLookupIndex() {
        migrationHelper
            .createDatabase(TEST_DATABASE, 5)
            .use { database ->
                database.execSQL(
                    "INSERT INTO behavioral_events " +
                        "(id, event_type, paper_id, occurred_at, duration_millis, sync_state, " +
                        "sync_attempt_count, last_sync_attempt_at, last_sync_error) VALUES " +
                        "('saved-event', 'paper_saved', 'paper-1', 30, NULL, 'synced', 0, NULL, NULL)",
                )
            }

        migrationHelper
            .runMigrationsAndValidate(
                TEST_DATABASE,
                6,
                true,
                MnemeDatabase.MIGRATION_5_6,
            ).use { database ->
                database
                    .query("SELECT paper_id FROM behavioral_events WHERE id = 'saved-event'")
                    .use { cursor ->
                        cursor.moveToFirst()
                        assertEquals("paper-1", cursor.getString(0))
                    }
                database
                    .query("PRAGMA index_list('behavioral_events')")
                    .use { cursor ->
                        val nameColumn = cursor.getColumnIndexOrThrow("name")
                        val indexNames =
                            buildSet {
                                while (cursor.moveToNext()) {
                                    add(cursor.getString(nameColumn))
                                }
                            }
                        assertEquals(
                            true,
                            "index_behavioral_events_event_type_paper_id_occurred_at" in indexNames,
                        )
                    }
            }
    }

    companion object {
        private const val TEST_DATABASE = "mneme-migration-test"
    }
}
