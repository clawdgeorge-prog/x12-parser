# X12 Parser Backlog

_Last updated: 2026-04-05_

This file is the standing backlog for future X12 parser work. It is intentionally broader than the completed top-5 hardening campaign and should be treated as a living list of ideas, not a promise that everything here is currently in scope.

## Status legend
- **Now** — strong candidate for near-term work
- **Soon** — worthwhile, but not urgent
- **Later** — valuable longer-term work
- **Watch** — monitor / revisit if evidence strengthens

---

# 1) Parser correctness / reliability

## 1.1 Repetition separator support beyond extraction
**Status:** Soon

- Current parser extracts ISA-11 repetition separator, but does not really use it for repeated-element parsing semantics.
- Worth implementing if we start seeing real files that rely on repetition semantics.

## 1.2 More robust delimiter and ISA validation
**Status:** Soon

- Delimiter detection was hardened, but the parser could still do more explicit ISA-shape validation.
- Potential additions:
  - verify fixed-width ISA expectations
  - detect malformed ISA before partial parse
  - return clearer diagnostics on malformed envelopes

## 1.3 Explicit malformed-envelope diagnostics
**Status:** Soon

- Build more precise failure classes/messages for:
  - broken ISA/IEA structure
  - broken GS/GE structure
  - malformed ST/SE wrappers
- Helpful for operators debugging bad files.

## 1.4 Fragment-aware validation mode refinement
**Status:** Now

- Fragment-aware mode now exists.
- Potential follow-ups:
  - add more explicit issue tags stating “fragment mode suppression applied”
  - expose mode semantics more clearly in JSON validator output
  - decide whether fragment-aware should become part of a richer validation policy object

---

# 2) 835-specific opportunities

## 2.1 Deeper 835 balancing / reconciliation logic
**Status:** Soon

- Current bounded balancing checks are useful, but public samples still expose reconciliation ambiguity.
- Future enhancements:
  - more nuanced BPR/CLP/SVC/PLB balancing
  - separate review flags from stronger balancing failures
  - better handling of payer-specific or atypical remittance patterns

## 2.2 Provider-level adjustment / PLB-heavy 835 support
**Status:** Soon

- Some external samples show unusual provider-level adjustment structures.
- Potential work:
  - better treatment of PLB-heavy or claim-light remittances
  - clearer validator messages when CLP absence is expected/unusual rather than simply missing

## 2.3 Optional 835 segment semantic expansion
**Status:** Watch

- TS2 / TS3 / MIA / MOA are now recognized in bounded form.
- Future work could add limited semantic extraction if stronger sample evidence accumulates.

## 2.4 More nuanced CLP status handling
**Status:** Watch

- Current warnings on non-standard public sample values are correct.
- Future opportunity: distinguish “outside standard X12 range” from “payer-specific/private-use style code” more explicitly in messaging.

## 2.5 Better handling of claim-without-service-line cases
**Status:** Watch

- External inpatient-style examples sometimes contain claim-level records without SVC detail.
- May justify a more nuanced validator rule or a softer warning tier depending on file class.

---

# 3) 837-specific opportunities

## 3.1 Institutional claim semantic depth
**Status:** Soon

- The parser now tolerates more 837I support segments, but institutional semantics remain bounded.
- Potential follow-up:
  - deeper CL1 / PWK / OI / SVD support
  - more explicit institutional claim summary fields
  - better handling of adjudication-related loops where relevant

## 3.2 Dental (837D) support maturity
**Status:** Soon

- Dental support still feels scaffolded/bounded.
- Potential work:
  - improve dental loop semantics
  - validate common dental service/attachment patterns more explicitly
  - strengthen examples/fixtures beyond simple detection

## 3.3 Professional support-segment refinement
**Status:** Watch

- PRV / MEA / PS1 / FRM support has been improved in bounded form.
- Add more semantic modeling only if more external/prod-like samples justify it.

## 3.4 Better multi-transaction 837 sample handling
**Status:** Watch

- Public sample sets include fragment/multi-ST examples that are useful but not always clean validators.
- Opportunity:
  - clearer reporting for multi-transaction fragments
  - improved sample classification in validator output

---

# 4) Validation architecture and rules

## 4.1 Validation pipeline modularization
**Status:** Later

- `validate()` remains large and could be split into smaller rule groups:
  - envelope checks
  - transaction checks
  - semantic checks
  - balancing / quality checks
