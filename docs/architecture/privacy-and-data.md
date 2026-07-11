# Privacy, Licensing, and Reproducibility

This is the MVP engineering policy, not legal advice. Re-check provider policies before a
public release.

## Paper Content

- Store arXiv metadata with attribution and a canonical source URL.
- Record each paper's declared license in `papers.source_license`.
- Cache only PDFs required for processing/demo; do not publish a bulk PDF mirror.
- PDF redistribution and derivative use follow each paper's individual license.
- Delete cached PDFs after the configured retention period while preserving derived
  metadata when the source license and project purpose allow it.

## User and Provider Data

- The UI discloses that questions and selected paper excerpts may be sent to configured
  external LLM/embedding providers.
- Do not send unnecessary profile fields, raw behavioral history, secrets, or identifiers.
- Never log API keys, authorization headers, full prompts, full answers, or paper text.
- Development uses synthetic users; demo behavior history contains no real personal data.
- OpenAI API data is not used for training by default unless the organization opts in;
  default abuse-monitoring retention may be up to 30 days. See
  <https://platform.openai.com/docs/models/default-usage-policies-by-endpoint>.
- Anthropic API inputs and outputs are normally deleted within 30 days, with policy/legal
  exceptions and different terms possible by agreement. See
  <https://privacy.anthropic.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data>.
- At project end, revoke provider keys and delete the cloud database, cached PDFs, backups,
  and object-store artifacts unless the team documents a new retention purpose.

## Generated-Artifact Metadata

Every summary, embedding batch, Q&A response, recommendation run, and graph-algorithm run
records enough metadata to reproduce or invalidate it:

- provider and exact model snapshot;
- prompt/algorithm/pipeline version;
- temperature and relevant generation parameters;
- input/content hash;
- timestamp, latency, token usage, and estimated cost.

Provider configuration and secrets live in environment variables or a secret manager,
never in source control or Android resources.
