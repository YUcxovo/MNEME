package com.mneme.app.ui.paper

import androidx.annotation.StringRes
import com.mneme.app.R
import com.mneme.app.ui.EventRecordingStatus

@StringRes
internal fun EventRecordingStatus.saveLabel(): Int =
    when (this) {
        EventRecordingStatus.IDLE -> R.string.action_save_paper
        EventRecordingStatus.RECORDING -> R.string.action_saving_paper
        EventRecordingStatus.RECORDED -> R.string.action_saved
        EventRecordingStatus.FAILED -> R.string.action_retry_save_paper
    }

@StringRes
internal fun EventRecordingStatus.feedbackRes(isShare: Boolean = false): Int? =
    when (this) {
        EventRecordingStatus.IDLE -> null
        EventRecordingStatus.RECORDING ->
            if (isShare) R.string.share_recording else R.string.save_recording
        EventRecordingStatus.RECORDED ->
            if (isShare) R.string.share_recorded else R.string.save_recorded
        EventRecordingStatus.FAILED ->
            if (isShare) R.string.share_record_failed else R.string.save_record_failed
    }