- Good maintainability work, but not urgent if tests stay strong.

## 4.2 Rule severity / taxonomy cleanup
**Status:** Soon

- Could standardize issue taxonomy further:
  - structural error
  - semantic warning
  - sample-quality warning
  - review flag
- Would help users interpret output better.

## 4.3 Validation policy profiles
**Status:** Later

- Could evolve beyond `strict/default` and `fragment-aware` into formal policy profiles:
  - production-strict
  - sample-lenient
  - fragment-aware
  - research/forensic mode

## 4.4 Companion / payer-rule framework expansion
**Status:** Soon

- Foundation exists.
- Natural next steps:
  - more example rule packs
  - better docs and examples
  - limited rule testing against real-ish samples
  - careful public API cleanup so rule engine does not depend on parser internals unnecessarily

## 4.5 Public helper APIs for rule engines / downstream tools
**Status:** Soon

- The code review correctly pointed out some coupling risk.
- Expose stable public helper methods rather than relying on parser internals where practical.

---

# 5) Output modes / export quality

## 5.1 Output-mode verification automation
**Status:** Now

- We manually validated outputs against external samples.
- Worth turning that into a more formal regression harness or fixture-based export verification suite.

## 5.2 Better NDJSON contract documentation
**Status:** Soon

- NDJSON works, but the exact emitted record taxonomy could be documented more explicitly.

## 5.3 SQLite import ergonomics
**Status:** Soon

- Current SQLite bundle is practical.
- Possible future improvements:
  - optional SQLite DB generation directly
  - import helper script
  - DuckDB/Parquet export

## 5.4 CSV schema stability docs
**Status:** Soon

- Clarify which CSV columns are considered stable vs opportunistic.

## 5.5 Additional output formats
**Status:** Later

Potential future output modes:
- DuckDB / Parquet
- normalized JSONL by table type
- XML if a downstream need appears
- posting-oriented 835 extracts

---

# 6) External sample program / sample curation

## 6.1 Curated external sample matrix maintenance
**Status:** Now

- Continue improving:
  - `EXTERNAL_835_COMPATIBILITY_REPORT.md`
  - `EXTERNAL_SAMPLE_TAXONOMY.md`
  - `ROOT_CAUSE_ANALYSIS_EXTERNAL_SAMPLES.md`
- Keep them synchronized as the curated sample set grows.

## 6.2 Stronger Category A sample hunt
**Status:** Now

- Keep looking for:
  - full-envelope institutional 837 files
  - unusual but valid 835 remits
  - high-quality raw downloadable examples
- Avoid PDFs/snippets unless turned into clearly labeled research artifacts.

## 6.3 Curate `edx12_835_remittance.txt`
**Status:** Watch

- Promising candidate from the sample hunt.
- Needs direct inspection/verification before inclusion.

## 6.4 External sample metadata file
**Status:** Soon

- Create a machine-readable inventory describing:
  - source
  - file class (A/B/C)
  - expected validation posture
  - intended use (compatibility/demo/coverage)

## 6.5 Fragment sample strategy
**Status:** Soon

- Decide whether to keep fragment samples in main compatibility docs or separate them more clearly into a research bucket.

---

# 7) Performance / scale

## 7.1 Streaming parser for very large files
**Status:** Later

- Current large-file work is synthetic benchmark coverage, not a true streaming architecture.
- If bigger real files emerge, streaming may become worthwhile.

## 7.2 Parse/result cache design refinement
**Status:** Soon

- Basic caching/guards now exist.
- Could evolve into cleaner invalidation semantics if mutable parser usage grows.

## 7.3 Performance regression harness
**Status:** Soon

- Build an automated baseline check around the large synthetic 835 generator / benchmark tools.

---

# 8) Packaging / developer experience

## 8.1 One source of truth for versioning
**Status:** Soon

- Version consistency improved, but a single authoritative version source would be cleaner.
- Ideal future state:
  - package metadata
  - module exports
  - emitted parser metadata all aligned from one place

## 8.2 CLI error model cleanup
**Status:** Watch

- Top-level broad exception handling is currently acceptable, but a more structured exception hierarchy could improve automation UX later.

## 8.3 Entry-point / packaging polish
**Status:** Soon

- Continue removing brittle packaging assumptions and making the project friendlier for pip/CLI style usage.

## 8.4 Docs map / architecture overview
**Status:** Soon

