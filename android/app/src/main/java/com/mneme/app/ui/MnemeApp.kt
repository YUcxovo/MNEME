@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.annotation.StringRes
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
import com.mneme.app.ui.home.HomeScreen
import com.mneme.app.ui.home.HomeUiState
import com.mneme.app.ui.navigation.BriefingRoute
import com.mneme.app.ui.navigation.InterestsRoute
import com.mneme.app.ui.navigation.PaperDetailRoute
import com.mneme.app.ui.navigation.QaRoute
import com.mneme.app.ui.navigation.SavedRoute
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

private data class MnemeUiSnapshot(
    val home: HomeUiState,
    val paper: PaperDetailUiState,
    val qa: QaUiState,
)

private data class MnemeUiActions(
    val refreshBriefing: () -> Unit,
    val requestPaper: (String) -> Unit,
    val retryPaper: (String) -> Unit,
    val requestQa: (String, String) -> Unit,
)

@Composable
fun MnemeApp(
    viewModel: MnemeViewModel,
    modifier: Modifier = Modifier,
    onOpenSource: ((String) -> Unit)? = null,
) {
    val homeState by viewModel.homeState.collectAsStateWithLifecycle()
    val paperState by viewModel.paperState.collectAsStateWithLifecycle()
    val qaState by viewModel.qaState.collectAsStateWithLifecycle()
    MnemeAppScaffold(
        snapshot = MnemeUiSnapshot(homeState, paperState, qaState),
        actions =
            MnemeUiActions(
                refreshBriefing = viewModel::refreshBriefing,
                requestPaper = { paperId -> viewModel.loadPaper(paperId) },
                retryPaper = { paperId -> viewModel.loadPaper(paperId, force = true) },
                requestQa = viewModel::askQuestion,
            ),
        onOpenSource = onOpenSource,
        modifier = modifier,
    )
}

@Composable
fun MnemeApp(
    modifier: Modifier = Modifier,
    repository: SkeletalContentRepository = SeededSkeletalContentRepository,
    onOpenSource: ((String) -> Unit)? = null,
) {
    var paperState by remember(repository) { mutableStateOf<PaperDetailUiState>(PaperDetailUiState.Idle) }
    var qaState by remember(repository) { mutableStateOf<QaUiState>(QaUiState.Idle) }
    val briefing = remember(repository) { repository.briefing() }
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
    MnemeAppScaffold(
        snapshot = MnemeUiSnapshot(HomeUiState.Content(briefing), paperState, qaState),
        actions =
            MnemeUiActions(
                refreshBriefing = {},
                requestPaper = loadPaper,
                retryPaper = loadPaper,
                requestQa = loadQa,
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
        composable<BriefingRoute> {
            HomeScreen(
                state = snapshot.home,
                onRetry = actions.refreshBriefing,
                onPaperClick = { paperId ->
                    navController.navigate(PaperDetailRoute(paperId))
                },
            )
        }
        composable<SavedRoute> {
            SavedScreen()
        }
        composable<InterestsRoute> {
            InterestsDestination(
                homeState = snapshot.home,
                onRetry = actions.refreshBriefing,
            )
        }
        composable<PaperDetailRoute> { entry ->
            val paperId = entry.toRoute<PaperDetailRoute>().paperId
            LaunchedEffect(paperId) { actions.requestPaper(paperId) }
            PaperDestination(
                paperId = paperId,
                state = snapshot.paper,
                onRetry = { actions.retryPaper(paperId) },
                onAskQuestion = { navController.navigate(QaRoute(paperId)) },
                onOpenSource = onOpenSource,
            )
        }
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
        else -> R.string.screen_title_briefing
    }
