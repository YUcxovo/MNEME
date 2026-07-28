# Hanyang Android and UI/UX thesis handoff

This directory supplies material for the Android and UI/UX parts of Chapters 3
and 4. It is an integration packet, not a replacement chapter. The chapter
owners remain responsible for fitting the material into the thesis argument,
removing duplication, and keeping terminology consistent with the surrounding
text.

## Integration ownership

| Target | Integration owner | Material supplied here |
| --- | --- | --- |
| Chapter 3: App Design | Ruiyu (`@YUcxovo`) | Android state architecture, UI/UX rationale, graph interaction boundary, and design-stage usability evidence |
| Chapter 4: Evaluation | Yifan (`@YifanZhang2026`) | Android E4 protocol, measured results, analysis, limitations, and sample thesis prose |

Hanyang (`@whyseagull`) remains the contact for questions about the Android
measurements and the intended UI behavior.

## Files in this packet

- [`chapter-3-android-design.md`](chapter-3-android-design.md) maps the supplied
  design material to the Chapter 3 template and provides sample prose.
- [`chapter-4-android-evaluation.md`](chapter-4-android-evaluation.md) gives the
  complete Android E4 method, results, interpretation, limitations, and sample
  prose.
- [`result-traceability.md`](result-traceability.md) maps every numerical claim
  in the sample writing to a retained artifact and records the permitted
  interpretation.
- [`feature-acceptance-results.md`](feature-acceptance-results.md) supplies the
  supervisor-requested product-level acceptance table with screenshot or raw
  test evidence for every row.
- [`ui-ux-course-assets/`](ui-ux-course-assets/) contains direct page exports
  of the original UI/UX flow, usability results, and design adjustments for
  Chapter 3.
- [`ui-ux-product-flow/`](ui-ux-product-flow/) contains the real integrated
  Android product-flow screenshots for Chapter 4.

## Canonical evidence

The canonical experiment record is
[`docs/evaluation/e4/`](../../evaluation/e4/). It contains:

- direct CSV measurements and the connected-device test report in
  [`raw/`](../../evaluation/e4/raw/);
- the recorded device environment and run manifest;
- machine-generated summaries in
  [`summary.csv`](../../evaluation/e4/summary.csv) and
  [`summary.json`](../../evaluation/e4/summary.json);
- publication-ready PNG and PDF figures in
  [`figures/`](../../evaluation/e4/figures/);
- the run and analysis commands in
  [`docs/evaluation/e4/README.md`](../../evaluation/e4/README.md).

The packet links to those files rather than duplicating them. This keeps a
single source of truth for the numerical results.

## Scope boundary

The supplied evidence evaluates the Android client in four areas:

1. process start and task foreground/resume time;
2. controlled UI-state transitions, cache disclosure, and asynchronous job
   polling;
3. citation-graph rendering and node-selection interaction on Android;
4. client event queueing, retry, duplicate handling, live upload, and
   readback.

It does not evaluate retrieval quality, generated-answer quality,
recommendation quality, graph ranking or clustering quality, notification
delivery, background-worker policy, or user preference modelling. Those topics
belong to other evaluation streams and must not be inferred from these
measurements.

The separate automatic citation-neighbourhood work is intentionally excluded
from the primary packet while its cross-layer implementation is still being
reviewed. The Chapter 4 sample therefore relies only on the merged and retained
E4 record.

## How to use the sample writing

The sample paragraphs are written in thesis style and contain no issue,
branch, pull-request, or commit narration. Chapter owners may adapt them, but
should preserve the numerical values, experimental qualifications, and scope
limitations. Repository paths and contributor names belong in this handoff
only; they should not be copied into the thesis body.
