@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Interests
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavDestination
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import com.mneme.app.R
import com.mneme.app.data.demo.SeededSkeletalContentRepository
import com.mneme.app.data.demo.SkeletalContentRepository
import com.mneme.app.ui.component.LoadingState
import com.mneme.app.ui.home.HomeUiState
import com.mneme.app.ui.navigation.BriefingRoute
import com.mneme.app.ui.navigation.GraphRoute
import com.mneme.app.ui.navigation.InterestsRoute
import com.mneme.app.ui.navigation.PaperDetailRoute
import com.mneme.app.ui.navigation.QaRoute
import com.mneme.app.ui.navigation.SavedRoute
import com.mneme.app.ui.onboarding.SeedOnboardingScreen
import com.mneme.app.ui.saved.SavedScreen

private enum class TopLevelDestination(
    val route: Any,
    @StringRes val labelRes: Int,
) {
    BRIEFING(BriefingRoute, R.string.nav_briefing),
    SAVED(SavedRoute, R.string.nav_saved),
    INTERESTS(InterestsRoute, R.string.nav_interests),
    ;

    fun icon(): ImageVector =
        when (this) {
            BRIEFING -> Icons.Default.Home
            SAVED -> Icons.Default.Bookmark
            INTERESTS -> Icons.Default.Interests
        }
}

internal data class MnemeUiSnapshot(
    val home: HomeUiState,
    val paper: PaperDetailUiState,
    val qa: QaUiState,
    val graph: GraphUiState,
    val interestEdit: InterestEditUiState,
)

private data class MnemeUiActions(
    val refreshBriefing: () -> Unit,
    val recordPaperImpressions: (List<String>) -> Unit,
    val recordPaperOpened: (String) -> Unit,
    val requestPaper: (String) -> Unit,
    val retryPaper: (String) -> Unit,
    val requestQa: (String, String) -> Unit,
    val requestGraph: (String) -> Unit,
    val retryGraph: (String) -> Unit,
    val saveInterests: (List<String>) -> Unit,
)

@Composable
fun MnemeApp(
    viewModel: MnemeViewModel,
    modifier: Modifier = Modifier,
    onOpenSource: ((String) -> Unit)? = null,
) {
    val onboardingState by viewModel.onboardingState.collectAsStateWithLifecycle()
    val snapshot = viewModel.collectUiSnapshot()
    when (val current = onboardingState) {
        OnboardingUiState.Checking ->
            Box(
                modifier = modifier.fillMaxSize().testTag("briefing-restore-loading"),
                contentAlignment = Alignment.Center,
            ) {
                LoadingState(message = stringResource(R.string.briefing_restore_loading))
            }
        OnboardingUiState.AwaitingSeed ->
            SeedOnboardingScreen(
                initialReference = "",
                errorMessage = null,
                onSubmit = viewModel::initializeFromSeed,
                modifier = modifier,
            )
        is OnboardingUiState.Loading ->
            Box(
                modifier = modifier.fillMaxSize().testTag("seed-onboarding-loading"),
                contentAlignment = Alignment.Center,
            ) {
                LoadingState(message = stringResource(R.string.onboarding_loading))
            }
        is OnboardingUiState.Error ->
            SeedOnboardingScreen(
                initialReference = current.arxivReference,
                errorMessage = current.message,
                onSubmit = viewModel::initializeFromSeed,
                modifier = modifier,
            )
        OnboardingUiState.Ready ->
            MnemeAppScaffold(
                snapshot = snapshot,
                actions =
                    MnemeUiActions(
                        refreshBriefing = viewModel::refreshBriefing,
                        recordPaperImpressions = viewModel.behavioralEvents::recordPaperImpressions,
                        recordPaperOpened = viewModel.behavioralEvents::recordPaperOpened,
                        requestPaper = { paperId -> viewModel.loadPaper(paperId) },
                        retryPaper = { paperId -> viewModel.loadPaper(paperId, force = true) },
                        requestQa = viewModel::askQuestion,
                        requestGraph = { paperId -> viewModel.loadGraph(paperId) },
                        retryGraph = { paperId -> viewModel.loadGraph(paperId, force = true) },
                        saveInterests = viewModel::saveInterests,
                    ),
                onOpenSource = onOpenSource,
                modifier = modifier,
            )
    }
}

