package com.mneme.app.data.local

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mneme.app.data.local.entity.PaperEntity
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MnemeDatabaseTest {
    private lateinit var database: MnemeDatabase

    @Before
    fun createDatabase() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        database =
            Room
                .inMemoryDatabaseBuilder(context, MnemeDatabase::class.java)
                .allowMainThreadQueries()
                .build()
    }

    @After
    fun closeDatabase() {
        database.close()
    }

    @Test
    fun paperDao_upsertAndObserve_returnsNewestFirst() =
        runBlocking {
            database.paperDao().upsertAll(
                listOf(
                    paper(id = "older", arxivId = "2401.00001", updatedAt = 1),
                    paper(id = "newer", arxivId = "2401.00002", updatedAt = 2),
                ),
            )

            val papers = database.paperDao().observeAll().first()

            assertEquals(listOf("newer", "older"), papers.map(PaperEntity::id))
        }

    private fun paper(
        id: String,
        arxivId: String,
        updatedAt: Long,
    ) = PaperEntity(
        id = id,
        arxivId = arxivId,
        title = "Paper $id",
        authorsJson = "[]",
        abstractText = "Abstract",
        primaryCategory = "cs.HC",
        pdfUrl = null,
        processingStatus = "ready",
        updatedAtEpochMillis = updatedAt,
    )
}
