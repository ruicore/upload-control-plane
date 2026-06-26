# Deliverables Boundary: Agentic Repository Execution Standard

## Purpose

This document defines the final deliverable boundaries for the repository
evolution project.

The main product is a reusable Agentic Repository Execution Standard. The
`upload-control-plane` repository is the demonstration case used to validate
that standard against a real codebase. Repository cleanup matters only when it
produces evidence that the standard improves agentic execution.

## Deliverable Boundary Principles

- The reusable standard must not depend on `upload-control-plane` business
  logic, multipart-upload terminology, FastAPI-specific implementation details,
  PostgreSQL schema names, MinIO behavior, or this repository's current file
  layout.
- The demonstration repository must prove that the standard works in a real
  codebase with real feature breadth, implementation history, tests, handoffs,
  and architectural tradeoffs.
- Publication assets should explain the experiment and make the evidence
  understandable. They must not replace engineering evidence or become the
  source of truth for claims.
- Repository cleanup is secondary to standard extraction. A cleaner repository
  is useful only if it shows which constraints, evidence gates, and autonomy
  rules made the improvement repeatable.
- Any rule that is specific to multipart upload, presigned URLs, MinIO, upload
  sessions, upload tasks, object keys, device flows, or dataset lifecycle must
  stay in the demonstration layer unless it is generalized.
- Any rule about agent execution, evidence, autonomy, repository intake,
  architecture governance, task decomposition, verification, or escalation
  should be considered for the reusable standard layer.

## What Must Not Be Mixed

- Do not mix reusable standards with `upload-control-plane`-specific invariants.
  For example, "file bytes must not pass through the backend" is a demo
  invariant unless generalized into an architecture-boundary pattern.
- Do not mix baseline reports with future standard templates. A baseline report
  describes what happened in this repository; a template defines how to inspect
  another repository.
- Do not mix Medium article narrative with engineering evidence. The article may
  cite reports, metrics, screenshots, and diffs, but it must not invent claims
  that the evidence does not support.
- Do not mix refactor task details with Phase 0 boundary documents. Phase 0
  defines what later work should produce; it does not prescribe individual code
  edits.
- Do not mix human preferences with executable agent constraints. Preferences
  may inform standards, but the final standard should state rules Codex can
  apply, verify, or escalate.

## 1. Reusable Standard Deliverables

Reusable standard deliverables are generic artifacts intended to be reused in
future repositories. They should describe agent-executable constraints and
evidence requirements without copying this repository's business logic.

