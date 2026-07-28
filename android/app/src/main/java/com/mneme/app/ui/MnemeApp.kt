@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import android.content.Intent
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
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
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
    val engagement: PaperEngagementUiState,
)

internal data class MnemeUiActions(
    val refreshBriefing: () -> Unit,
    val recordPaperImpressions: (List<String>) -> Unit,
    val recordPaperOpened: (String) -> Unit,
    val requestPaper: (String) -> Unit,
    val retryPaper: (String) -> Unit,
    val openQa: (String) -> Unit,
    val requestQa: (String, String) -> Unit,
    val requestGraph: (String) -> Unit,
    val retryGraph: (String) -> Unit,
    val saveInterests: (List<String>) -> Unit,
    val savePaper: (String) -> Unit,
    val sharePaper: (String) -> Unit,
)

internal data class MnemeExternalActions(
    val openSource: (String) -> Unit,
    val sharePaper: (String, String) -> Unit,
)

@Composable
fun MnemeApp(
    viewModel: MnemeViewModel,
    modifier: Modifier = Modifier,
    onOpenSource: ((String) -> Unit)? = null,
    onSharePaper: ((String, String) -> Unit)? = null,
) {
    val onboardingState by viewModel.onboardingState.collectAsStateWithLifecycle()
    val snapshot = viewModel.collectUiSnapshot(onboardingState)
    Surface(
        modifier = modifier.semantics { testTagsAsResourceId = true },
        color = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.onBackground,
    ) {
        when (val current = onboardingState) {
            OnboardingUiState.Checking ->
                Box(
                    modifier = Modifier.fillMaxSize().testTag("briefing-restore-loading"),
                    contentAlignment = Alignment.Center,
                ) {
                    LoadingState(message = stringResource(R.string.briefing_restore_loading))
                }
            OnboardingUiState.AwaitingSeed ->
                SeedOnboardingScreen(
                    initialReference = "",
                    errorMessage = null,
                    onSubmit = viewModel::initializeFromSeed,
                    modifier = Modifier,
                )
            is OnboardingUiState.Loading ->
                Box(
                    modifier = Modifier.fillMaxSize().testTag("seed-onboarding-loading"),
                    contentAlignment = Alignment.Center,
                ) {
                    LoadingState(message = stringResource(R.string.onboarding_loading))
                }
            is OnboardingUiState.Error ->
                SeedOnboardingScreen(
                    initialReference = current.arxivReference,
                    errorMessage = current.message,
                    onSubmit = viewModel::initializeFromSeed,
                    modifier = Modifier,
                )
            OnboardingUiState.Ready ->
                MnemeAppScaffold(
                    snapshot = snapshot,
                    actions = viewModel.uiActions(),
                    onOpenSource = onOpenSource,
                    onSharePaper = onSharePaper,
                    modifier = Modifier,
                )
        }
    }
}

@Composable
fun MnemeApp(
    modifier: Modifier = Modifier,
    repository: SkeletalContentRepository = SeededSkeletalContentRepository,
    onOpenSource: ((String) -> Unit)? = null,
    onSharePaper: ((String, String) -> Unit)? = null,
) {
    val state = remember(repository) { FixtureMnemeState(repository) }
    MnemeAppScaffold(
        snapshot = state.snapshot,
        actions = state.actions,
        onOpenSource = onOpenSource,
        onSharePaper = onSharePaper,
        modifier = modifier.semantics { testTagsAsResourceId = true },
    )
}

@Composable
private fun MnemeAppScaffold(
    snapshot: MnemeUiSnapshot,
    actions: MnemeUiActions,
    onOpenSource: ((String) -> Unit)?,
    onSharePaper: ((String, String) -> Unit)?,
    modifier: Modifier = Modifier,
) {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = backStackEntry?.destination
    val topLevelDestination = currentDestination.topLevelDestination()
    val uriHandler = LocalUriHandler.current
    val context = LocalContext.current
    val sourceOpener = onOpenSource ?: { url: String -> uriHandler.openUri(url) }
    val paperSharer =
        onSharePaper ?: { title: String, url: String ->
            val sendIntent =
                Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_SUBJECT, title)
                    putExtra(Intent.EXTRA_TEXT, "$title\n$url")
                }
            context.startActivity(
                Intent.createChooser(
                    sendIntent,
                    context.getString(R.string.share_chooser_title),
                ),
            )
        }
    val externalActions =
        MnemeExternalActions(
            openSource = sourceOpener,
            sharePaper = paperSharer,
        )

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
            externalActions = externalActions,
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
    externalActions: MnemeExternalActions,
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
        paperDetailNavigation(navController, snapshot, actions, externalActions)
        graphNavigation(
            navController = navController,
            state = snapshot.graph,
            requestGraph = actions.requestGraph,
            retryGraph = actions.retryGraph,
        )
        qaNavigation(snapshot, actions, externalActions)
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
