# Final MVP Android screenshots

These screenshots were captured on 2026-08-10 from the integrated local MVP in
`MNEME-m5-integration`. The Android client ran on the
`Mneme_Pixel_9_Pro_XL_API_34` emulator (Android 14, six virtual CPU cores, and
14,336 MB RAM) and connected to the local FastAPI, PostgreSQL, Redis, and ARQ
services. Controlled Android fixtures were disabled.

The session began with seed `arXiv:1706.03762`. The briefing opened the paper
`arXiv:1703.03906`, which was saved, shared through the Android chooser, used for
two questions in one paper-scoped conversation, and explored through a
50-paper/53-edge citation graph. The weekly briefing was then generated through
the production recommender. Its maximum relevance was 0.856913, above the
configured 0.75 notification threshold, and the ordinary Android worker
published the notification.

| File | Recorded state |
| --- | --- |
| `01-paper-actions.png` | Source-linked paper detail with Save, Share, citation graph, and question actions |
| `02-saved-list.png` | Saved-paper collection after the selected paper was persisted |
| `03-share-chooser.png` | Android share chooser with the paper title and public arXiv URL |
| `04-qa-follow-up.png` | Second question and answer in the same paper-scoped conversation |
| `05-graph-all.png` | Complete 50-paper citation view with relation and category filters |
| `06-graph-references.png` | The same graph after applying the References filter |
| `07-weekly-notification.png` | Weekly research briefing notification at the standard threshold |
| `08-weekly-briefing.png` | Ten-paper weekly briefing opened from the notification |

The share chooser contains the paper title and public arXiv URL shown in the
recorded product flow.
