# Android feature-acceptance results

This table supplies the product-level acceptance evidence requested for
Chapter 4. Each row is backed by a retained screenshot, connected-device test,
or raw E4 record. The chapter owner may shorten the table for layout, but
should keep the five fields `Feature`, `Test task`, `Expected result`, `Actual
result`, and `Status`.

| Feature | Test task | Expected result | Actual result | Status | Retained evidence |
| --- | --- | --- | --- | --- | --- |
| Seed onboarding | Enter a valid arXiv URL on first launch | Accept the user-supplied seed and expose the start action | The seed URL was accepted and the start action became available | Pass | `ui-ux-product-flow/02-seed-entered.png` |
| Paper preparation | Start the seed workflow | Show a visible processing state until backend preparation completes | The Android client displayed the preparation state before the briefing | Pass | `ui-ux-product-flow/03-seed-processing.png` |
| Initial briefing | Complete preparation from an empty database | Display five backend-prepared candidate papers | The live briefing contained five papers prepared from the seed | Pass | `ui-ux-product-flow/04-live-briefing-top.png`; `05-live-briefing-paper-list.png` |
| Paper detail | Open a paper from the briefing | Preserve paper identity and show its live metadata | The selected paper opened with title, metadata, overview, and actions | Pass | `ui-ux-product-flow/06-paper-detail-top.png` |
| Structured summary | Inspect the selected paper | Show claims, method, limitation, source trace, and next actions | All specified summary sections and paper actions were visible | Pass | `ui-ux-product-flow/07-paper-summary-claims.png` |
| Citation graph | Open the citation view for the selected paper | Render a multi-node graph returned through the backend path | The graph rendered six local papers and five directed citations | Pass | `ui-ux-product-flow/08-multi-node-citation-graph.png` |
| Graph selection | Select a non-centre graph node | Retain the selected state and enable a paper action | The selected node remained highlighted and Open Paper became available | Pass | `ui-ux-product-flow/09-graph-selected-node.png` |
| Graph-to-paper navigation | Use Open Paper on the selected node | Open the neighbouring paper through the ordinary detail path | The neighbouring paper opened as a standard paper-detail screen | Pass | `ui-ux-product-flow/10-open-selected-paper.png` |
| Question entry | Open the question composer and enter a free-form question | Preserve the user-entered question and expose submission | The typed question remained visible and could be submitted | Pass | `ui-ux-product-flow/11-paper-question-composer.png`; `12-question-entered.png` |
| Question processing | Submit the free-form question | Show a visible processing state while the backend answers | The Android client displayed the in-progress state until completion | Pass | `ui-ux-product-flow/13-question-processing.png` |
| Cited answer | Complete the question request | Display the backend answer with inline evidence markers | The returned answer contained inline citations and an evidence status | Pass | `ui-ux-product-flow/14-cited-answer.png` |
| Evidence inspection | Open the evidence associated with the answer | Show the matched source location and retain a paper action | The evidence card displayed the source passage and source-paper action | Pass | `ui-ux-product-flow/15-answer-source-evidence.png` |
| Explicit-interest editing | Add a research topic to the interest profile | Keep the edit visible before persistence | The new topic appeared in the editable interest list | Pass | `ui-ux-product-flow/16-interest-profile.png`; `17-interest-topic-added.png` |
| Interest persistence | Save the edited profile and refresh | Confirm backend persistence and complete the refresh | The save and recommendation refresh completed successfully | Pass | `ui-ux-product-flow/18-interest-refresh-completed.png` |
| Interest-to-briefing loop | Return to the briefing after the preference update | Display a refreshed briefing under the updated topics | The briefing displayed updated topics and six newly ranked catalogue papers | Pass | `ui-ux-product-flow/19-briefing-after-interest-update.png` |
| Offline recovery | Reopen the retained briefing while the API is unavailable | Display complete cached content and identify its origin | The cached briefing remained available with an offline disclosure | Pass | `ui-ux-product-flow/21-offline-cached-briefing.png`; `docs/evaluation/e4/raw/state_measurements.csv` |
| Live recovery | Restore the API after the offline state | Refresh the same workflow from the live backend | The briefing returned to a live-backend state after connectivity recovery | Pass | `ui-ux-product-flow/22-live-recovery-after-offline.png` |
| Event synchronization | Queue events, inject a retryable failure, retry, and replay identifiers | Preserve pending events, upload once, and acknowledge duplicate replay | All controlled queue stages passed; each of five live repetitions accepted three new identifiers and reported the three replays as duplicates | Pass | `docs/evaluation/e4/raw/event_sync_measurements.csv`; `docs/evaluation/e4/raw/live_event_closed_loop.csv` |

## Interpretation

The screenshot rows document one complete integrated Android session. The E4
rows add repeated controlled and live event evidence. These results establish
the listed client actions under the recorded conditions. They do not establish
scientific answer correctness, recommendation relevance, graph quality, or
performance across physical devices.
