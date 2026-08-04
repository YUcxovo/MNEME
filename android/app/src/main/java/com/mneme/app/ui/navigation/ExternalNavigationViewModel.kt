package com.mneme.app.ui.navigation

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import kotlinx.coroutines.flow.StateFlow
import java.io.Serializable
import java.util.UUID

sealed interface ExternalNavigationRequest : Serializable {
    val requestId: Long

    data class OpenPaper(
        override val requestId: Long,
        val paperId: String,
        val eventId: String,
    ) : ExternalNavigationRequest

    data class OpenDigest(
        override val requestId: Long,
        val digestId: String,
    ) : ExternalNavigationRequest

    data class InvalidPaperLink(
        override val requestId: Long,
    ) : ExternalNavigationRequest
}

internal class ExternalNavigationViewModel(
    private val savedStateHandle: SavedStateHandle,
) : ViewModel() {
    val request: StateFlow<ExternalNavigationRequest?> =
        savedStateHandle.getStateFlow(PENDING_REQUEST_KEY, null)

    fun openPaper(paperId: String) {
        require(PaperDeepLink.parseUri(PaperDeepLink.buildUri(paperId)) == paperId) {
            "A canonical paper identifier is required."
        }
        savedStateHandle[PENDING_REQUEST_KEY] =
            ExternalNavigationRequest.OpenPaper(
                requestId = nextRequestId(),
                paperId = paperId,
                eventId = UUID.randomUUID().toString(),
            )
    }

    fun rejectPaperLink() {
        savedStateHandle[PENDING_REQUEST_KEY] =
            ExternalNavigationRequest.InvalidPaperLink(nextRequestId())
    }

    fun openDigest(digestId: String) {
        require(digestId.isNotBlank()) { "A digest identifier is required." }
        savedStateHandle[PENDING_REQUEST_KEY] =
            ExternalNavigationRequest.OpenDigest(
                requestId = nextRequestId(),
                digestId = digestId,
            )
    }

    fun consume(requestId: Long) {
        if (request.value?.requestId == requestId) {
            savedStateHandle[PENDING_REQUEST_KEY] = null
        }
    }

    private fun nextRequestId(): Long {
        val next = (savedStateHandle[LAST_REQUEST_ID_KEY] ?: 0L) + 1L
        savedStateHandle[LAST_REQUEST_ID_KEY] = next
        return next
    }

    private companion object {
        const val PENDING_REQUEST_KEY = "pending_external_navigation"
        const val LAST_REQUEST_ID_KEY = "last_external_navigation_id"
    }
}
