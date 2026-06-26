# Document Structure: Agentic Repository Execution Standard

## 1. Purpose

Document structure is part of the execution harness for an
agent-governed repository. It is not cosmetic organization.

Codex uses files and directories as context boundaries. If standards,
reports, templates, skills, and publication drafts are mixed together, Codex
has to load more context than the task requires and is more likely to treat
evidence, reusable rules, and public narrative as interchangeable.

A clear structure should help Codex:

- load only the context relevant to the current task;
- distinguish reusable execution standards from repository-specific evidence;
- avoid mixing engineering evidence with Medium or GitHub narrative;
- keep Phase 0 boundary documents separate from later executable standards;
- preserve stable paths that future automation can target;
- make the standard easier to copy into future repositories without copying
  `upload-control-plane` facts.

The main product remains the reusable Agentic Repository Execution Standard.
The document structure exists to protect that product from context pollution.

## 2. Structure Principles

Document placement must follow these principles:

1. Separate reusable standards from repository-specific evidence.
2. Separate Phase 0 boundary documents from later executable standards.
3. Separate engineering evidence from Medium and GitHub narrative.
4. Keep templates repository-agnostic.
5. Keep `upload-control-plane`-specific invariants out of reusable standard
   documents unless they are generalized.
6. Prefer stable, predictable paths over ad-hoc documents.
7. Give each document one primary purpose.
8. Make it possible for Codex to infer what to read based on task type.
9. Support future automation with predictable directories, names, and document
   roles.

These principles are stricter than ordinary documentation hygiene because the
reader is often an executing agent. Placement errors can become execution
errors.

## 3. Proposed Top-Level Documentation Layout

The following is a proposed future layout under `docs/`. This task does not
create these directories or files. It only defines where future artifacts should
live when later phases create them.

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
    execution-standard.md

  reports/
    baseline/
      unconstrained-codex-baseline.md
      repository-hotspots.md
      architecture-drift.md
      baseline-metrics.json

    current-repo/
      repository-intake.md
      architecture-map.md
      rule-candidates.md
      refactor-task-graph.md

    refactor/
      upload-sessions-before-after.md
      evidence-reports/

    metrics/
      before-after-summary.md
      before-after.json

  templates/
    repository-intake-report.md
    evidence-report.md
    before-after-report.md
    task-graph.md
    rule-classification.md

  skills/
    repository-intake.md
    architecture-audit.md
    evidence-review.md
    api-contract-review.md
    test-gap-analysis.md

  articles/
    medium-outline.md
    medium-draft.md
    github-case-study.md
    figures/
