# Chapter 3 provenance ledger

This file is a non-rendered evidence ledger for contents/chapter_3.tex. It records the source of design claims, figures, study results, and bibliography entries so that later editorial work can distinguish internal evidence from interpretation. The rendered chapter must not expose repository workflow or use this ledger as a substitute for a scholarly citation.

## Source snapshot

- Second-supervisor design-scope revision baseline: 9ef8fca. The revised chapter preserves the exact template hierarchy, retains design-level architecture and formative evidence, and moves algorithms, equations, parameter catalogues, and runtime implementation details to the non-rendered transfer package at `thesis_revison/TEMP_CONTENT.md`.
- Chapter source baseline inspected for this revision: 17da6785217510728bc39ee324bdcc23e5441456.
- Android/UI handoff and implementation snapshot inspected for the state, navigation, and graph-interaction revision: 4c1e53310f7e989ceab1ba4186faef7d4617665c.
- Behavior-model source snapshot inspected for the revised interest-memory design: 0a21abd847a09db172edf680b12dd56b07e1e3a7.
- Runtime interface baseline: docs/api/openapi-v0.1.yaml plus FastAPI-generated schemas and routes under backend/src/mneme/api/.
- Architecture and evaluation specifications consulted: docs/architecture/, docs/adr/, backend services and repositories, Android data/network/navigation code, and their tests.

## Course-material claims

- Story map and five engine stages: materials/Story Map and Engine Architecture (5).pdf, slides 3--4; SHA-256 717d08368532b9e5a5522c334d9fbd38c57975a745f14700abb57d8a428b3268.
- Story-map narrative and acceptance criteria: materials/Thesis_Story Map 2026 (4).pdf, pages 1--6; SHA-256 b04f0a9f0b01e7365641e4437fec7d5b5a90849bc6758b63f4e799ae7b4cbf54.
- Prototype flow, screen inventory, usability script, task targets, and questionnaires: materials/UIUXMockups(1).pdf, slides 3--12; SHA-256 03bad5c1954f26f9462a485ca6175fa45e327105c653f9d022a39f7bc9afaf7d.
- Five-participant result counts and design responses: materials/UsabilityTests(1).pdf, slides 3--10; SHA-256 4f28bae6b3b3d89c8150ab7b2f7ff8d2917d2dac679d26f8f21b54a6b8f14b35.
- Recorded task counts: T1 5/5, T2 5/5, T3 5/5, T4 2/5, T5 4/5. The chapter derives only the descriptive total 21/25 = 84%; it does not infer a population rate.
- Missing evidence explicitly bounded in the chapter: participant demographics and recruitment, participant-level questionnaire responses, time-on-task, tap counts, hesitation duration, free-response transcripts, and a retest of the graph redesign.

## Engineering claim locators

