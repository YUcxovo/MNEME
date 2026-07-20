@file:Suppress("ktlint:standard:function-naming")

package com.mneme.app.ui

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Interests
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
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
import com.mneme.app.ui.component.ErrorState
import com.mneme.app.ui.home.HomeScreen
import com.mneme.app.ui.home.HomeUiState
import com.mneme.app.ui.interests.InterestsScreen
import com.mneme.app.ui.navigation.BriefingRoute
import com.mneme.app.ui.navigation.InterestsRoute
import com.mneme.app.ui.navigation.PaperDetailRoute
import com.mneme.app.ui.navigation.QaRoute
import com.mneme.app.ui.navigation.SavedRoute
import com.mneme.app.ui.paper.PaperDetailScreen
import com.mneme.app.ui.qa.QaScreen
import com.mneme.app.ui.saved.SavedScreen
import com.mneme.app.ui.theme.MnemeTheme

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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MnemeApp(
    modifier: Modifier = Modifier,
    repository: SkeletalContentRepository = SeededSkeletalContentRepository,
    onOpenSource: ((String) -> Unit)? = null,
) {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = backStackEntry?.destination
    val topLevelDestination = currentDestination.topLevelDestination()
    val uriHandler = LocalUriHandler.current
    val sourceOpener = onOpenSource ?: { url: String -> uriHandler.openUri(url) }

    Scaffold(
        modifier = modifier,
        topBar = {
            MnemeTopAppBar(
                titleRes = currentDestination.titleRes(),
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
            repository = repository,
            onOpenSource = sourceOpener,
            modifier = Modifier.padding(innerPadding),
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MnemeTopAppBar(
    @StringRes titleRes: Int,
    canNavigateBack: Boolean,
    onNavigateBack: () -> Unit,
) {
    TopAppBar(
        title = { Text(text = stringResource(titleRes)) },
        navigationIcon = {
            if (canNavigateBack) {
                IconButton(
                    onClick = onNavigateBack,
                    modifier = Modifier.testTag("navigate-back"),
                ) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = stringResource(R.string.action_back),
                    )
                }
            }
        },
    )
}

@Composable
private fun MnemeNavigationBar(
    selectedDestination: TopLevelDestination,
    onDestinationSelected: (TopLevelDestination) -> Unit,
) {
    NavigationBar {
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
                label = { Text(text = label) },
                modifier = Modifier.testTag("nav-${destination.name.lowercase()}"),
            )
        }
    }
}

@Composable
private fun MnemeNavHost(
    navController: NavHostController,
    repository: SkeletalContentRepository,
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
                state = HomeUiState.Content(repository.briefing()),
                onRetry = {},
                onPaperClick = { paperId ->
                    navController.navigate(PaperDetailRoute(paperId))
                },
            )
        }
        composable<SavedRoute> {
            SavedScreen()
        }
        composable<InterestsRoute> {
            InterestsScreen(interests = repository.briefing().interests)
        }
        composable<PaperDetailRoute> { entry ->
            val paperId = entry.toRoute<PaperDetailRoute>().paperId
            val paper = repository.paper(paperId)
            if (paper == null) {
                ErrorState(
                    message = stringResource(R.string.paper_not_found),
                    onRetry = navController::popBackStack,
                )
            } else {
                PaperDetailScreen(
                    paper = paper,
                    onAskQuestion = { navController.navigate(QaRoute(paperId)) },
                    onOpenSource = onOpenSource,
                )
            }
        }
        composable<QaRoute> { entry ->
            val paperId = entry.toRoute<QaRoute>().paperId
            val qa = repository.qa(paperId)
            if (qa == null) {
                ErrorState(
                    message = stringResource(R.string.qa_not_found),
                    onRetry = navController::popBackStack,
                )
            } else {
                QaScreen(qa = qa, onOpenSource = onOpenSource)
            }
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

@Preview(showBackground = true)
@Composable
private fun MnemeAppPreview() {
    MnemeTheme {
        MnemeApp(onOpenSource = {})
    }
}
