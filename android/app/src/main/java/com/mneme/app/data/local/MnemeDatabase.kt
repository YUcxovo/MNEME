package com.mneme.app.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.mneme.app.data.local.dao.BehavioralEventDao
import com.mneme.app.data.local.dao.CacheMetadataDao
import com.mneme.app.data.local.dao.DigestDao
import com.mneme.app.data.local.dao.PaperDao
import com.mneme.app.data.local.dao.UserPrefsDao
import com.mneme.app.data.local.entity.BehavioralEventEntity
import com.mneme.app.data.local.entity.CacheMetadataEntity
import com.mneme.app.data.local.entity.DigestEntity
import com.mneme.app.data.local.entity.PaperEntity
import com.mneme.app.data.local.entity.UserPrefsEntity

@Database(
    entities = [
        PaperEntity::class,
        DigestEntity::class,
        UserPrefsEntity::class,
        CacheMetadataEntity::class,
        BehavioralEventEntity::class,
    ],
    version = 4,
    exportSchema = true,
)
abstract class MnemeDatabase : RoomDatabase() {
    abstract fun cacheMetadataDao(): CacheMetadataDao

    abstract fun behavioralEventDao(): BehavioralEventDao

    abstract fun paperDao(): PaperDao

    abstract fun digestDao(): DigestDao

    abstract fun userPrefsDao(): UserPrefsDao

    companion object {
        const val DATABASE_NAME = "mneme.db"
        const val CONTROLLED_FIXTURE_DATABASE_NAME = "mneme-controlled-fixture.db"

        val MIGRATION_1_2 =
            object : Migration(1, 2) {
                override fun migrate(database: SupportSQLiteDatabase) {
                    database.execSQL(
                        "ALTER TABLE papers ADD COLUMN last_synced_at INTEGER NOT NULL DEFAULT 0",
                    )
                    database.execSQL(
                        "ALTER TABLE digests ADD COLUMN last_synced_at INTEGER NOT NULL DEFAULT 0",
                    )
                    database.execSQL(
                        "ALTER TABLE user_preferences " +
                            "ADD COLUMN last_synced_at INTEGER NOT NULL DEFAULT 0",
                    )
                }
            }

        val MIGRATION_2_3 =
            object : Migration(2, 3) {
                override fun migrate(database: SupportSQLiteDatabase) {
                    database.execSQL(
                        "ALTER TABLE papers ADD COLUMN last_opened_at INTEGER NOT NULL DEFAULT 0",
                    )
                    database.execSQL(
                        "CREATE TABLE IF NOT EXISTS cache_metadata " +
                            "(id TEXT NOT NULL, last_successful_refresh_at INTEGER NOT NULL, " +
                            "PRIMARY KEY(id))",
                    )
                }
            }

        val MIGRATION_3_4 =
            object : Migration(3, 4) {
                override fun migrate(database: SupportSQLiteDatabase) {
                    database.execSQL(
                        "CREATE TABLE IF NOT EXISTS behavioral_events " +
                            "(id TEXT NOT NULL, event_type TEXT NOT NULL, paper_id TEXT, " +
                            "occurred_at INTEGER NOT NULL, duration_millis INTEGER, " +
                            "sync_state TEXT NOT NULL, sync_attempt_count INTEGER NOT NULL, " +
                            "last_sync_attempt_at INTEGER, last_sync_error TEXT, PRIMARY KEY(id))",
                    )
                    database.execSQL(
                        "CREATE INDEX IF NOT EXISTS index_behavioral_events_sync_state_occurred_at " +
                            "ON behavioral_events (sync_state, occurred_at)",
                    )
                }
            }

        fun create(context: Context): MnemeDatabase = create(context, DATABASE_NAME)

        fun createControlledFixture(context: Context): MnemeDatabase = create(context, CONTROLLED_FIXTURE_DATABASE_NAME)

        private fun create(
            context: Context,
            databaseName: String,
        ): MnemeDatabase =
            Room
                .databaseBuilder(
                    context.applicationContext,
                    MnemeDatabase::class.java,
                    databaseName,
                ).addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
                .build()
    }
}