| Deliverable | Purpose | Why it is reusable | Repository-agnostic content | Repository-specific customization | Expected location | Completion criteria |
| --- | --- | --- | --- | --- | --- | --- |
| `AGENTS.md` template | Define how Codex should inspect, change, test, and report work in a repository. | Most repositories need durable agent instructions at the repo root. | Role boundaries, allowed autonomy, evidence gates, escalation rules, task execution protocol, testing expectations. | Project commands, owned domains, forbidden operations, service names, deployment constraints. | Later template under `docs/templates/AGENTS.md`; later repository instance at `AGENTS.md`. | A new repository can fill in project-specific sections without inheriting upload-control-plane terminology. |
| Repository intake standard | Define the first-pass inspection Codex must perform before planning or changing a repo. | Any repo needs a consistent way to identify languages, commands, architecture, risks, and docs. | Intake checklist, required evidence, questions to answer, output shape. | Actual stack, commands, CI files, runtime topology, domain docs, ownership boundaries. | `docs/agentic-engineering/repository-intake-standard.md`. | Produces an intake report that is specific enough to guide work but does not perform a deep audit. |
| Rule classification standard | Classify rules by source, enforceability, risk, and generality. | Agents need to separate hard constraints from preferences in every repo. | Rule classes such as invariant, policy, convention, preference, temporary workaround, and evidence requirement. | Local examples, domain invariants, team preferences, repo-specific exceptions. | `docs/agentic-engineering/rule-classification-standard.md`. | Codex can decide whether to obey, generalize, question, or escalate a rule. |
| Autonomy policy | Define when Codex can proceed independently and when it must escalate. | Safe autonomy is needed across repositories, independent of tech stack. | Risk levels, reversible vs irreversible actions, external side effects, approval triggers, evidence-before-action requirements. | Local deploy targets, credentials handling, migration risk, production access, branch policy. | `docs/agentic-engineering/autonomy-policy.md`. | Routine local changes can proceed without human synchronous review, while high-risk actions are clearly blocked or escalated. |
| Evidence gate standard | Define the evidence required before claims, refactors, and completion reports are accepted. | Every repo needs evidence standards for agent output to be trusted. | Reproduction evidence, command output expectations, test evidence, diff evidence, source citations, uncertainty reporting. | Project-specific test commands, benchmark commands, deployment checks, runtime smoke tests. | `docs/agentic-engineering/evidence-gate-standard.md`. | A future agent can prove what changed and avoid subjective completion claims. |
| Architecture boundary standard | Define how to identify, preserve, and enforce architecture boundaries. | Architecture drift is common across agentic work and is not repo-specific. | Boundary discovery method, ownership rules, dependency-direction checks, allowed integration patterns, escalation triggers. | Specific domains, modules, service names, API contracts, storage boundaries. | `docs/agentic-engineering/architecture-boundary-standard.md`. | Codex can identify when a proposed change crosses a boundary and either justify, test, or escalate it. |
| Code organization standard | Define how agents should create, split, move, and name code. | Code organization decisions recur in every implementation project. | Rules for module size, coupling, public/private APIs, shared utilities, generated code, scripts, tests, and docs. | Framework-specific package layout, naming conventions, local migration style, CLI structure. | `docs/agentic-engineering/code-organization-standard.md`. | The standard explains when reorganization is justified and what evidence is needed before moving code. |
| Testing and verification standard | Define expected verification levels by change type. | Test scope and verification evidence need consistent treatment across repos. | Verification matrix for docs, small code changes, shared logic, migrations, API changes, refactors, and external integrations. | Actual command set, service startup path, fixtures, coverage expectations, CI names. | `docs/agentic-engineering/testing-and-verification-standard.md`. | Codex can choose a proportionate verification set and explain unrun checks. |
| Report templates | Provide reusable shapes for baseline, evidence, before/after, and refactor reports. | Future repos need consistent reports without copying this repo's findings. | Section structure, required evidence, risks, command log fields, metric placeholders, decision records. | Local metrics, file paths, command outputs, screenshots, domain-specific findings. | `docs/templates/`. | Templates contain placeholders and instructions, not upload-control-plane conclusions. |
| Reusable Codex task prompts | Provide prompts for intake, baseline capture, governed refactor, validation, and report generation. | Prompt quality directly affects repeatable agent execution. | Prompt roles, scope constraints, evidence requirements, escalation rules, output contracts. | Repo name, task IDs, local commands, branch names, domain constraints. | `docs/templates/codex-prompts/` or equivalent later location. | Prompts can be copied into another repository with bounded project-specific substitutions. |
| Reusable skills or skill-like instructions | Package recurring agent workflows as durable instructions. | Skills make complex workflows repeatable across repositories. | Intake workflow, evidence package workflow, architecture-boundary review, refactor validation, publication evidence selection. | Local command adapters, repo-specific examples, private tool availability. | `docs/agentic-engineering/skills/` or external Codex skill folder after validation. | At least one validation pass proves the instruction works outside a single hand-written prompt. |
| Reusable scripts for metrics or boundary checks, if added later | Automate structural metrics, dependency checks, or documentation completeness checks. | Scripts reduce subjective review and can be adapted to other repos. | Script intent, input/output contracts, language-agnostic metric definitions where possible. | Parser adapters, source roots, ignore rules, framework-specific dependency extraction. | `scripts/agentic-engineering/` or `docs/tools/` if documentation-only. | Scripts are documented, deterministic, non-destructive by default, and separated from repository-specific findings. |

## 2. Demonstration Repository Deliverables

Demonstration deliverables are specific to this `upload-control-plane`
repository. They capture the baseline, governed changes, and evidence needed to
validate the reusable standard.

