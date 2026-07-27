# Chapter 3 handoff: Android architecture and UI/UX design

**Integration owner:** Ruiyu (`@YUcxovo`)

**Intended locations in the thesis template:**

- `Engine Architecture`: the Android client boundary and state flow;
- `UI/UX Design`: interface hierarchy, provenance disclosure, and graph
  interaction;
- `Usability Testing`: the earlier formative study and the design response.

This material describes the Android and UI/UX contribution only. It does not
specify the server pipeline, recommendation algorithm, citation-graph
construction algorithm, notification implementation, or background scheduling
policy.

## Technical material

### Client state architecture

The Android client uses a unidirectional state flow. A screen sends an action
to its view model. The view model calls a repository, converts the result into
a typed UI state, and exposes that state to Jetpack Compose. The composable
renders the state and emits further user actions. Loading, content, and error
states are represented explicitly. Screens that can display retained data also
receive the content origin, allowing the interface to distinguish a live
response from cached or fallback content.

The separation has two practical purposes. First, it prevents network response
objects from becoming the interface state. Second, it makes recovery behaviour
testable without changing the composables. A controlled repository can return
the same domain result as the live repository and exercise the same view-model
and rendering path.

The relevant implementation sources are:

- `android/app/src/main/java/com/mneme/app/ui/MnemeViewModel.kt`;
- `android/app/src/main/java/com/mneme/app/ui/home/HomeUiState.kt`;
- `android/app/src/main/java/com/mneme/app/ui/SkeletalUiState.kt`;
- `android/app/src/main/java/com/mneme/app/data/repository/`;
- `android/app/src/main/java/com/mneme/app/data/network/MnemeApiClient.kt`.

### Navigation and paper identity

Compose Navigation defines the top-level destinations and passes a stable paper
identifier between the briefing, paper detail, question-answering, source, and
graph views. The identifier allows the detail view and graph selection panel
to request the same paper record without copying the full paper object into a
navigation route. Returning from the selected paper to the graph restores the
graph view and its selected-node context.

The relevant implementation sources are:

- `android/app/src/main/java/com/mneme/app/ui/MnemeApp.kt`;
- `android/app/src/main/java/com/mneme/app/ui/MnemeBriefingNavigation.kt`;
- `android/app/src/main/java/com/mneme/app/ui/MnemeGraphNavigation.kt`;
- `android/app/src/androidTest/java/com/mneme/app/ui/MnemeAppFlowTest.kt`;
- `android/app/src/androidTest/java/com/mneme/app/ui/graph/GraphScreenTest.kt`.

### Citation-graph interaction boundary

The graph screen combines native Compose controls with a local WebView
renderer. Android serializes the graph model and sends it to the renderer. The
renderer reports a selected paper identifier through a narrow JavaScript
bridge. The bridge accepts identifiers that occur in the current graph and
posts the selection to the Android main thread. The native selection panel
then displays the paper context and provides the Open Paper action.

This boundary separates graph presentation from graph construction. The
Android contribution covers rendering, selection, state restoration, and
navigation. Node ranking, clustering, and edge-generation quality remain
outside this contribution.

The relevant implementation sources are:

- `android/app/src/main/java/com/mneme/app/ui/graph/CitationGraphWebView.kt`;
- `android/app/src/main/java/com/mneme/app/ui/graph/GraphScreen.kt`;
- `android/app/src/androidTest/java/com/mneme/app/ui/graph/GraphScreenTest.kt`;
- `android/app/src/androidTest/java/com/mneme/app/ui/graph/E4GraphMeasurementTest.kt`.

### UI/UX rationale

The primary mobile flow begins with a compact briefing and keeps paper-centred
actions close to each paper. Paper details, a concise summary, question
answering, source inspection, and citation exploration are reached through
explicit actions. The interface presents loading, processing, empty, fallback,
and error states instead of leaving an old successful screen visible without
explanation.

The graph view uses three layers of interaction: the graph canvas provides
overview, node selection exposes the current paper and relation context, and a
persistent Open Paper action connects exploration to reading. This design
responds to the main difficulty observed in the formative usability study:
participants could see the graph but did not always understand what action to
take next.

### Formative usability evidence

The design-stage usability study involved five participants and five tasks.
All five participants completed the briefing and paper-reading tasks, two
completed citation-graph exploration without assistance, and four completed
the preference task. This gave 21 successful task completions out of 25
attempts. The result identified graph discoverability as the clearest
interaction problem. The subsequent interface added visible graph guidance, a
persistent selected-node state, relation context, and an explicit Open Paper
action.

This is formative evidence from the earlier prototype. The revised graph
interaction was not retested with the same participants, so the design change
should be presented as a response to the finding rather than proof that the
usability problem was eliminated.

## Sample thesis writing

The following paragraphs may be adapted into Chapter 3. They deliberately omit
repository and project-management details.

### Sample for Engine Architecture

The Android application follows a unidirectional state flow. Each screen sends
user actions to a view model, which obtains domain results through a repository
and converts them into a typed UI state. Jetpack Compose renders this state and
emits subsequent actions. Loading, content, and error conditions are therefore
represented explicitly rather than inferred from nullable response fields.
For screens that can recover retained content, the state also carries its
origin so that live, cached, and fallback results can be disclosed to the
reader. This separation keeps transport objects outside the presentation layer
and allows the same rendering path to be evaluated with controlled and live
data sources.

Navigation is based on stable paper identifiers. The briefing, paper-detail,
question-answering, source, and citation-graph views use the identifier to
refer to a shared paper record without embedding a complete paper object in a
route. The approach also supports restoration of the graph context when the
reader returns from a selected paper.

### Sample for UI/UX Design

The mobile interface is organized around a paper-centred reading flow. The
briefing provides a compact entry point, while each paper exposes actions for
detail, summary, question answering, source inspection, and citation
exploration. Waiting and recovery conditions are visible in the interface.
Processing, empty, cached, fallback, and error states use distinct messages so
that the reader can understand whether the displayed material is current and
which action remains available.

Citation exploration combines a WebView-based graph canvas with native Android
controls. Android sends the graph data to the renderer and receives only a
validated paper identifier when a node is selected. The native panel preserves
the selected state, shows the relation context, and provides an Open Paper
action. This design gives an overview of the local citation neighbourhood while
retaining a direct path to the paper-reading interface. It evaluates the
client-side presentation and interaction boundary; the construction and
ranking of the graph are described separately.

### Sample for Usability Testing

A formative usability study with five participants evaluated five core mobile
tasks. The participants completed 21 of the 25 task attempts. Briefing access
and paper reading were completed by all participants, while citation-graph
exploration was completed without assistance by two participants. Four
participants completed the preference task. The graph result indicated that
the visual structure alone did not communicate the next action clearly enough.
The revised interface therefore added short instructions, an explicit
selected-node state, relation context, and a persistent Open Paper action.
Because the revised interaction was not evaluated with the same study
protocol, these changes are reported as design responses rather than a measured
improvement in usability.

## Integration checks

Before incorporating this material, the Chapter 3 owner should:

1. retain the distinction between Android graph interaction and graph
   construction;
2. keep the formative study separate from the E4 technical measurements;
3. avoid attributing notification or worker behaviour to this contribution;
4. preserve the limitation that the revised graph was not retested with the
   formative study.