- The repo now has several useful docs. A single “docs map” or architecture overview page would help future contributors navigate them.

---

# 9) Broader idea pool from the original development plan

These are ideas from the original X12 development plan that are still potentially valuable, but not yet immediate priorities.

## 9.1 Formal loop modeling by TR3 loop IDs
**Status:** Later

- Today’s practical loop model works, but canonical TR3 loop identity would improve deeper semantics and validation.

## 9.2 Full SNIP-style validation layering
**Status:** Later

- Syntax / semantic / balancing / business-rule tiers could be formalized further.

## 9.3 Code-set validation
**Status:** Later

- ICD/CPT/HCPCS/NPI/etc. validation may become useful if the project broadens from structural parser into richer operational validator.

## 9.4 Transport / ingestion pipeline
**Status:** Later

- AS2/SFTP/cloud transport concerns remain out of scope for the parser repo, but could become a separate adjacent project.

## 9.5 Outbound generation
**Status:** Later

- Generating X12 (835/837/etc.) is a separate product surface; not a current priority.

---

# 10) My additional ideas

## 10.1 Machine-readable issue recommendation mapping
**Status:** Soon

- Emit structured remediation guidance in validator JSON, not just human-readable recommendation text.

## 10.2 Confidence labeling in summaries/exports
**Status:** Watch

- Could label some derived values as direct / inferred / heuristic to improve transparency.

## 10.3 Sample-source provenance tracking
**Status:** Soon

- Keep source/provenance and curation notes close to curated external samples.

## 10.4 “Research mode” docs/examples
**Status:** Watch

- Since the repo increasingly supports public-sample forensics, documenting a research workflow could be useful.

## 10.5 Backlog triage rhythm
**Status:** Now

- Revisit this file periodically after each major hardening wave or code review.
- Keep it pruned and prioritized so it remains useful.

---

# 11) Strategic market-driven differentiators

These items come from the 2026-04-04 competitive analysis pass. They are not just “nice technical ideas”; they map to real gaps in the current X12 parsing / clearinghouse / developer-tool landscape.

Market signal behind them:
- clearinghouses (Waystar, Availity, Change/Optum) are strong on workflow, payer connectivity, edits, and operational scale, but weak on transparency and developer-friendly local parsing
- developer/integration platforms (Stedi, EDIdEv, Altova, Databricks) are strong on APIs, transformation, and integration, but often less specialized in explainable healthcare claim/remit analysis
- open-source parsers (LinuxForHealth/x12, imsweb/x12-parser, pyx12, Databricks x12-edi-parser) handle parsing/validation reasonably well, but usually leave whitespace in explainability, analytics-ready exports, payer-rule packaging, and messy-file forensics

## 11.1 Explainable validation v2
**Status:** Now

- Push beyond “valid/invalid” into a more operator- and developer-friendly diagnosis model.
- Priorities:
  - stable issue codes suitable for downstream automation
  - precise segment / loop / transaction coordinates in every issue
  - clearer separation of issue class:
    - X12-standard violation
    - payer / companion-guide rule violation
    - sample-quality / research artifact
    - review flag / reconciliation anomaly
  - structured remediation guidance in JSON output
- Why this matters:
  - many competitors can validate; fewer explain validation well
  - this is a realistic differentiator versus black-box clearinghouses and enterprise validators

## 11.2 Parser diff / regression comparison mode
**Status:** Soon

- Add a way to compare two files or two parse results and emit:
  - envelope / transaction differences
  - claim-level financial deltas
  - segment/tag additions/removals
  - validation-issue delta summary
- Why this matters:
  - useful for QA, payer testing, mapping changes, regression review, and external sample forensics
  - browser tools expose some version comparison UX, but local/CLI diff remains underserved

## 11.3 Research / forensic workflow mode
**Status:** Now

- Formalize support for messy real-world artifacts:
  - partial files
  - transaction fragments
  - redacted samples
  - broken public examples
  - hand-edited or malformed payer examples
- Possible additions:
  - explicit “research mode” policy/profile
  - stronger fragment-aware annotations
  - provenance tags in reports and exports
  - sample-quality classification in validator output
- Why this matters:
  - most products optimize for clean production transactions, but real teams constantly inspect ugly files
  - we already have momentum here; should lean into it intentionally

## 11.4 Companion-guide / payer-rule pack ecosystem
**Status:** Now