- Revision-aware paper identity and migrations: backend/src/mneme/models/paper.py, backend/src/mneme/repositories/arxiv_ingestion.py, and Alembic revisions under backend/alembic/versions/.
- Durable jobs, canonical idempotency, dispatch leasing, and recovery: backend/src/mneme/repositories/job_identity.py, backend/src/mneme/repositories/jobs.py, and backend/src/mneme/tasks/.
- Bounded download, atomic artifact publication, parsing tiers, and section-aware chunking: backend/src/mneme/services/documents/, backend/src/mneme/ai/chunking.py, and backend/src/mneme/core/config.py.
- Retrieval, deterministic reranking, evidence threshold, marker validation, and local lexical source matching: backend/src/mneme/ai/retrieval.py, backend/src/mneme/ai/qa.py, backend/src/mneme/api/routes/qa.py, and backend/src/mneme/api/schemas/qa.py.
- Provider routing, caching, usage metadata, and budget guard: backend/src/mneme/ai/service.py, backend/src/mneme/ai/cache.py, backend/src/mneme/ai/budget.py, and provider adapters under backend/src/mneme/ai/providers/.
- Contrastive behavioral semantics, exposure gating, continuous duration weighting, dual-timescale decay, per-paper saturation, separate profile channels, and confidence calculation: docs/adr/0003-behavior-v2.md, backend/src/mneme/services/behavior_v2.py, and backend/src/mneme/services/behavior_v2_profile.py at the behavior-model source snapshot above.
- Transactional event ingestion, duplicate handling, deterministic replay, and profile persistence: backend/src/mneme/services/events.py, backend/src/mneme/repositories/events.py, backend/src/mneme/cli/recompute_behavior.py, backend/src/mneme/api/routes/events.py, and backend/alembic/versions/0007_add_behavior_v2_profile.py at the behavior-model source snapshot above.
- Confidence-scaled contrastive affinity, component renormalization, recency decay, deterministic reasons, and immutable digest snapshots: backend/src/mneme/ai/recommendation.py, backend/src/mneme/services/recommendation.py, and backend/src/mneme/repositories/digests.py at the behavior-model source snapshot above.
- Explicit-interest correction: the Android interest editor and ViewModel under android/app/src/main/java/com/mneme/app/ui/, the network repository preference-to-briefing transition, the preference API and repository, and digest freshness invalidation. The controlled scorer results and run manifest are retained under docs/evaluation/explicit-interest-correction/.
- Citation observation persistence, deferred identity resolution, bounded traversal, graph algorithms, and fallback: backend/src/mneme/repositories/citation_graph.py, backend/src/mneme/repositories/graph_queries.py, backend/src/mneme/graph/algorithms.py, and backend/src/mneme/services/graph.py.
- API versioning, authentication, errors, request correlation, and the 13-operation surface: backend/src/mneme/main.py, backend/src/mneme/api/router.py, backend/src/mneme/api/dependencies/auth.py, backend/src/mneme/core/security.py, backend/src/mneme/api/errors.py, and docs/api/openapi-v0.1.yaml.
- Android unidirectional state flow and transport/presentation separation: docs/thesis-handoffs/hanyang/chapter-3-android-design.md plus android/app/src/main/java/com/mneme/app/ui/MnemeViewModel.kt, android/app/src/main/java/com/mneme/app/ui/SkeletalUiState.kt, android/app/src/main/java/com/mneme/app/ui/home/HomeUiState.kt, android/app/src/main/java/com/mneme/app/data/repository/, and android/app/src/main/java/com/mneme/app/data/network/MnemeApiClient.kt at the Android/UI snapshot above.
- Stable paper-identity navigation, graph-selection restoration, bridge validation, main-thread callback, native selection context, and Open Paper action: android/app/src/main/java/com/mneme/app/ui/MnemeApp.kt, android/app/src/main/java/com/mneme/app/ui/MnemeGraphNavigation.kt, android/app/src/main/java/com/mneme/app/ui/graph/CitationGraphWebView.kt, android/app/src/main/java/com/mneme/app/ui/graph/GraphScreen.kt, android/app/src/androidTest/java/com/mneme/app/ui/MnemeAppFlowTest.kt, and android/app/src/androidTest/java/com/mneme/app/ui/graph/GraphScreenTest.kt at the Android/UI snapshot above.
- Android data origin, cache restoration, and duplicate-safe behavioral-event synchronization: source and tests under android/app/src/, including the Room event store and sync coordinator, checked against the server contract. Chapter 3 uses these components as design evidence rather than as technical-evaluation results. The retained E4 measurements remain Chapter 4 evidence and are not used to infer usability, graph construction or ranking quality, recommendation adaptation, notification delivery, or background-worker policy. Claims about full event-vocabulary emission and heterogeneous public graph nodes are deliberately excluded.

## Figure provenance