| Deliverable | Purpose | Why it is specific to this repository | Evidence it should provide | Expected location | Completion criteria |
| --- | --- | --- | --- | --- | --- |
| Unconstrained Codex baseline tag or branch | Freeze the current implementation state before governed refactoring begins. | The baseline represents this repository's unconstrained Codex history. | Git ref, date, commit, short description of included state, known untracked exclusions if any. | Git tag or branch; reference noted under `docs/reports/baseline/`. | A reviewer can check out the baseline state and compare it to later governed work. |
| Baseline report | Describe current structure, agent behavior traces, risks, strengths, and governance gaps before refactoring. | Findings depend on this repository's code, docs, task packs, tests, and handoffs. | File/module observations, command evidence, examples of drift or good behavior, explicit non-audit limitations. | `docs/reports/baseline/`. | Report identifies actionable governance lessons without becoming a refactor plan. |
| Hotspot file report | Identify files or areas where size, churn, coupling, or responsibility concentration suggests agent difficulty. | Hotspots are determined from this repo's files, history, and implementation shape. | Collected metrics, file paths, rationale, caveats, and follow-up questions. | `docs/reports/current-repo/` or `docs/reports/metrics/`. | Hotspots are evidence-backed and avoid uncollected metric claims. |
| Architecture drift report | Compare intended architecture against current implementation boundaries. | Drift depends on this repo's PRD, README, source tree, tests, and runtime design. | PRD citations, implementation evidence, drift examples, risk level, standard lessons. | `docs/reports/current-repo/`. | Each finding distinguishes upload-specific invariants from reusable governance rules. |
| Governed branch or implementation path | Provide the path where Codex applies the emerging standard to repository changes. | The path operates on this repository's actual code and docs. | Branch name or execution path, applied standard version, task list, constraints, validation commands. | Git branch plus `docs/tasks/` or `docs/reports/refactor/` references. | Work is traceable from standard rule to task to evidence to diff. |
| Before/after comparison report | Show how governed execution changed repository structure, evidence quality, or agent behavior. | The comparison is anchored in this repo's baseline and governed branch. | Baseline ref, governed ref, collected metrics, qualitative evidence, examples, limitations. | `docs/reports/refactor/before-after-report.md`. | Claims are supported by collected evidence rather than taste-based comparison. |
| Refactor evidence reports | Record each governed refactor slice and its verification results. | Each report corresponds to concrete changes in this repository. | Scope, files changed, standard rules applied, tests run, commands skipped with reason, risks. | `docs/reports/refactor/` or task-specific handoff files. | A reviewer can understand why each refactor happened and how it was verified. |
| Final cleaned demonstration structure | Present the final repository shape after governed work. | The final structure reflects this repository's domain and implementation. | Directory map, boundary explanation, remaining tradeoffs, links to standards that drove decisions. | README section plus `docs/reports/refactor/` or final case-study doc. | The structure is useful as a demo without pretending to be the generic standard. |
| Test and verification evidence | Prove that governed changes preserve expected behavior. | Commands, fixtures, services, and tests are repository-specific. | Test command logs, smoke checks, failure notes, local runtime checks where needed, unrun checks. | `docs/reports/refactor/verification/` or evidence report appendices. | Evidence is sufficient for the risk level of each change and clearly states gaps. |
| PRD-to-implementation alignment notes | Track how implementation aligns with the split PRD and where deviations remain. | The PRD is specific to industrial multipart upload control-plane behavior. | PRD references, implemented evidence, deviations, deferred scope, questions. | `docs/reports/current-repo/` or `docs/reports/refactor/`. | Notes separate product-specific alignment from reusable agentic-engineering lessons. |

## 3. Publication and Portfolio Deliverables

Publication deliverables are public-facing explanations for Medium, GitHub, and
portfolio review. They should cite evidence generated by the standard and
demonstration layers.

