package com.mneme.app.benchmark

import android.os.SystemClock
import androidx.benchmark.Outputs
import androidx.benchmark.macro.CompilationMode
import androidx.benchmark.macro.StartupMode
import androidx.benchmark.macro.StartupTimingMetric
import androidx.benchmark.macro.junit4.MacrobenchmarkRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Startup and foreground-resume measurements over a deterministic production Room cache.
 *
 * Each method retains six raw iterations and their traces. Iteration 1 is the declared warm-up;
 * downstream analysis must report iterations 2-6 without deleting the raw warm-up observation.
 */
@RunWith(AndroidJUnit4::class)
class MnemeStartupBenchmark {
    @get:Rule
    val benchmarkRule = MacrobenchmarkRule()

    private val device =
        UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

    @Before
    fun seedFivePaperCache() {
        device.pressHome()
        device.executeShellCommand("am force-stop $TARGET_PACKAGE")
        device.executeShellCommand("pm clear $TARGET_PACKAGE")
        device.executeShellCommand("am start -W -n $SEED_COMPONENT")

        val seedReady =
            device.wait(
                Until.hasObject(By.desc(SEED_READY_CONTENT_DESCRIPTION)),
                UI_TIMEOUT_MILLIS,
            )
        val seedError = device.hasObject(By.desc(SEED_ERROR_CONTENT_DESCRIPTION))
        assertFalse("The benchmark cache seed activity reported an error.", seedError)
        assertTrue("The benchmark cache seed activity did not become ready.", seedReady)

        device.pressHome()
        device.executeShellCommand("am force-stop $TARGET_PACKAGE")
    }

    @After
    fun stopTargetApp() {
        device.pressHome()
        device.executeShellCommand("am force-stop $TARGET_PACKAGE")
    }

    @Test
    fun coldCachedLaunch() {
        benchmarkRule.measureRepeated(
            packageName = TARGET_PACKAGE,
            metrics = listOf(StartupTimingMetric()),
            compilationMode = CompilationMode.None(),
            startupMode = StartupMode.COLD,
            iterations = RAW_ITERATION_COUNT,
            setupBlock = {
                pressHome()
            },
        ) {
            startActivityAndWait()
            assertCachedFivePaperBriefing()
        }
    }

    @Test
    fun foregroundResume() {
        var expectedProcessId = ""
        var expectedActivityRecordId = ""
        val completedObservations = mutableListOf<ResumeContractObservation>()
        benchmarkRule.measureRepeated(
            packageName = TARGET_PACKAGE,
            metrics = listOf(StartupTimingMetric()),
            compilationMode = CompilationMode.None(),
            startupMode = StartupMode.HOT,
            iterations = RAW_ITERATION_COUNT,
            setupBlock = {
                startActivityAndWait()
                assertCachedFivePaperBriefing()
                expectedProcessId = targetProcessId()
                expectedActivityRecordId = targetActivityRecordId()
                pressHome()
                SystemClock.sleep(FOREGROUND_RESUME_DWELL_MILLIS)
                assertEquals(
                    "The target process died while the app was in the background.",
                    expectedProcessId,
                    targetProcessId(),
                )
                assertEquals(
                    "The target Activity was recreated while the app was in the background.",
                    expectedActivityRecordId,
                    targetActivityRecordId(),
                )
            },
        ) {
            startActivityAndWait()
            assertCachedFivePaperBriefing()
            assertEquals(
                "The foreground resume unexpectedly created a new target process.",
                expectedProcessId,
                targetProcessId(),
            )
            assertEquals(
                "The foreground resume unexpectedly created a new Activity instance.",
                expectedActivityRecordId,
                targetActivityRecordId(),
            )
            completedObservations +=
                ResumeContractObservation(
                    assertionObservationOrdinal = completedObservations.size + 1,
                    processId = expectedProcessId,
                    activityRecordId = expectedActivityRecordId,
                )
            writeResumeContract(completedObservations)
        }
    }

    private fun assertCachedFivePaperBriefing() {
        assertTrue(
            "Expected exactly five papers restored with cached-backend origin.",
            device.wait(
                Until.hasObject(By.res(CACHED_FIVE_PAPER_TAG)),
                UI_TIMEOUT_MILLIS,
            ),
        )
    }

    private fun targetProcessId(): String {
        val processId = device.executeShellCommand("pidof $TARGET_PACKAGE").trim()
        assertTrue(
            "Expected one live target process but found '$processId'.",
            processId.matches(Regex("\\d+")),
        )
        return processId
    }

    private fun targetActivityRecordId(): String {
        val activityDump = device.executeShellCommand("dumpsys activity activities")
        val recordIds =
            TARGET_ACTIVITY_RECORD_PATTERN
                .findAll(activityDump)
                .map { match -> match.groupValues[1] }
                .toSet()
        assertEquals(
            "Expected one MainActivity record but found $recordIds.",
            1,
            recordIds.size,
        )
        return recordIds.single()
    }

    private fun writeResumeContract(observations: List<ResumeContractObservation>) {
        Outputs.writeFile(RESUME_CONTRACT_FILE_NAME, false) { outputFile ->
            val encodedObservations =
                observations.joinToString(separator = ",\n") { observation ->
                    """
                    |    {
                    |      "assertion_observation_ordinal": ${observation.assertionObservationOrdinal},
                    |      "pid": "${observation.processId}",
                    |      "activity_record_id": "${observation.activityRecordId}",
                    |      "same_pid": true,
                    |      "same_activity": true
                    |    }
                    """.trimMargin()
                }
            outputFile.writeText(
                """
                |{
                |  "status": "assertions_passed_for_completed_iterations",
                |  "expected_ui_tag": "$CACHED_FIVE_PAPER_TAG",
                |  "declared_raw_iterations": $RAW_ITERATION_COUNT,
                |  "warmup_iteration_ordinal": 1,
                |  "completed_assertion_observations": ${observations.size},
                |  "observations": [
                |$encodedObservations
                |  ]
                |}
                """.trimMargin(),
            )
        }
    }

    private companion object {
        const val TARGET_PACKAGE = "com.mneme.app"
        const val SEED_COMPONENT =
            "$TARGET_PACKAGE/com.mneme.app.evaluation.BenchmarkCacheSeedActivity"
        const val SEED_READY_CONTENT_DESCRIPTION = "benchmark-cache-seed-ready"
        const val SEED_ERROR_CONTENT_DESCRIPTION = "benchmark-cache-seed-error"
        const val CACHED_FIVE_PAPER_TAG = "briefing-content-5-cached-backend"
        const val RESUME_CONTRACT_FILE_NAME = "MnemeStartupBenchmark_foregroundResume_contract.json"
        const val RAW_ITERATION_COUNT = 6
        const val UI_TIMEOUT_MILLIS = 15_000L
        const val FOREGROUND_RESUME_DWELL_MILLIS = 2_000L
        val TARGET_ACTIVITY_RECORD_PATTERN =
            Regex("""ActivityRecord\{([0-9a-f]+) u\d+ com\.mneme\.app/\.MainActivity""")
    }
}

private data class ResumeContractObservation(
    val assertionObservationOrdinal: Int,
    val processId: String,
    val activityRecordId: String,
)