- Figures storymap, system-architecture, document-dag, and ui-flow are original SVG diagrams under figures/src/ and remain embedded in Chapter 3 as high-resolution PNGs. Their layout was revised for legibility in the supervisor template; the SVG files remain the editable source of truth.
- The behavior-loop PNG and editable SVG were removed from rendered Chapter 3 together with the behavior equations and pseudocode. They remain available to Chapter 4 through transfer packet `CH3-OUT-003` and must not be counted as a Chapter 3 figure.
- Reproducible diagram-rendering script: figures/src/render_chapter3_diagrams.sh. It uses librsvg to generate the five PNGs at their declared 2400-pixel widths.
- chapter3_storymap.png: SHA-256 024a85ce241270e22150f927aa93f54755eb98278257918d80e6a6cc23ceb7f4.
- chapter3_system_architecture.png: SHA-256 e79e0970912adb387a025c5cdc3f85f0026adf4743560d62501283fdc7af7346.
- chapter3_document_dag.png: SHA-256 e89f53a19b555ca66e812302c69681fd22f6e09c75d30e38740705de7da50bae.
- chapter3_behavior_loop.png: SHA-256 79eb489856ef0b46bf77bb588c10ffbb01f79ff5518ba45361de97466b453588.
- chapter3_ui_flow.png: SHA-256 46793959ae81202499022cf390a81fa780349f4383a8aec2ea945920bf8ed67c.
- Figures api-sequence and usability-results remain original TikZ diagrams embedded in contents/chapter_3.tex, derived from the sources above. The former inline Q&A method flow was removed from rendered Chapter 3 and is represented by transfer packet `CH3-OUT-002`.
- Prototype source: materials/Mneme_demo.html; SHA-256 491799d4812c6118d3a3eff139f640b48e38f17b4b4adad205ca85d7d07a4f5f.
- Reproducible capture script: figures/src/capture_prototype.cjs.
- prototype_digest.png: SHA-256 e1adb5e13c61d406f90d09a7cb578282e96c8add37e9c12937d54a7534f0d418.
- prototype_summary.png: SHA-256 dd66b6d9d5efa83836356edf182e3df1bda2c6dc8e7b4e369f477072117cac33.
- prototype_qa.png: SHA-256 ebbc2c6a1cc63f57045e021fe94768ec1bb69e7fd6db286bcd246f2e1aba9c82.
- prototype_graph.png: SHA-256 e4b389db9a39381a8030cdeccf733a926a33000255f1771e48315e7fdc04418c.
- All prototype captures are fixtures and are labelled as such in the rendered captions. In particular, concept and author tabs in the graph prototype do not describe the paper-only public graph schema.

## Verified scholarly references

- Lewis et al. (2020), Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. Official NeurIPS proceedings: https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html
- Gao et al. (2023), Enabling Large Language Models to Generate Text with Citations. ACL Anthology and DOI: https://aclanthology.org/2023.emnlp-main.398/ and https://doi.org/10.18653/v1/2023.emnlp-main.398
- Wang et al. (2024), Searching for Best Practices in Retrieval-Augmented Generation. ACL Anthology and DOI: https://aclanthology.org/2024.emnlp-main.981/ and https://doi.org/10.18653/v1/2024.emnlp-main.981
- Niu et al. (2024), RAGTruth: A Hallucination Corpus for Developing Trustworthy Retrieval-Augmented Language Models. ACL Anthology and DOI: https://aclanthology.org/2024.acl-long.585/ and https://doi.org/10.18653/v1/2024.acl-long.585
- Ramos et al. (2024), Transparent and Scrutable Recommendations Using Natural Language User Profiles. ACL Anthology and DOI: https://aclanthology.org/2024.acl-long.753/ and https://doi.org/10.18653/v1/2024.acl-long.753
- Amershi et al. (2019), Guidelines for Human-AI Interaction. ACM DOI and Microsoft Research publication page: https://doi.org/10.1145/3290605.3300233 and https://www.microsoft.com/en-us/research/publication/guidelines-for-human-ai-interaction/
- Android Developers, Build an Offline-First App. Official platform guide inspected 2026-07-28: https://developer.android.com/topic/architecture/data-layer/offline-first
- Head et al. (2021), Augmenting Scientific Papers with Just-in-Time, Position-Sensitive Definitions of Terms and Symbols. ACM DOI: https://doi.org/10.1145/3411764.3445648
- Munzner (2009), A Nested Model for Visualization Design and Validation. IEEE DOI and PubMed record: https://doi.org/10.1109/TVCG.2009.111 and https://pubmed.ncbi.nlm.nih.gov/19834155/
- Yi et al. (2007), Toward a Deeper Understanding of the Role of Interaction in Information Visualization. IEEE DOI and institutional record: https://doi.org/10.1109/TVCG.2007.70515 and https://www.research.ed.ac.uk/en/publications/toward-a-deeper-understanding-of-the-role-of-interaction-in-infor/
- Brehmer and Munzner (2013), A Multi-Level Typology of Abstract Visualization Tasks. IEEE DOI and UBC project record: https://doi.org/10.1109/TVCG.2013.124 and https://www.cs.ubc.ca/labs/imager/tr/2013/MultiLevelTaskTypology/
- Fan et al. (2019), Concurrent Think-Aloud Verbalizations and Usability Problems. ACM DOI: https://doi.org/10.1145/3325281