| Deliverable | Purpose | Audience | Evidence it should reference | Expected location | Completion criteria |
| --- | --- | --- | --- | --- | --- |
| Medium article outline | Define the public narrative before drafting. | Engineering readers, agentic-coding practitioners, potential collaborators. | Charter, baseline plan, report list, evidence inventory, before/after framing. | `docs/articles/medium-outline.md`. | The outline explains the experiment without making claims before evidence exists. |
| Medium article draft | Tell the story of the standard, the baseline, the governed pass, and the lessons. | Medium readers interested in agentic software engineering. | Baseline report, before/after report, metrics table, selected diagrams, concrete examples. | `docs/articles/medium-draft.md`. | Draft claims are traceable to repository evidence and avoid private or unverifiable details. |
| GitHub case study document | Provide a durable repo-native summary of the experiment and result. | GitHub visitors, portfolio reviewers, technical evaluators. | Charter, standards, baseline and governed refs, metrics, verification reports, final structure. | `docs/articles/github-case-study.md` or `docs/case-study.md`. | The document lets a reader evaluate the work without reading the Medium article. |
| Before/after metrics table | Summarize collected structural and verification metrics. | Readers who need quick evidence. | Metrics scripts or manual collection notes, baseline ref, governed ref, caveats. | `docs/reports/metrics/` and referenced by publication docs. | Table contains only collected metrics and includes collection method and limitations. |
| Diagrams or screenshots | Make the experiment and final structure easier to inspect. | Medium and GitHub readers. | Architecture boundary diagrams, before/after structure diagrams, screenshots of reports or repo state. | `docs/articles/assets/` or `docs/reports/assets/`. | Visuals clarify evidence and do not replace source reports. |
| Short LinkedIn/GitHub summary, if useful | Provide a compact public summary for social or repository presentation. | Recruiters, peers, maintainers, casual readers. | Final case study, metrics table, article, repository links. | `docs/articles/short-summary.md` or README section draft. | Summary is accurate, short, and points back to evidence. |
| Final public-facing README section | Surface the project as a case study from the repository entrypoint. | GitHub visitors and portfolio reviewers. | GitHub case study, final standard docs, before/after evidence, verification summary. | Later update to `README.md`. | README presents the project without overwhelming the product documentation or hiding evidence. |

## Expected Final Repository Documentation Shape

The final documentation structure should separate boundary documents, reusable
standards, repository-specific reports, templates, and publication materials.
This is a proposed shape only. Later tasks may adjust names after validation.

```text
docs/
  agentic-engineering/
    project-charter.md
    deliverables.md
    human-role-and-autonomy.md
    experiment-design.md
    document-structure.md
    repository-intake-standard.md
    rule-classification-standard.md
    autonomy-policy.md
    evidence-gate-standard.md
    architecture-boundary-standard.md
    code-organization-standard.md
    testing-and-verification-standard.md

  reports/
    baseline/
    current-repo/
    refactor/
    metrics/

  templates/
    repository-intake-report.md
    evidence-report.md
    before-after-report.md
    codex-prompts/

  articles/
    medium-outline.md
    medium-draft.md
    github-case-study.md
    assets/
```

Do not treat this proposed shape as permission to create all files at once.
Each file should be created only when the corresponding task reaches that phase.

## Deliverable Dependency Order

1. Phase 0 boundary documents come first.
   - Project charter.
   - Deliverables boundary.
   - Human/agent role and autonomy boundary.
   - Experiment design.
   - Document structure.
2. Baseline evidence comes before refactoring.
   - Freeze the unconstrained baseline.
   - Capture current structure, reports, and evidence.
   - Record known limitations before applying standards.
3. Reusable standards come before governed refactoring.
   - Define intake, rule classification, autonomy, evidence gates,
     architecture boundaries, code organization, and verification standards.
   - Create only enough templates to run the first validation pass.
4. Governed refactoring produces evidence.
   - Apply the standard to bounded repository changes.
   - Record refactor evidence, verification commands, skipped checks, and
     unresolved risks.
5. Evidence feeds publication materials.
   - Write Medium and GitHub materials from reports, metrics, diffs, and
     screenshots.
   - Keep article claims traceable to repository evidence.
6. Templates are extracted after at least one validation pass.
   - Convert repeated report shapes, prompts, and checks into reusable templates.
   - Remove upload-control-plane-specific content from reusable artifacts.

## Success Criteria

The deliverables set is complete when:

- A future repository can reuse the standard without copying
  `upload-control-plane` business logic, file paths, product vocabulary, or
  multipart-upload invariants.
- The current repository can demonstrate before/after Codex behavior change
  through a frozen baseline, governed execution path, reports, diffs, and
  verification evidence.
- Medium and GitHub materials can cite real evidence rather than subjective
  claims about cleanliness or quality.
- Human synchronous review is reduced by clear autonomy rules, evidence gates,
  escalation boundaries, and agent-executable constraints.
- The project does not collapse into a one-off manual refactor. Each meaningful
  repository improvement should either validate an existing standard rule or
  produce a candidate rule for the reusable standard layer.
