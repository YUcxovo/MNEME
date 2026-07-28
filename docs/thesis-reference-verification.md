# Thesis Reference Verification

Date: 28 July 2026

## Scope

The audit covered every source cited in the rendered thesis: twenty-four academic
publications and twelve official product, service, or platform pages. Academic metadata was
checked against Crossref and the official publisher or proceedings record.
Product claims were checked against the cited vendor's official documentation.

## Result

- All twenty-four academic entries match the official title, author order, year,
  venue, pages, and DOI. The NeurIPS record for Lewis et al. has no DOI.
- All twelve product, service, and platform references resolve to an official source.
- The Google source formerly titled *Use Chat in NotebookLM* now redirects to
  *Use Chat in Gemini Notebook*. The title, URL, and product name were updated.
- Two academic claim-to-source mismatches were corrected:
  - Zhang et al. define continued engagement and silent disengagement as
    positive and negative unpaired signals; the thesis no longer describes
    their meanings as inherently unstable.
  - Wang et al. support effects on retrieval quality and answer faithfulness;
    the thesis no longer attributes a processing-cost result to that study.
- Comparative statements about literature assistants, reference managers, and
  graph tools were narrowed to the capabilities documented by their official
  sources.

## Verified Academic Sources

| Key | Official record |
|---|---|
| `lewis2020rag` | [NeurIPS](https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html) |
| `gao2023alce` | [ACL Anthology](https://aclanthology.org/2023.emnlp-main.398/) |
| `liu2024lost` | [ACL Anthology](https://aclanthology.org/2024.tacl-1.9/) |
| `wadden2020scifact` | [ACL Anthology](https://aclanthology.org/2020.emnlp-main.609/) |
| `amershi2019guidelines` | [Microsoft Research](https://www.microsoft.com/en-us/research/publication/guidelines-for-human-ai-interaction/) |
| `zhao2024longrag` | [ACL Anthology](https://aclanthology.org/2024.emnlp-main.1259/) |
| `wang2024bestpractices` | [ACL Anthology](https://aclanthology.org/2024.emnlp-main.981/) |
| `niu2024ragtruth` | [ACL Anthology](https://aclanthology.org/2024.acl-long.585/) |
| `huang2024grounded` | [ACL Anthology](https://aclanthology.org/2024.findings-acl.838/) |
| `ramos2024scrutable` | [ACL Anthology](https://aclanthology.org/2024.acl-long.753/) |
| `zhang2025unpaired` | [ACL Anthology](https://aclanthology.org/2025.findings-emnlp.1332/) |
| `russell1993sensemaking` | [ACM Digital Library](https://doi.org/10.1145/169059.169209) |
| `fortunato2018science` | [Science](https://doi.org/10.1126/science.aao0185) |
| `lo2020s2orc` | [ACL Anthology](https://aclanthology.org/2020.acl-main.447/) |
| `tkaczyk2015cermine` | [Springer](https://doi.org/10.1007/s10032-015-0249-8) |
| `raghavan2007label` | [Physical Review E](https://doi.org/10.1103/PhysRevE.76.036106) |
| `hu2008implicit` | [IEEE](https://doi.org/10.1109/ICDM.2008.22) |
| `koren2009temporal` | [ACM Digital Library](https://doi.org/10.1145/1557019.1557072) |
| `head2021scholarphi` | [ACM Digital Library](https://doi.org/10.1145/3411764.3445648) |
| `jones2002keeping` | [Wiley](https://doi.org/10.1002/meet.1450390143) |
| `fan2019thinkaloud` | [ACM Digital Library](https://doi.org/10.1145/3325281) |
| `munzner2009nested` | [IEEE Xplore](https://doi.org/10.1109/TVCG.2009.111) |
| `yi2007interaction` | [IEEE Xplore](https://doi.org/10.1109/TVCG.2007.70515) |
| `brehmer2013typology` | [IEEE Xplore](https://doi.org/10.1109/TVCG.2013.124) |

## Verified Platform Design Sources

| Key | Official record |
|---|---|
| `googleScholarHelp2026` | [Google Scholar Search Help](https://scholar.google.com/intl/us/scholar/help.html) |
| `arxivAnnual2023` | [arXiv Annual Report 2023](https://info.arxiv.org/about/reports/2023_arXiv_annual_report.pdf) |
| `semanticScholarProduct2026` | [Semantic Scholar Product](https://www.semanticscholar.org/product) |
| `elicitHelp2026` | [Elicit Help Centre](https://support.elicit.com/en/articles/14757967-why-elicit-is-different-from-other-research-tools) |
| `consensusHelp2026` | [Consensus Help Centre](https://help.consensus.app/en/articles/9922673-how-consensus-works) |
| `scispaceHelp2026` | [SciSpace Help Centre](https://scispace.com/help/en/articles/10660587-how-to-conduct-a-literature-review-using-scispace) |
| `notebookLMHelp2026` | [Gemini Notebook Help](https://support.google.com/gemininotebook/answer/16179559) |
| `zoteroDocs2026` | [Zotero PDF Reader and Note Editor](https://www.zotero.org/support/pdf_reader) |
| `zoteroSync2026` | [Zotero Syncing](https://www.zotero.org/support/sync) |
| `connectedPapersAbout2026` | [About Connected Papers](https://www.connectedpapers.com/about) |
| `androidOfflineFirst2026` | [Android Developers: Build an offline-first app](https://developer.android.com/topic/architecture/data-layer/offline-first) |
| `androidWorkManager2026` | [Android Developers: Task scheduling](https://developer.android.com/develop/background-work/background-tasks/persistent) |

## Remaining Author Check

Before submission, a second author should compare the rendered bibliography
against this report and confirm that the thesis still cites the intended source
after any later prose edits.