@Composable
fun MnemeApp(
    modifier: Modifier = Modifier,
    repository: SkeletalContentRepository = SeededSkeletalContentRepository,
    onOpenSource: ((String) -> Unit)? = null,
) {
    var paperState by remember(repository) { mutableStateOf<PaperDetailUiState>(PaperDetailUiState.Idle) }
    var qaState by remember(repository) { mutableStateOf<QaUiState>(QaUiState.Idle) }
    var graphState by remember(repository) { mutableStateOf<GraphUiState>(GraphUiState.Idle) }
    var briefing by remember(repository) { mutableStateOf(repository.briefing()) }
    var interestEditState by remember(repository) {
        mutableStateOf<InterestEditUiState>(InterestEditUiState.Idle)
    }
    val loadPaper = { paperId: String ->
        paperState =
            repository.paper(paperId)?.let(PaperDetailUiState::Content)
                ?: PaperDetailUiState.Error(paperId, "The selected paper is not available.")
    }
    val loadQa = { paperId: String, question: String ->
        qaState =
            repository.qa(paperId, question)?.let(QaUiState::Content)
                ?: QaUiState.Error(
                    paperId,
                    question,
                    "A paper-specific answer is not available.",
                )
    }
    val loadGraph = { paperId: String ->
        graphState =
            repository.graph(paperId)?.let(GraphUiState::Content)
                ?: GraphUiState.Error(paperId, "A citation graph is not available for this paper.")
    }
    MnemeAppScaffold(
        snapshot =
            MnemeUiSnapshot(
                HomeUiState.Content(briefing),
                paperState,
                qaState,
                graphState,
                interestEditState,
            ),
        actions =
            MnemeUiActions(
                refreshBriefing = {},
                recordPaperImpressions = {},
                recordPaperOpened = {},
                requestPaper = loadPaper,
                retryPaper = loadPaper,
                requestQa = loadQa,
                requestGraph = loadGraph,
                retryGraph = loadGraph,
                saveInterests = { topics ->
                    briefing = briefing.copy(interests = topics)
                    interestEditState = InterestEditUiState.Saved
                },
            ),
        onOpenSource = onOpenSource,
        modifier = modifier,
    )
}

@Composable
private fun MnemeAppScaffold(
    snapshot: MnemeUiSnapshot,
    actions: MnemeUiActions,
    onOpenSource: ((String) -> Unit)?,
    modifier: Modifier = Modifier,
) {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = backStackEntry?.destination
    val topLevelDestination = currentDestination.topLevelDestination()
    val uriHandler = LocalUriHandler.current
    val sourceOpener = onOpenSource ?: { url: String -> uriHandler.openUri(url) }

    Scaffold(
        modifier = modifier,
        containerColor = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.onBackground,
        topBar = {
            MnemeTopAppBar(
                titleRes = currentDestination.appBarTitleRes(topLevelDestination),
                kickerRes = topLevelDestination.kickerRes(),
                showBrandMark = topLevelDestination != null,
                canNavigateBack = currentDestination != null && topLevelDestination == null,
                onNavigateBack = navController::popBackStack,
            )
        },
        bottomBar = {
            if (topLevelDestination != null) {
                MnemeNavigationBar(
                    selectedDestination = topLevelDestination,
                    onDestinationSelected = navController::navigateToTopLevel,
                )
            }
        },
    ) { innerPadding ->
        MnemeNavHost(
            navController = navController,
            snapshot = snapshot,
            actions = actions,
            onOpenSource = sourceOpener,
            modifier = Modifier.padding(innerPadding),
        )
    }
}

@Composable
private fun MnemeNavigationBar(
    selectedDestination: TopLevelDestination,
    onDestinationSelected: (TopLevelDestination) -> Unit,
) {
    NavigationBar(
        containerColor = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.onBackground,
        tonalElevation = 0.dp,
    ) {
        TopLevelDestination.entries.forEach { destination ->
            val label = stringResource(destination.labelRes)
            NavigationBarItem(
                selected = destination == selectedDestination,
                onClick = { onDestinationSelected(destination) },
                icon = {
                    Icon(
                        imageVector = destination.icon(),
                        contentDescription = label,
                    )
                },
                label = { Text(text = label, style = MaterialTheme.typography.labelMedium) },
                modifier = Modifier.testTag("nav-${destination.name.lowercase()}"),
                colors =
                    NavigationBarItemDefaults.colors(
                        selectedIconColor = MaterialTheme.colorScheme.primary,
                        selectedTextColor = MaterialTheme.colorScheme.primary,
                        indicatorColor = MaterialTheme.colorScheme.surface,
                        unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                        unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
                    ),
            )
        }
    }
}

