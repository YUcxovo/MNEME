# Citation integrity audit

Date checked: 2026-08-10

## Scope

This audit checks two separate questions:

1. whether every bibliography record corresponds to a real source and accurately
   records its bibliographic metadata; and
2. whether the statement attached to each in-text citation is supported by that
   source.

All 42 records in `refs.bib` were checked against publisher records, official
proceedings pages, Crossref records, or first-party product documentation. The
claim audit covered every `\cite{...}` occurrence in the thesis source. Product
documentation was accepted only as evidence of documented product capabilities or
prices, not as evidence of research effectiveness.

## Mechanical integrity

- Bibliography records: **42**
- Records cited in the thesis: **39**
- Missing citation keys: **0**
- Duplicate bibliography keys: **0**
- Undefined citations in the latest build: **0**
- Real but currently uncited records: `es2024ragas`, `saadfalcon2024ares`, and
  `katsis2025mtrag`

The three uncited records are not printed because the thesis does not use
`\nocite{*}`. They were nevertheless verified and are not fabricated records.

## Claim-to-source audit

| Claim family in the thesis | Sources checked | Result |
|---|---|---|
| Retrieval-augmented generation supplies retrieved non-parametric context | Lewis et al. (2020) | Supported by the method description of RAG. |
| Long-context position effects and the local/global retrieval trade-off | Liu et al. (2024); Zhao et al. (2024) | Supported. The thesis uses these sources to motivate design constraints, without attributing MNEME's results to them. |
| Scientific claims, rationale spans, fine-grained attribution, hallucination, and citation correctness/completeness | Wadden et al. (2020); Huang et al. (2024); Niu et al. (2024); Gao et al. (2023) | Supported. The cited works respectively cover claim--evidence rationales, fine-grained grounded citations, hallucinations in RAG outputs, and citation correctness/completeness. |
| Implicit feedback confidence, temporal preference drift, editable user profiles, and unpaired long-term feedback | Hu et al. (2008); Koren (2009); Ramos et al. (2024); Zhang et al. (2025) | Supported. The continued-engagement and silent-disengagement wording is stated explicitly in Zhang et al.'s abstract. |
| Science as a network, sensemaking, and personal information keeping | Fortunato et al. (2018); Russell et al. (1993); Jones et al. (2002) | Supported at the level used in the background section. |
| Position-sensitive reading assistance and human--AI correction | Head et al. (2021); Amershi et al. (2019) | Supported. |
| Visualization design levels and interaction/task taxonomies | Munzner (2009); Yi et al. (2007); Brehmer and Munzner (2013) | Supported. The weighted graph construction remains MNEME's own design; Raghavan et al. (2007) is cited only for the underlying label-propagation method. |
| Think-aloud verbalization and usability-problem evidence | Fan et al. (2019) | Supported. |
| Scientific-document structure extraction and structured scholarly corpora | Tkaczyk et al. (2015); Lo et al. (2020) | Supported. |
| Chunking choices affect retrieval and answer quality | Wang et al. (2024) | Supported. The thesis presents its 450/60 setting as a fixed study configuration, not as an optimum reported by the source. |
| Android offline-first access and persistent background work | Android Developers documentation | Supported as platform guidance. |
| Google Scholar, arXiv, Semantic Scholar, Elicit, Consensus, SciSpace, Gemini Notebook, Zotero, and Connected Papers capabilities | First-party documentation for each product | Supported. These citations describe available functions only. |
| Anthropic, DeepSeek, and OpenAI prices | First-party pricing/model pages | Supported for the explicitly stated review date. |

## High-risk first-party checks

- Semantic Scholar's product page explicitly documents its personal library,
  Research Feeds, email alerts, TLDR summaries, and the limited “Ask This Paper”
  function with supporting statements.
- Zotero's synchronization documentation explicitly lists library items, notes,
  links, and tags, and distinguishes data synchronization from optional attachment
  synchronization. Its PDF-reader documentation states that annotations added to
  notes contain citations and links back to the PDF page.
- The arXiv annual report describes arXiv as an open-access host for scholarly
  articles shared by researchers. The thesis does not imply that arXiv peer-reviews
  those submissions.
- Connected Papers states that graph similarity is based on co-citation and
  bibliographic coupling rather than direct citation alone.
- The prices in Chapter 4 match the first-party pages reviewed on the date stated in
  the thesis. They are used as dated inputs to the cost calculation, not as permanent
  prices.

## Result

No fabricated, nonexistent, or misidentified reference was found. No in-text
citation was found to support an unrelated claim. The bibliography contains three
verified but unused records; they do not appear in the compiled thesis and may be
retained or removed without changing the cited literature.

Detailed field-by-field metadata evidence is recorded in
`reference-verification-report-2026-08-10.md`.
