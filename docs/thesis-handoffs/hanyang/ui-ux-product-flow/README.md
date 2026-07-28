# Android product-flow screenshots

This directory contains the retained screenshots for the final Android
product-flow presentation requested in the supervisor feedback. The images are
individual captures so that the Chapter 4 owner can arrange them as readable
subfigures without treating a contact sheet as the only evidence.

## Capture environment

- Device: Pixel 9 Pro XL emulator
- Android: API 34
- Resolution: 1344 x 2992
- Emulator resources: 6 CPU cores and 8 GB RAM
- Seed: `https://arxiv.org/abs/1706.03762`
- Data path: Android connected to the live local FastAPI, PostgreSQL, Redis,
  worker, DeepSeek completion, and local FastEmbed embedding services
- Graph result: six local papers and five persisted directed citations

The database was empty before the seed-onboarding run. The candidate papers,
paper summaries, citation edges, cited answer, explicit-interest update, and
refreshed briefing were returned through the backend during the capture
session.

## Suggested figure groups

### 1. Seed onboarding and briefing

1. `01-seed-onboarding.png`
2. `02-seed-entered.png`
3. `03-seed-processing.png`
4. `04-live-briefing-top.png`
5. `05-live-briefing-paper-list.png`

This group shows the user-supplied arXiv seed, the visible processing state,
and the resulting multi-paper briefing.

### 2. Reading and citation exploration

1. `06-paper-detail-top.png`
2. `07-paper-summary-claims.png`
3. `08-multi-node-citation-graph.png`
4. `09-graph-selected-node.png`
5. `10-open-selected-paper.png`

This group shows the transition from a paper account to a six-node citation
neighbourhood, persistent node selection, and graph-to-paper navigation.

### 3. Evidence-linked question answering

1. `11-paper-question-composer.png`
2. `12-question-entered.png`
3. `13-question-processing.png`
4. `14-cited-answer.png`
5. `15-answer-source-evidence.png`

This group shows an open user question, the processing state, the cited
answer, and inspection of the supporting source card.

### 4. Explicit-interest correction

1. `16-interest-profile.png`
2. `17-interest-topic-added.png`
3. `18-interest-refresh-completed.png`
4. `19-briefing-after-interest-update.png`

This group shows an explicit preference edit, backend persistence, refresh,
and the subsequent briefing state.

### 5. Offline and live recovery

1. `21-offline-cached-briefing.png`
2. `22-live-recovery-after-offline.png`

This pair shows a complete cached briefing while the API is unavailable and
the same workflow after live connectivity is restored.

## Overview images

- `contact-sheet-01-product-loop.png`
- `contact-sheet-02-qa-preference-recovery.png`

The contact sheets are for quick review. The individual screenshots should be
used in the thesis when labels and interface text need to remain readable.

## Evidence boundary

These captures demonstrate the Android interaction flow and the live
client-backend path used in the session. They do not measure retrieval
quality, generated-answer correctness, recommendation quality, graph
construction quality, or general performance across devices.
