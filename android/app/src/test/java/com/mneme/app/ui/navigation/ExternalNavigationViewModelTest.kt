package com.mneme.app.ui.navigation

import androidx.lifecycle.SavedStateHandle
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ExternalNavigationViewModelTest {
    @Test
    fun openPaperPublishesValidRequest() {
        val viewModel = ExternalNavigationViewModel(SavedStateHandle())

        viewModel.openPaper(PAPER_ID)

        assertEquals(
            ExternalNavigationRequest.OpenPaper(
                requestId = 1L,
                paperId = PAPER_ID,
            ),
            viewModel.request.value,
        )
    }

    @Test
    fun rejectPaperLinkPublishesInvalidRequest() {
        val viewModel = ExternalNavigationViewModel(SavedStateHandle())

        viewModel.rejectPaperLink()

        assertEquals(
            ExternalNavigationRequest.InvalidPaperLink(requestId = 1L),
            viewModel.request.value,
        )
    }

    @Test
    fun consumeClearsOnlyMatchingRequest() {
        val viewModel = ExternalNavigationViewModel(SavedStateHandle())
        viewModel.openPaper(PAPER_ID)
        val pendingRequest = viewModel.request.value
        requireNotNull(pendingRequest)

        viewModel.consume(pendingRequest.requestId + 1L)

        assertEquals(pendingRequest, viewModel.request.value)

        viewModel.consume(pendingRequest.requestId)

        assertNull(viewModel.request.value)
    }

    @Test
    fun pendingRequestSurvivesViewModelRecreationWithSavedStateHandle() {
        val savedStateHandle = SavedStateHandle()
        val firstViewModel = ExternalNavigationViewModel(savedStateHandle)
        firstViewModel.openPaper(PAPER_ID)

        val recreatedViewModel = ExternalNavigationViewModel(savedStateHandle.recreated())

        assertEquals(firstViewModel.request.value, recreatedViewModel.request.value)
    }

    @Test
    fun requestIdsIncreaseAcrossRequestKindsConsumptionAndRecreation() {
        val savedStateHandle = SavedStateHandle()
        val viewModel = ExternalNavigationViewModel(savedStateHandle)

        viewModel.openPaper(PAPER_ID)
        val firstId = requireNotNull(viewModel.request.value).requestId
        viewModel.consume(firstId)
        viewModel.rejectPaperLink()
        val secondId = requireNotNull(viewModel.request.value).requestId

        val recreatedViewModel = ExternalNavigationViewModel(savedStateHandle.recreated())
        recreatedViewModel.openPaper(OTHER_PAPER_ID)
        val thirdRequest = recreatedViewModel.request.value
        assertTrue(thirdRequest is ExternalNavigationRequest.OpenPaper)
        val thirdId = requireNotNull(thirdRequest).requestId

        assertEquals(1L, firstId)
        assertEquals(2L, secondId)
        assertEquals(3L, thirdId)
    }

    private companion object {
        const val PAPER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        const val OTHER_PAPER_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    }
}

private fun SavedStateHandle.recreated(): SavedStateHandle =
    SavedStateHandle(
        keys().associateWith { key -> get<Any?>(key) },
    )
