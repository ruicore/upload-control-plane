# Experiment Design: Unconstrained Codex vs Governed Codex

## 1. Purpose

This document defines the comparison model for the `upload-control-plane`
repository evolution project.

The experiment compares two execution modes:

- the current unconstrained Codex baseline;
- later governed Codex execution under an Agentic Repository Execution
  Standard.

The goal is to measure agent behavior change, not merely final code quality.
The comparison should show whether Codex changes how it plans, edits, verifies,
documents, and escalates when durable repository governance is available.

This experiment is not answered by asking only whether the repository was
refactored, whether the final structure looks cleaner, or whether a human
reviewer prefers the result. Those outcomes may matter, but the central
question is whether the same AI coding agent moves from local task completion
toward structured, evidence-backed, safer, and more reusable execution.

## 2. Core Hypothesis

When Codex works without explicit repository governance, it tends to:

- extend existing files instead of creating new structure;
- concentrate multiple responsibilities in large files;
- optimize for immediate task completion;
- rely on existing local context and session history;
- under-produce durable architecture evidence;
- treat documentation and standards as reference material rather than
  executable constraints.

When Codex works under a reusable execution standard, it should:

- create appropriate module boundaries;
- produce task graphs before multi-step work;
- preserve public contracts unless a change is explicitly gated;
- generate evidence reports before claiming completion;
- classify risky work before acting;
- reduce synchronous human review;
- improve repository maintainability without manual step-by-step steering.

The hypothesis is behavioral: governed Codex should make different decisions
under the same repository pressure. Cleaner files, better tests, and clearer
docs are expected effects, but they are not sufficient proof unless the work
also shows changed execution behavior.

## 3. Experimental Units

### Baseline Version

The baseline version is the existing repository state before governance is
added.

Purpose:

- capture unconstrained Codex behavior;
- preserve evidence of natural agent coding tendencies;
- provide before/after comparison material.

Expected artifact:

- baseline tag or branch, for example `codex-unconstrained-baseline`;
- baseline report under `docs/reports/baseline/`.

The baseline should preserve the repository as a functional demonstration
case: a FastAPI upload control plane with PostgreSQL persistence, MinIO-backed
multipart upload behavior, CLI and browser upload tools, migrations, tests,
observability work, and project documentation. It should not be presented as a
failed repository.

### Governed Version

The governed version is the later repository state after execution standards
are added and used.

Purpose:

- show how Codex behaves when standards, autonomy boundaries, evidence gates,
  and task graphs are available;
- validate the reusable standard against a real repository;
- compare agent execution behavior before and after governance.

Expected artifact:

- governed branch or implementation path;
- governed refactor reports;
- before/after comparison report.

The governed version succeeds only if the execution path is traceable from
standard to task graph to code or documentation changes to verification
evidence.

### Reusable Standard

The standard itself is also an experimental artifact.

Purpose:

- test whether the approach can be reused beyond this repository;
- distinguish reusable agent governance from
  `upload-control-plane`-specific cleanup;
- provide executable constraints for future Codex work.

Expected artifact:

- `AGENTS.md` template, later;
- repository intake standard;
- autonomy policy;
- evidence gate standard;
- architecture boundary standard;
- report templates.

Rules about agent execution, evidence, autonomy, repository intake,
architecture governance, task decomposition, verification, and escalation
belong in the reusable standard layer. Rules about multipart uploads,
presigned URLs, MinIO, upload sessions, devices, datasets, and local service
ports belong in the demonstration layer unless they are generalized into a
repository-independent pattern.

## 4. What Counts as Evidence

Evidence must be inspectable after the session. A claim should point to a
report, diff, metric definition, test result, task graph, or documented
decision rather than relying on memory or taste.

### Structural Evidence

Structural evidence describes how the repository is organized.

Examples:

- maximum file LOC;
- median file LOC;
- number of large hotspot files;
- directory depth;
- number of modules or packages;
- number of files with mixed responsibilities;
- API, schema, mapper, permission, and application-service separation;
- application, domain, and infrastructure boundary clarity.