```

The current repository already has documentation under `docs/`, including
Phase 0 boundary documents, PRD documents, task documents, and project
documentation. This proposed layout does not require moving existing files.
Future phases should add only the files needed for their phase.

## 4. Directory Responsibilities

| Directory | Purpose | Reusable or repository-specific? | Who/what reads it? | What must not be placed there |
| --- | --- | --- | --- | --- |
| `docs/agentic-engineering/` | Boundary documents and later reusable execution standards for agentic repository work. | Reusable, except Phase 0 documents may refer to this repository as the demonstration case. | Codex during governance tasks, humans defining the standard, future repositories adopting the standard. | Baseline findings, current repository audits, metrics outputs, refactor evidence logs, Medium drafts, repository-specific invariants that have not been generalized. |
| `docs/reports/baseline/` | Frozen evidence about the unconstrained Codex baseline. | Repository-specific. | Codex and humans comparing baseline to governed execution. | Reusable rules, templates, future target structure, article narrative, uncollected metrics. |
| `docs/reports/current-repo/` | Current repository intake, architecture map, rule candidates, and task graph evidence. | Repository-specific. | Codex before planning governed work, humans reviewing repository-specific findings. | Generic standards, publication drafts, reusable templates, claims about other repositories. |
| `docs/reports/refactor/` | Evidence from governed refactor slices and before/after observations. | Repository-specific. | Codex validating changes, humans reviewing whether the standard changed execution behavior. | Reusable policy text, generic template skeletons, Medium story drafts, undocumented future plans. |
| `docs/reports/metrics/` | Machine-readable and human-readable metric outputs for comparisons. | Repository-specific, with reusable metric definitions referenced elsewhere. | Codex, humans, and later publication documents that cite collected evidence. | Metrics not collected, generic standards, narrative claims without collection method, templates. |
| `docs/templates/` | Repository-agnostic skeletons for reports, task graphs, prompts, and rule classification. | Reusable. | Codex when starting a new report or future repository adoption. | Actual `upload-control-plane` findings, filled-in reports, metrics outputs, article prose. |
| `docs/skills/` | Task-specific instruction documents for repeatable Codex workflows. | Reusable or mostly reusable, with local adapters only when clearly marked. | Codex when a task matches a skill-like workflow. | Full execution standard duplication, repository audit findings, article drafts, broad advice unrelated to the task. |
| `docs/articles/` | Downstream public narrative and portfolio material. | Publication-specific and evidence-derived. | Humans writing public materials, Codex drafting from reports. | Source engineering evidence, reusable standards, templates, unverified claims, baseline reports as primary records. |

## 5. Phase 0 Documents

Phase 0 documents define project boundaries. They are active boundary documents,
not executable standards yet.

Phase 0 includes:

- `project-charter.md`
- `deliverables.md`
- `human-role-and-autonomy.md`
- `experiment-design.md`
- `document-structure.md`

These documents define:

- the project goal;
- deliverable categories;
- human and agent autonomy boundaries;
- the experiment design;
- the document structure for later work.

They should not contain:

- detailed refactor plans;
- repository audit findings;
- baseline metrics;
- Medium narrative;
- executable task procedures that belong in later standards;
- source code restructuring instructions.

Phase 0 documents guide later documents. They should be stable enough for later
phases to cite, but they should not pretend that later standards already exist.

## 6. Later Standard Documents

Later reusable standard documents turn Phase 0 principles into executable
governance.

Examples include:

- `repository-intake-standard.md`
- `rule-classification-standard.md`
- `autonomy-policy.md`
- `evidence-gate-standard.md`
- `architecture-boundary-standard.md`
- `code-organization-standard.md`
- `testing-and-verification-standard.md`
- `execution-standard.md`

These documents will be created after Phase 0. They should be reusable across
repositories and written as agent-executable governance, not generic advice.

They should define:

- required inputs;
- decision rules;
- allowed and denied actions;
- evidence gates;
- escalation triggers;
- expected output shapes;
- verification requirements.

They should avoid `upload-control-plane`-specific details unless those details
are clearly marked as examples of a generalized rule. The eventual `AGENTS.md`
should draw from these standards, but should not duplicate them in full.

## 7. Report Documents

Report documents are repository-specific evidence. They describe what was
observed, changed, measured, or verified in this repository.

Examples include:

- baseline reports;
- hotspot reports;
- architecture drift reports;
- repository intake reports;
- refactor evidence reports;
- before/after metrics reports.

Reports may include `upload-control-plane`-specific findings, file paths,
domain terms, command outputs, test results, limitations, and risks.

Reports are evidence, not reusable rules. A future repository may copy the
report format, but it should not copy the findings. If a report reveals a rule
that seems reusable, that rule should be extracted into a standard or template
with repository-specific details removed or clearly marked as examples.

## 8. Template Documents

Templates are repository-agnostic skeletons that can be copied into another
repository.

Examples include:

- repository intake report template;
- evidence report template;
- before/after report template;
- task graph template;
- rule classification template.

Templates define structure, required sections, and placeholders. They do not
contain current findings.

Templates should use placeholders where repository-specific content belongs,
such as:

- repository name;
- git ref;
- command output;
- affected files;
- observed risks;
- verification results;
- limitations.

Templates must not include actual `upload-control-plane` findings, metrics, or
domain invariants.

## 9. Skill Documents

Skill-like documents guide Codex behavior for repeatable work. They should be
concise, task-specific, and loaded only when relevant.

Examples include:

- repository intake;
- architecture audit;
- evidence review;
- API contract review;
- test gap analysis.

Skills should tell Codex:

- when to use the skill;
- what to read;
- what to inspect;
- what evidence to produce;
- when to stop;
- when to escalate.

Skills should not duplicate the full execution standard. They should reference
the relevant standard when needed and provide a narrow workflow for a specific
task type. This prevents context pollution by keeping Codex from loading every
governance document for a small task.

## 10. Article and Portfolio Documents

Publication documents are downstream of engineering evidence.

Examples include:

- Medium outline;
- Medium draft;
- GitHub case study;
- diagrams, screenshots, or figures.

Publication materials should cite or reference reports, metrics, diffs, and
verification evidence. They may simplify the story for readers, but they must
not replace engineering evidence or make claims that the reports cannot
support.

Article documents belong under `docs/articles/` because their purpose is
communication, not repository governance. Codex should not read article drafts
as execution rules unless a task explicitly concerns publication.

## 11. Placement Rules

Use these decision rules when creating a new document:

1. Is this document a reusable rule or standard?

   Put it under `docs/agentic-engineering/`.

2. Is this document evidence about the current repository?

   Put it under `docs/reports/`.

3. Is this document a reusable skeleton?

   Put it under `docs/templates/`.

4. Is this document a task-specific instruction for Codex?

   Put it under `docs/skills/`.

5. Is this document for Medium or GitHub presentation?

   Put it under `docs/articles/`.

6. Does the document mix two purposes?

   Split it.

7. Does the document contain both a reusable rule and local evidence?

   Put the rule in a standard and the evidence in a report, then cross-reference
   them.

8. Does the document contain future target structure and current findings?

   Put the target structure in a standard or boundary document and the current
   findings in a report.

## 12. Naming Conventions

Use stable, descriptive names:

- Use lowercase kebab-case for Markdown files.
- Use clear nouns over vague names.
- Avoid names such as `notes.md`, `misc.md`, `final.md`, `draft2.md`, and
  `latest.md`.
- Use `*-standard.md` for reusable standards.
- Use `*-report.md` for evidence reports when the document is primarily a
  report.
- Use `*-template.md` for templates when the filename would otherwise be
  ambiguous.
- Use JSON only for machine-readable metrics, task graphs, or other structured
  artifacts.
- Prefer names that reveal task type to Codex before the file is opened.

Examples:

- `repository-intake-standard.md`
- `architecture-drift-report.md`
- `evidence-report-template.md`
- `before-after.json`

## 13. Document Lifecycle

Documents should have an explicit lifecycle state when the status is not
obvious from the phase.

Suggested states:

- `proposed`: drafted for review or future use, not yet authoritative;
- `active`: current source for its document purpose;
- `superseded`: replaced by a newer document, retained for history;
- `archived`: no longer part of the active workflow, retained only as record.

Phase 0 documents are active boundary documents. Later standards may supersede
earlier principles with more executable detail. When that happens, the older
document should be marked as superseded instead of silently deleted.

Reports should remain historically stable. If later evidence changes an
interpretation, add a new report or an explicit update note rather than
rewriting the old evidence into a different record.

## 14. What Must Not Be Mixed

Do not mix:

- reusable standards with `upload-control-plane`-specific facts;
- reports with templates;
- Medium narrative with engineering evidence;
- Phase 0 boundaries with later implementation instructions;
- current findings with future target structure;
- human preference rules with executable agent constraints;
- source code restructuring plans with document-structure rules;
- collected metrics with proposed metrics;
- task handoffs with public case-study prose;
- examples with authoritative rules unless the difference is explicit.

When in doubt, split the document and add cross-references.

## 15. Relationship to AGENTS.md

`AGENTS.md` will be created later. It is outside Phase 0.

Its future role should be the Codex entrypoint for repository execution. It
should:

- point to relevant standards and skills;
- tell Codex what to read based on task type;
- summarize the active autonomy and evidence expectations;
- identify repository-specific commands and constraints;
- avoid duplicating every full standard document;
- use this document structure to avoid loading unnecessary context.

`AGENTS.md` should be concise enough to load frequently. Full rationale,
examples, and detailed procedures should remain in the standards, reports,
templates, and skills directories.

## 16. Migration to Future Repositories

This structure should make future repository adoption easier.

For a new repository:

- copy reusable standards from `docs/agentic-engineering/`;
- copy reusable templates from `docs/templates/`;
- copy skill-like documents from `docs/skills/` when the workflows apply;
- create new repository-specific reports under that repository's
  `docs/reports/`;
- replace `upload-control-plane` examples with the new repository's
  invariants;
- keep the same separation between standards, reports, templates, skills, and
  publication materials.

The goal is not to copy the demonstration repository. The goal is to copy the
execution standard and regenerate repository-specific evidence.

## 17. Phase 0 Completion Boundary

After this document, Phase 0 boundary definition is complete.

Phase 0 has defined:

- project charter;
- deliverable boundaries;
- human and agent autonomy boundaries;
- experiment design;
- document structure.

After Phase 0, later phases may begin:

- baseline freezing;
- baseline reporting;
- reusable standard creation;
- governed repository intake;
- governed refactoring;
- evidence reporting.

Those later phases should use this structure, but they should create their
documents only when the corresponding phase begins.