- Expand the current rule foundation into a real portable rule-pack system.
- Priorities:
  - versioned JSON rule packs
  - rule-pack test fixtures and golden outputs
  - pack metadata (payer, version, owner, effective dates)
  - docs on authoring and maintaining packs
  - public helper APIs that keep rule logic off private parser internals
- Why this matters:
  - enterprise platforms clearly sell custom edits, but often opaquely
  - transparent, file-based rule packs could become one of the strongest differentiators in the repo

## 11.5 Analytics-native export surface
**Status:** Now

- Keep pushing exports beyond raw JSON.
- High-value additions:
  - DuckDB / Parquet output
  - direct SQLite DB creation option
  - stronger NDJSON record-contract docs
  - stable CSV schema guarantees with version markers
  - import helpers for local analytics workflows
- Why this matters:
  - the market is proving that parsing is valuable when it unlocks downstream analytics, not just inspection
  - this is a practical middle ground between tiny parsers and heavy Spark-only workflows

## 11.6 AI-ready structured anomaly output
**Status:** Soon

- Add an output/profile designed for LLM and agent consumption without losing traceability.
- Potential shape:
  - anomaly blocks with issue code, severity, coordinates, explanation, recommendation
  - claim-level review summaries
  - confidence labels on inferred/derived fields
  - compact token-efficient summary views
- Why this matters:
  - AI is becoming part of RCM and developer workflows
  - the useful path is not “AI replaces parsing,” but “parser emits trustworthy structured facts AI can reason over”

## 11.7 Clearinghouse-adjacent preflight mode
**Status:** Soon

- Position the validator as the tool used before or beside clearinghouse submission.
- Potential features:
  - preflight summary focused on likely rejection risk
  - configurable severity thresholds / fail gates for CI or ETL
  - payer-profile-based warnings
  - exportable QA checklist output
- Why this matters:
  - strong market gap between full clearinghouses and standalone parsers
  - this could become a compelling “observability / preflight layer” use case

## 11.8 835 operational reconciliation expansion
**Status:** Soon

- Move further toward practical remittance-review support.
- Candidate enhancements:
  - stronger BPR vs CLP/SVC/PLB reconciliation breakdowns
  - explicit “review flags” vs “hard balancing failures”
  - provider-level adjustment narratives
  - payer-pattern heuristics kept clearly separate from standard validation
- Why this matters:
  - many tools process 835s, but fewer help humans interpret why the numbers feel off
  - this is a strong practical differentiator for revenue-cycle teams

## 11.9 837 institutional + dental depth for differentiation
**Status:** Soon

- Improve where many lightweight parsers stay shallow.
- Focus areas:
  - deeper 837I institutional semantics
  - better 837D loop/attachment/service semantics
  - clearer variant-specific summaries and validations
- Why this matters:
  - broad “837 supported” claims are common; high-quality institutional/dental depth is less common
  - sharper support here improves credibility and expands addressable workflows

## 11.10 Deployment ergonomics for cloud-native use
**Status:** Watch

- Without turning into a full platform, make the parser easy to embed in modern workflows.
- Potential additions:
  - container-friendly examples
  - streaming-friendly NDJSON docs/examples
  - serverless batch examples
  - webhook/event pipeline examples in docs
- Why this matters:
  - the market increasingly expects cloud-native integration patterns even for smaller components
  - good packaging/docs can capture much of this value without overbuilding the product

## 11.11 Preflight / rejection-risk summary mode
**Status:** Now

- Add a dedicated summary mode aimed at the gap between a raw parser and a clearinghouse.
- Potential additions:
  - top rejection-risk drivers for an 837 file
  - configurable fail thresholds by severity or issue-code family
  - compact provider-ops summary for “send / hold / review” decisions
  - exportable QA/preflight checklist
- Why this matters:
  - clearinghouses sell this operational value, but usually as part of a larger opaque workflow
  - a transparent local preflight layer could be one of the repo’s strongest real-world use cases

## 11.12 Open-source benchmark / comparison harness
**Status:** Soon

- Build a reproducible comparison harness against representative open-source parsers where feasible.
- Potential additions:
  - same-sample parse/validation comparison runs
  - issue-count / issue-taxonomy diff reports
  - export-shape comparison notes
  - performance notes on small vs large files
- Why this matters:
  - helps validate differentiation claims against LinuxForHealth/x12, imsweb/x12-parser, Databricks x12-edi-parser, and pyx12-style baselines
  - keeps market positioning honest and gives future README/benchmark material

