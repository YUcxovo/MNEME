# Chapter 3 provenance ledger

This file is a non-rendered evidence ledger for contents/chapter_3.tex. It records the source of design claims, figures, study results, and bibliography entries so that later editorial work can distinguish internal evidence from interpretation. The rendered chapter must not expose repository workflow or use this ledger as a substitute for a scholarly citation.

## Source snapshot

- MNEME source identity inspected for the chapter: 947029d6d24232e5bcdc9297f65ada53cdf3aec2.
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
- Behavioral weights, duration multipliers, half-life, 90-day window, transactional ingestion, and duplicate handling: backend/src/mneme/services/behavior.py, backend/src/mneme/services/events.py, backend/src/mneme/repositories/events.py, and backend/src/mneme/api/routes/events.py.
- Recommendation weights, recency decay, signal renormalization, deterministic reasons, and immutable digest snapshots: backend/src/mneme/ai/recommendation.py, backend/src/mneme/services/recommendation.py, and backend/src/mneme/repositories/digests.py.
- Citation observation persistence, deferred identity resolution, bounded traversal, graph algorithms, and fallback: backend/src/mneme/repositories/citation_graph.py, backend/src/mneme/repositories/graph_queries.py, backend/src/mneme/graph/algorithms.py, and backend/src/mneme/services/graph.py.
- API versioning, authentication, errors, request correlation, and the 13-operation surface: backend/src/mneme/main.py, backend/src/mneme/api/router.py, backend/src/mneme/api/dependencies/auth.py, backend/src/mneme/core/security.py, backend/src/mneme/api/errors.py, and docs/api/openapi-v0.1.yaml.
- Android data origin, networking, cache restoration, navigation, paper Q&A, graph boundary, and duplicate-safe behavioral-event synchronization: source and tests under android/app/src/, including the Room event store, sync coordinator, and WorkManager worker, checked against the server contract. Chapter 3 uses these components as design evidence rather than as technical-evaluation results. Claims about periodic briefing notifications, full event-vocabulary emission, and heterogeneous public graph nodes are deliberately excluded.

## Figure provenance

- Figures storymap, system-architecture, document-dag, and ui-flow are original SVG diagrams under figures/src/ and are embedded in the chapter as high-resolution PNGs. Their layout was revised for legibility in the supervisor template; the SVG files remain the editable source of truth.
- Reproducible diagram-rendering script: figures/src/render_chapter3_diagrams.sh. It uses librsvg to generate the four PNGs at their declared 2400-pixel widths.
- chapter3_storymap.png: SHA-256 024a85ce241270e22150f927aa93f54755eb98278257918d80e6a6cc23ceb7f4.
- chapter3_system_architecture.png: SHA-256 e79e0970912adb387a025c5cdc3f85f0026adf4743560d62501283fdc7af7346.
- chapter3_document_dag.png: SHA-256 e89f53a19b555ca66e812302c69681fd22f6e09c75d30e38740705de7da50bae.
- chapter3_ui_flow.png: SHA-256 46793959ae81202499022cf390a81fa780349f4383a8aec2ea945920bf8ed67c.
- Figures qa-flow, behavior-loop, api-sequence, and usability-results remain original TikZ diagrams embedded in contents/chapter_3.tex, derived from the sources above.
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

| Bib key | Metadata fields cross-checked | Claim supported in Chapter 3 | Result |
| --- | --- | --- | --- |
| lewis2020rag | Title, 12-author order, editors, venue, volume, pages 9459--9474, publisher, year, proceedings URL | RAG combines parametric generation with explicit non-parametric memory; official abstract, lines describing the two memories | Verified |
| gao2023alce | Title, four-author order, EMNLP 2023, pages 6465--6488, DOI | Answer correctness is evaluated separately from citation quality; citation quality includes support coverage and relevance | Verified |
| wang2024bestpractices | Title, 14-author order, EMNLP 2024, pages 17716--17736, DOI | RAG configuration choices, including chunking and context strategy, trade performance against efficiency; no universal optimum is claimed | Verified |
| niu2024ragtruth | Title, eight-author order, ACL 2024, pages 10862--10878, DOI | Retrieved context can coexist with unsupported or contradictory generated claims | Verified |
| ramos2024scrutable | Title, five-author order, ACL 2024, pages 13971--13984, DOI | Inspectable and editable user profiles motivate scrutable recommendation representations | Verified |
| amershi2019guidelines | Title, 13-author order, CHI 2019, pages 1--13, DOI | Human-AI interfaces should set expectations and support correction of wrong inferences | Verified |

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