| Bib key | Metadata fields cross-checked | Claim supported in Chapter 3 | Result |
| --- | --- | --- | --- |
| lewis2020rag | Title, 12-author order, editors, venue, volume, pages 9459--9474, publisher, year, proceedings URL | RAG combines parametric generation with explicit non-parametric memory; official abstract, lines describing the two memories | Verified |
| gao2023alce | Title, four-author order, EMNLP 2023, pages 6465--6488, DOI | Answer correctness is evaluated separately from citation quality; citation quality includes support coverage and relevance | Verified |
| wang2024bestpractices | Title, 14-author order, EMNLP 2024, pages 17716--17736, DOI | RAG configuration choices, including chunking and context strategy, trade performance against efficiency; no universal optimum is claimed | Verified |
| niu2024ragtruth | Title, eight-author order, ACL 2024, pages 10862--10878, DOI | Retrieved context can coexist with unsupported or contradictory generated claims | Verified |
| ramos2024scrutable | Title, five-author order, ACL 2024, pages 13971--13984, DOI | Inspectable and editable user profiles motivate scrutable recommendation representations | Verified |
| amershi2019guidelines | Title, 13-author order, CHI 2019, pages 1--13, DOI | Human-AI interfaces should set expectations and support correction of wrong inferences | Verified |
| androidOfflineFirst2026 | Corporate author, title, official URL, access date | Offline-first design assigns local/network reconciliation to repositories and supports immediate local reads | Verified |
| head2021scholarphi | Title, seven-author order, CHI 2021, article length, DOI | Position-sensitive reading support presents contextual information at the point of need | Verified |
| munzner2009nested | Title, author, TVCG 15(6), pages 921--928, DOI | Visualization design separates domain/task abstraction, encoding/interaction, and algorithm layers | Verified |
| yi2007interaction | Title, four-author order, TVCG 13(6), pages 1224--1231, DOI | Selection and exploration are distinct categories of visualization interaction | Verified |
| brehmer2013typology | Title, two-author order, TVCG 19(12), pages 2376--2385, DOI | Task analysis distinguishes why, what, and how an interaction is performed | Verified |
| fan2019thinkaloud | Title, four-author order, TOCHI 26(5), article 28, pages 1--35, DOI | Concurrent think-aloud is used in usability testing, and verbalization patterns vary in their relation to usability problems | Verified |

## Claim boundaries for editorial review

- Ordered pgvector cosine search is described without an approximate-nearest-neighbor claim.
- Source matching is described as marker validity plus local lexical support, not semantic entailment, scientific truth, or citation correctness.
- Q&A is scoped to one paper revision; conversation identity is not described as history-conditioned generation.
- Public citation responses are not described as character-span or page-level annotations.
- PDF parsing is limited to implemented layout recovery, likely marginal-block filtering, and heading detection; repeated-header/footer removal is not claimed.
- Summary artifacts retain a fuller generation identity than Q&A messages. Q&A telemetry supports audit and partial reconstruction but is not described as sufficient for exact regeneration.
- FastAPI's runtime schema is OpenAPI 3.1.0; docs/api/openapi-v0.1.yaml is the frozen OpenAPI 3.0.3 compatibility specification.
- The public graph contains paper nodes and citation edges; heterogeneous prototype nodes are labelled as exploratory fixtures.
- Followed authors are stored explicit preferences but are not described as a recommendation-scoring component.
- Process health is not described as database, Redis, or provider health.
- The usability findings are formative, task-specific, and not evidence of model, ranking, runtime, or redesign effectiveness.
- The graph adjustments were not tested in a second participant study. Chapter 3 reports the observed problem and resulting design change only; Chapter 4 functional tests must not be used to claim improved usability.
- Chapter 3 contains no algorithm, equation, pseudocode, model-weight table, backend implementation procedure, final-product screenshot, or performance result. The implementation-level material is preserved in `CH3-OUT-001` through `CH3-OUT-006` for owner-local Chapter 4 integration.
