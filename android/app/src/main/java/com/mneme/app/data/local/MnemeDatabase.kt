package com.mneme.app.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.mneme.app.data.local.dao.DigestDao
import com.mneme.app.data.local.dao.PaperDao
import com.mneme.app.data.local.dao.UserPrefsDao
import com.mneme.app.data.local.entity.DigestEntity
import com.mneme.app.data.local.entity.PaperEntity
import com.mneme.app.data.local.entity.UserPrefsEntity

@Database(
    entities = [PaperEntity::class, DigestEntity::class, UserPrefsEntity::class],
    version = 2,
    exportSchema = true,
)
abstract class MnemeDatabase : RoomDatabase() {
    abstract fun paperDao(): PaperDao

    abstract fun digestDao(): DigestDao

    abstract fun userPrefsDao(): UserPrefsDao

    companion object {
        const val DATABASE_NAME = "mneme.db"

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

        fun create(context: Context): MnemeDatabase =
            Room
                .databaseBuilder(
                    context.applicationContext,
                    MnemeDatabase::class.java,
                    DATABASE_NAME,
                ).addMigrations(MIGRATION_1_2)
                .build()
    }
}
