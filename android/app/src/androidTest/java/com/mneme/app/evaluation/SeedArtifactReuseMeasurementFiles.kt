package com.mneme.app.evaluation

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import java.io.File
import java.util.Locale

internal object SeedArtifactReuseMeasurementFiles {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private val outputDirectory =
        File(
            requireNotNull(context.getExternalFilesDir(null)) {
                "App-specific external storage is required for evaluation artifacts."
            },
            "seed-artifact-reuse-evaluation",
        )
    private val resultFile = File(outputDirectory, "measurement.csv")

    fun reset() {
        outputDirectory.deleteRecursively()
        outputDirectory.mkdirs()
        resultFile.writeText("$HEADER\n")
    }

    @Synchronized
    fun write(
        input: SeedArtifactReuseMeasurementTest.MeasurementInput,
        durationMillis: Double?,
        success: Boolean,
        outcome: String,
        paperCount: Int?,
        paperIds: List<String>,
        contentOrigin: String?,
    ) {
        check(resultFile.readLines().size == 1) {
            "The focused measurement must retain exactly one result row."
        }
        val values =
            listOf(
                "seed-artifact-reuse-android-v1",
                input.pairId,
                input.seedArxivId,
                input.condition,
                durationMillis,
                success,
                outcome,
                paperCount,
                paperIds.joinToString(";"),
                contentOrigin,
            )
        resultFile.appendText(values.joinToString(",") { value -> csv(value) } + "\n")
    }

    private fun csv(value: Any?): String {
        val text =
            when (value) {
                null -> ""
                is Double -> String.format(Locale.US, "%.3f", value)
                else -> value.toString()
            }
        return if (text.any { character -> character in setOf(',', '"', '\n') }) {
            "\"${text.replace("\"", "\"\"")}\""
        } else {
            text
        }
    }

    private const val HEADER =
        "schema_version,pair_id,seed_arxiv_id,condition,duration_ms,success,outcome," +
            "paper_count,paper_ids,content_origin"
}
