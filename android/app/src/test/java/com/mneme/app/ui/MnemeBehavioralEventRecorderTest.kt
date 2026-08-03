package com.mneme.app.ui

import com.mneme.app.data.behavior.BehavioralEventTracker
import com.mneme.app.data.behavior.NoOpBehavioralEventTracker
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.yield
import org.junit.Assert.assertEquals
import org.junit.Test

class MnemeBehavioralEventRecorderTest {
    @Test
    fun saveConfirmsOnlyAfterDurableTrackerWriteCompletes() =
        runBlocking {
            val writeCompleted = CompletableDeferred<Unit>()
            val tracker = ConfigurableTracker(saveAction = { writeCompleted.await() })
            val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
            val recorder = MnemeBehavioralEventRecorder(tracker, scope)

            recorder.savePaper(PAPER_ID)

            assertEquals(
                EventRecordingStatus.RECORDING,
                recorder.engagementState.value.saveStatus(PAPER_ID),
            )
            writeCompleted.complete(Unit)
            yield()
            assertEquals(
                EventRecordingStatus.RECORDED,
                recorder.engagementState.value.saveStatus(PAPER_ID),
            )
            scope.cancel()
        }

    @Test
    fun failedSaveRemainsRetryableAndDoesNotClaimSuccess() {
        var attempts = 0
        var shouldFail = true
        val tracker =
            ConfigurableTracker(
                saveAction = {
                    attempts += 1
                    if (shouldFail) {
                        error("Room write failed")
                    }
                },
            )
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        val recorder = MnemeBehavioralEventRecorder(tracker, scope)

        recorder.savePaper(PAPER_ID)
        assertEquals(EventRecordingStatus.FAILED, recorder.engagementState.value.saveStatus(PAPER_ID))

        shouldFail = false
        recorder.savePaper(PAPER_ID)

        assertEquals(2, attempts)
        assertEquals(EventRecordingStatus.RECORDED, recorder.engagementState.value.saveStatus(PAPER_ID))
        scope.cancel()
    }

    @Test
    fun cancelledShareWriteExposesRetryAndLaterRecordsAction() {
        var attempts = 0
        val tracker =
            ConfigurableTracker(
                shareAction = {
                    attempts += 1
                    if (attempts == 1) {
                        throw CancellationException("write cancelled")
                    }
                },
            )
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        val recorder = MnemeBehavioralEventRecorder(tracker, scope)

        recorder.sharePaper(PAPER_ID)
        assertEquals(
            EventRecordingStatus.FAILED,
            recorder.engagementState.value.shareStatus(PAPER_ID),
        )

        recorder.sharePaper(PAPER_ID)

        assertEquals(2, attempts)
        assertEquals(
            EventRecordingStatus.RECORDED,
            recorder.engagementState.value.shareStatus(PAPER_ID),
        )
        scope.cancel()
    }

    @Test
    fun cancelledScopeDoesNotLeaveShareStuckAsRecording() {
        var attempts = 0
        val tracker = ConfigurableTracker(shareAction = { attempts += 1 })
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        val recorder = MnemeBehavioralEventRecorder(tracker, scope)
        scope.cancel()

        recorder.sharePaper(PAPER_ID)

        assertEquals(0, attempts)
        assertEquals(
            EventRecordingStatus.FAILED,
            recorder.engagementState.value.shareStatus(PAPER_ID),
        )
        recorder.sharePaper(PAPER_ID)
        assertEquals(
            EventRecordingStatus.FAILED,
            recorder.engagementState.value.shareStatus(PAPER_ID),
        )
    }

    @Test
    fun unavailableTrackerNeverClaimsThatSaveOrShareWasQueued() {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        val recorder = MnemeBehavioralEventRecorder(NoOpBehavioralEventTracker, scope)

        recorder.savePaper(PAPER_ID)
        recorder.sharePaper(PAPER_ID)

        assertEquals(
            EventRecordingStatus.FAILED,
            recorder.engagementState.value.saveStatus(PAPER_ID),
        )
        assertEquals(
            EventRecordingStatus.FAILED,
            recorder.engagementState.value.shareStatus(PAPER_ID),
        )
        scope.cancel()
    }

    private class ConfigurableTracker(
        private val saveAction: suspend () -> Unit = {},
        private val shareAction: suspend () -> Unit = {},
    ) : BehavioralEventTracker {
        override suspend fun recordPaperImpressions(paperIds: List<String>) = Unit

        override suspend fun recordPaperOpened(paperId: String) = Unit

        override suspend fun recordPaperSaved(paperId: String) = saveAction()

        override suspend fun recordPaperShared(paperId: String) = shareAction()

        override suspend fun recordQuestionAsked(paperId: String) = Unit
    }

    private companion object {
        const val PAPER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    }
}