Structural evidence should identify concentration risk and boundary drift, but
it should not assume that every large file is wrong or every split is good.

### Behavioral Evidence

Behavioral evidence describes how Codex worked.

Examples:

- whether Codex creates new directories when appropriate;
- whether Codex produces task graphs before multi-step work;
- whether Codex asks humans only for escalation-worthy decisions;
- whether Codex produces evidence before claiming completion;
- whether Codex avoids expanding existing hotspot files without an extraction
  plan;
- whether Codex distinguishes reusable rules from repository-specific rules.

Behavioral evidence is the primary evidence class for this experiment.

### Verification Evidence

Verification evidence describes how claims about correctness and compatibility
were checked.

Examples:

- tests run;
- test categories affected;
- contract compatibility checks;
- import boundary checks;
- failure-mode tests;
- lint and type-check results;
- security and redaction checks, where applicable.

Verification evidence should record both executed checks and checks that were
skipped, with reasons.

### Governance Evidence

Governance evidence describes how the standard affected decisions.

Examples:

- Auto Allow decisions;
- Auto Deny decisions;
- Evidence Gate decisions;
- Human Escalation cases;
- rule violations found;
- rules added or clarified after execution.

Governance evidence should make clear whether Codex followed written
constraints or merely made plausible choices after the fact.

### Documentation Evidence

Documentation evidence records the durable artifacts generated by the
experiment.

Examples:

- baseline report;
- hotspot report;
- architecture drift report;
- before/after report;
- evidence reports;
- task graph;
- reusable standard documents.

Documentation evidence should separate observations, rules, templates, and
publication narrative.

### Publication Evidence

Publication evidence provides material for Medium and GitHub without becoming
the source of truth.

Examples:

- metrics table for Medium or GitHub;
- diagrams;
- case study notes;
- concrete examples of behavior change.

Publication claims must be grounded in engineering evidence produced by the
baseline and governed phases.

## 5. Metrics to Collect Later

The following metrics should be collected in later phases. This document does
not collect them, assign values, or define final tooling. Exact metric
collection tools will be created or selected later.

| Metric | Purpose | Baseline Source | Governed Source |
| --- | --- | --- | --- |
| Max Python file LOC | Detect hotspot files | baseline metrics | governed metrics |
| Median Python file LOC | Detect distribution shift | baseline metrics | governed metrics |
| Number of files over threshold | Detect concentration risk | baseline metrics | governed metrics |
| Directory depth | Detect structural flattening or modularization | tree snapshot | tree snapshot |
| Responsibility-mixed files | Detect boundary problems | audit report | audit report |
| API contract changes | Detect accidental public behavior drift | contract report | contract report |
| Test count by category | Detect verification growth | test inventory | test inventory |
| Architecture boundary violations | Detect dependency drift | boundary check | boundary check |
| Human synchronous interventions | Detect human bottleneck | execution log | execution log |
| Evidence reports generated | Detect governed execution | N/A or baseline | governed reports |
| Task graphs generated | Detect planning behavior | baseline execution notes | governed execution notes |
| Auto Allow / Auto Deny / Evidence Gate cases | Detect autonomy model usage | N/A or baseline | governed execution notes |

Metric definitions should include collection command, input scope, excluded
paths, timestamp, git ref, and limitations. Metrics should be compared with
qualitative evidence and should not be treated as the only quality signal.

## 6. Qualitative Observations to Track

Some evidence cannot be fully captured by counts. Later reports should track:

- Did Codex prefer appending to existing files?
- Did Codex create new modules proactively?
- Did Codex preserve system invariants?
- Did Codex produce reasoning artifacts before execution?
- Did Codex distinguish reusable rules from repository-specific rules?
- Did Codex reduce human review burden?
- Did Codex report uncertainty honestly?
- Did Codex avoid turning the task into a rewrite?