## 11.13 Better product framing around local-first trust
**Status:** Soon

- Shape docs and examples around a clear promise: trustworthy local parsing, validation, and export without sending PHI to a black-box service.
- Potential additions:
  - explicit local/offline workflow examples
  - compliance-conscious docs language around data handling boundaries
  - examples for de-identified fixture work vs production data handling
- Why this matters:
  - enterprise vendors increasingly push platform/network lock-in
  - a credible local-first, developer-friendly posture is a real strategic differentiator if documented clearly

## 11.14 Stable machine-readable output contracts
**Status:** Now

- Competitor signal:
  - Stedi wins trust partly through strong API contracts and integration ergonomics
  - Databricks wins with explicit claim-level data engineering output patterns
- Priorities:
  - publish stable JSON schema/versioning rules
  - emit parser run metadata (parser version, validation policy, rule packs, feature flags)
  - define backward-compatibility expectations for CSV / NDJSON / SQLite exports
  - add contract tests for emitted artifacts
- Why this matters:
  - strong contracts make the parser safer to embed in apps, ETL, CI, and agent workflows
  - this helps us compete without becoming a hosted platform

## 11.15 Real-time workflow adjacency without platform bloat
**Status:** Soon

- Market trend:
  - modern healthcare transaction vendors emphasize 270/271, 276/277, 275, acknowledgments, and preflight workflows—not just batch 835/837 parsing
- Potential additions:
  - acknowledgment-aware docs/examples (999 / 277CA / claim status linkages)
  - transaction-lifecycle summary views that connect 837 submission risk to later responses/remits
  - helper exports oriented around “what happens next” in the workflow
- Why this matters:
  - broadens relevance to real revenue-cycle workflows without turning the repo into a clearinghouse
  - strengthens the “beside the clearinghouse” positioning

## 11.16 Pricing-aware commercialization options
**Status:** Watch

- Competitive signal:
  - Stedi proves transparent developer pricing can work
  - EDIdEv/FREDI proves perpetual/toolkit licensing still sells
  - most enterprise vendors remain opaque and sales-led
- Potential additions:
  - keep feature packaging in mind while designing advanced capabilities
  - separate likely open-core features from candidate paid surfaces (rule packs, advanced reconciliation, hosted batch validation, premium support)
  - avoid coupling the core parser too tightly to any future monetization path
- Why this matters:
  - preserves optionality between OSS-first, subscription, and embedded licensing models
  - helps ensure our strongest differentiators can support an actual product later if desired

## 11.17 AI-safe structured anomaly output
**Status:** Soon

- Market trend:
  - newer vendors increasingly market AI-ready workflows, but trustworthy structure is still the hard part
- Potential additions:
  - compact anomaly/event records with exact coordinates and issue codes
  - token-efficient claim/remit summaries for LLM consumption
  - direct vs inferred vs heuristic field labeling
  - explicit evidence snippets for every high-severity issue
- Why this matters:
  - lets AI consume the parser safely without replacing deterministic parsing
  - builds on our explainability strengths instead of competing in fuzzy “AI parsing” territory

## 11.18 Forensic-grade malformed file recovery guidance
**Status:** Now

- Competitive gap:
  - clearinghouses and SDKs mostly assume clean partner feeds; public-sample and partial-file debugging are still badly served
- Potential additions:
  - best-effort envelope recovery hints
  - malformed delimiter diagnosis with likely-fix suggestions
  - partial-file provenance and truncation markers
  - “unsafe to trust totals” / “structure partially reconstructed” style warnings
- Why this matters:
  - this is one of the clearest differentiation lanes not already owned by bigger vendors
  - makes the parser genuinely useful in debugging and research situations people hit constantly

## 11.19 Public benchmark and evidence-based positioning pack
**Status:** Soon

- Competitive need:
  - direct comparators such as LinuxForHealth/x12, Databricks EDI Ember, imsweb/x12-parser, EdiFabric, and Stedi create pressure to make claims precise
- Potential additions:
  - reproducible comparison corpus
  - explainability metrics, not just pass/fail counts
  - sample outputs showing why this parser is easier to trust/debug
  - repo docs with clearly sourced competitive positioning language
- Why this matters:
  - keeps differentiation honest
  - turns research into reusable marketing and product evidence rather than one-off notes