@Composable
private fun MnemeNavHost(
    navController: NavHostController,
    snapshot: MnemeUiSnapshot,
    actions: MnemeUiActions,
    onOpenSource: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    NavHost(
        navController = navController,
        startDestination = BriefingRoute,
        modifier = modifier,
    ) {
        briefingNavigation(
            navController = navController,
            state = snapshot.home,
            refreshBriefing = actions.refreshBriefing,
            recordPaperImpressions = actions.recordPaperImpressions,
            recordPaperOpened = actions.recordPaperOpened,
        )
        composable<SavedRoute> {
            SavedScreen()
        }
        composable<InterestsRoute> {
            InterestsDestination(
                homeState = snapshot.home,
                editState = snapshot.interestEdit,
                onRetry = actions.refreshBriefing,
                onSave = actions.saveInterests,
            )
        }
        composable<PaperDetailRoute> { entry ->
            val paperId = entry.toRoute<PaperDetailRoute>().paperId
            LaunchedEffect(paperId) { actions.requestPaper(paperId) }
            PaperDestination(
                paperId = paperId,
                state = snapshot.paper,
                actions =
                    PaperDestinationActions(
                        retry = { actions.retryPaper(paperId) },
                        askQuestion = { navController.navigate(QaRoute(paperId)) },
                        exploreGraph = { navController.navigate(GraphRoute(paperId)) },
                        openSource = onOpenSource,
                    ),
            )
        }
        graphNavigation(
            navController = navController,
            state = snapshot.graph,
            requestGraph = actions.requestGraph,
            retryGraph = actions.retryGraph,
        )
        composable<QaRoute> { entry ->
            val paperId = entry.toRoute<QaRoute>().paperId
            QaDestination(
                paperId = paperId,
                state = snapshot.qa,
                onSubmit = { question -> actions.requestQa(paperId, question) },
                onOpenSource = onOpenSource,
            )
        }
    }
}

private fun NavHostController.navigateToTopLevel(destination: TopLevelDestination) {
    navigate(destination.route) {
        popUpTo(graph.findStartDestination().id) {
            saveState = true
        }
        launchSingleTop = true
        restoreState = true
    }
}

private fun NavDestination?.topLevelDestination(): TopLevelDestination? =
    when {
        this?.hierarchy?.any { it.hasRoute<BriefingRoute>() } == true -> {
            TopLevelDestination.BRIEFING
        }
        this?.hierarchy?.any { it.hasRoute<SavedRoute>() } == true -> {
            TopLevelDestination.SAVED
        }
        this?.hierarchy?.any { it.hasRoute<InterestsRoute>() } == true -> {
            TopLevelDestination.INTERESTS
        }
        else -> null
    }

@StringRes
private fun NavDestination?.appBarTitleRes(topLevelDestination: TopLevelDestination?): Int =
    when (topLevelDestination) {
        TopLevelDestination.BRIEFING -> R.string.app_name
        TopLevelDestination.INTERESTS -> R.string.nav_interests
        else -> titleRes()
    }

@StringRes
private fun TopLevelDestination?.kickerRes(): Int? =
    when (this) {
        TopLevelDestination.BRIEFING -> R.string.kicker_research_briefing
        TopLevelDestination.SAVED, TopLevelDestination.INTERESTS -> R.string.kicker_research_memory
        null -> null
    }

@StringRes
private fun NavDestination?.titleRes(): Int =
    when {
        this?.hierarchy?.any { it.hasRoute<SavedRoute>() } == true -> R.string.screen_title_saved
        this?.hierarchy?.any { it.hasRoute<InterestsRoute>() } == true -> {
            R.string.screen_title_interests
        }
        this?.hierarchy?.any { it.hasRoute<PaperDetailRoute>() } == true -> {
            R.string.screen_title_paper
        }
        this?.hierarchy?.any { it.hasRoute<QaRoute>() } == true -> R.string.screen_title_qa
        this?.hierarchy?.any { it.hasRoute<GraphRoute>() } == true -> R.string.screen_title_graph
        else -> R.string.screen_title_briefing
    }