Each observation should include concrete examples, not only a conclusion. Good
examples include a task note, a diff, a changed file path, a refused action, an
escalation note, or a report section.

## 7. Baseline Evidence Model

The baseline report should be written later. It should capture the repository
before governed standards are added.

The baseline report should include:

- repository purpose;
- current source tree summary;
- hotspot files;
- large file examples;
- responsibility concentration examples;
- current testing safety net;
- current documentation state;
- observed unconstrained Codex behaviors;
- known limitations of the baseline observation.

The baseline should not portray the repository as a failure. It should portray
it as a functional repository that exposes natural agent coding tendencies
under weak constraints.

The baseline should also avoid turning into a deep architecture audit. Its
purpose is to preserve comparison evidence, not to design every future
refactor.

## 8. Governed Execution Evidence Model

Governed execution reports should be written during later governed work.

Each governed execution report should include:

- task graph before execution;
- autonomy classification;
- files changed;
- behavior preserved;
- tests run;
- evidence generated;
- risks remaining;
- public contract impact;
- comparison to baseline behavior.

Governed execution is successful only if Codex changes how it works, not
merely if the final diff looks cleaner. A governed refactor should show that
Codex followed boundaries, chose proportionate verification, preserved public
contracts, and generated durable evidence without requiring step-by-step human
organization decisions.

## 9. Comparison Method

The before/after comparison should follow this sequence:

1. Freeze baseline.
2. Add governance documents.
3. Run repository intake under the new standard.
4. Identify refactor targets.
5. Execute one governed refactor.
6. Generate evidence report.
7. Compare baseline vs governed results.
8. Extract reusable lessons.

The comparison should not rely only on subjective judgment. It should use
metrics, reports, diffs, test results, and documented agent behavior.

The comparison should answer these questions:

- What did Codex do differently after governance existed?
- Which decisions were guided by reusable rules?
- Which decisions remained repository-specific?
- Which risks were reduced by evidence gates or autonomy classification?
- Which claims are supported by metrics, tests, or diffs?
- Which claims remain qualitative or uncertain?

## 10. Threats to Validity

The experiment has limits:

- The governed version may improve because of human-written prompts, not only
  because of reusable standards.
- The repository is a single case study, not a statistical benchmark.
- Metrics like LOC can be gamed and should not be treated as the only quality
  signal.
- Some good architecture choices may temporarily increase file count or
  complexity.
- A cleaner structure does not automatically mean behavior is correct.
- The baseline was produced under a specific workflow and may not represent
  all Codex behavior.
- The final Medium article must not overclaim beyond the evidence.

Later reports should preserve these limitations rather than hiding them. The
project can still be useful as a case study if claims stay bounded to the
evidence.

## 11. Success Criteria

The experiment is successful if:

- baseline state is preserved;
- current unconstrained behavior is documented;
- governed execution produces measurable evidence;
- Codex creates clearer boundaries without step-by-step human steering;
- tests and contracts remain valid;
- before/after reports show behavior change;
- reusable standards can be extracted;
- publication material is grounded in evidence, not opinion.

The experiment is not successful if:

- the project becomes a one-off manual refactor;
- humans manually direct every code organization decision;
- the final article relies mainly on subjective claims;
- repository-specific upload rules are mixed into the reusable standard;
- code is made prettier but not more governable or verifiable.

The main product remains the reusable Agentic Repository Execution Standard.
Repository refactoring is evidence for that product, not the product itself.

## 12. Relationship to Later Phases

This document feeds later work:

- Phase 1 baseline report uses this evidence model.
- Rule classification defines which rules are reusable.
- Autonomy policy turns human role principles into executable decisions.
- Evidence gate standard defines required proof for risky work.
- Architecture boundary standard defines structural checks.
- Governed refactoring produces the before/after evidence.
- Medium and GitHub materials use the reports generated by this experiment.

Later phases may refine the exact metrics, thresholds, report formats, and
tooling. They should preserve the core comparison: unconstrained Codex behavior
versus governed Codex behavior under a reusable execution standard.
