# Human Role and Autonomy Boundary

## 1. Purpose

This document defines how humans and Codex divide responsibility during the
agentic repository execution project for `upload-control-plane`.

Humans define the goals, standards, and escalation boundaries. Codex performs
routine repository work autonomously inside those boundaries. Human synchronous
approval should be minimized because the purpose of this project is not to move
every agent decision back into a human review queue.

This boundary does not remove humans from the system. It moves humans out of
routine execution and into the work that actually needs human judgment: setting
direction, defining constraints, resolving ambiguity, approving irreversible
external effects, and deciding what evidence is good enough.

The repository is the demonstration case. The broader product is a reusable
Agentic Repository Execution Standard that lets Codex execute with bounded
autonomy instead of depending on continuous human supervision.

## 2. Why Traditional Ask-First Is Not Enough

A broad ask-first model is too slow for this project.

AI execution speed is much higher than human response speed. If Codex asks
before every structural decision, file organization choice, test run, or
documentation update, the workflow collapses into human-driven code review. That
would measure the human's ability to supervise Codex, not Codex's ability to
operate under reusable execution governance.

The project goal is reusable execution governance, not manual supervision.
Human approval should be reserved for ambiguity, irreversible risk, and
product-level tradeoffs. Routine engineering should be governed by written
rules, phase boundaries, tests, and evidence gates.

The question is not "did a human approve every important-looking action?" The
question is "did Codex have enough durable guidance to decide whether to act,
refuse, collect evidence, or escalate?"

## 3. Human-on-the-Loop, Not Human-in-Every-Step

The preferred model is human-on-the-loop.

Humans are on the loop when they:

- define direction;
- define constraints;
- review evidence when necessary;
- resolve ambiguity.

Humans are not in every step.

Humans should not:

- approve every file split;
- manually guide every import move;
- review every routine test or formatting change;
- become the default scheduler for Codex.

Codex should be able to perform routine local work without waiting for a human
message each time. When the rules are clear, Codex should act. When the rules
forbid the action, Codex should refuse. When the action is risky but valid,
Codex should produce evidence. When the decision cannot be resolved from rules
or evidence, Codex should escalate.

## 4. Human Responsibilities

Humans are responsible for the decisions that require project intent,
business judgment, or public accountability.

Human responsibilities include:

- define project goals and success criteria;
- define reusable engineering standards;
- define business and system invariants;
- decide ambiguous product tradeoffs;
- review evidence packages for high-risk changes;
- approve irreversible external effects;
- decide when a rule should be generalized into the reusable standard;
- decide what is publishable in the Medium/GitHub case study.

In this project, humans should focus on whether the standard is useful,
credible, reusable, and properly bounded. They should not be required to steer
every local documentation, test, or organization step.

## 5. Codex Responsibilities

Codex is responsible for executing within the written project boundaries and
making its decisions inspectable.

Codex responsibilities include:

- read relevant docs before acting;
- follow the project charter and deliverable boundaries;
- classify work into Auto Allow, Auto Deny, Evidence Gate, or Human
  Escalation;
- perform safe routine engineering autonomously;
- create or update documentation when required;
- generate task graphs for multi-step work;
- create evidence reports for gated work;
- preserve public contracts unless explicitly allowed to change them;
- report uncertainty and remaining risks;
- escalate only when rules cannot decide.

Codex should not treat missing human approval as permission to ignore
constraints. It should also not treat every uncertainty as a reason to stop.
The expected behavior is classification first, then action, refusal, evidence,
or escalation.

## 6. Autonomy Categories

This section defines the four autonomy categories at a principle level. It is
not the final detailed autonomy policy.

### Auto Allow

Auto Allow actions are safe, reversible, local, and verifiable. They should
proceed without asking humans.

Examples:

- creating documentation directories;
- creating Phase 0 boundary documents;
- adding report templates;
- splitting documentation by purpose;
- adding non-invasive tests;
- running tests, linters, formatters, and metrics scripts;
- creating local analysis reports;
- proposing task graphs;
- extracting code when behavior is unchanged and tests verify it, in later
  phases.

Auto Allow does not mean reckless execution. It means the action is inside
already-defined constraints. Codex must still stay within the current phase,
avoid unrelated changes, and report what it changed.

### Auto Deny

Auto Deny actions violate system invariants, safety rules, or project
boundaries. Codex should refuse these actions without asking humans to decide
whether a forbidden action is acceptable.

Examples:

- modifying production code during Phase 0;
- deleting tests to make checks pass;
- bypassing authorization or permission checks;
- exposing credentials or secrets;
- changing public API behavior without an evidence gate;
- turning the demonstration repository into a rewrite;
- mixing reusable standards with upload-control-plane-specific business rules;
- writing Medium narrative as a substitute for engineering evidence.

Auto Deny avoids wasting human attention on actions that should never be
accepted under the current rules. If the rule itself seems wrong, that is a
separate escalation about changing the rule, not permission to perform the
denied action.

### Evidence Gate

Evidence Gate actions may be valid but carry architectural, behavioral,
compatibility, or safety risk. They can proceed only with explicit evidence.

Examples:

- changing public API contracts;
- changing database schema;
- changing state-machine behavior;
- changing idempotency semantics;
- changing authorization semantics;
- restructuring major application modules;
- changing repository-wide architecture boundaries;
- extracting reusable templates after validation.

Required evidence may include:

- what changed;
- why it changed;
- what did not change;
- tests run;
- compatibility impact;
- rollback path;
- remaining risks.

Evidence Gate should reduce human synchronous review by making the result
reviewable after execution. The evidence package should let a human or later
Codex instance inspect the decision without reconstructing the whole session
from memory.

### Human Escalation

Human Escalation is reserved for decisions that cannot be resolved from written
rules or evidence.

Examples:

- ambiguous business meaning;
- conflicting valid design options;
- irreversible external side effects;
- production credentials, billing, deployment, or external publishing;
- conflicting rules;
- unclear publication boundaries;
- decisions that affect project thesis or public narrative.

Human Escalation should be rare and explicit. Codex should state the decision,
why existing rules do not decide it, what options exist, and what risk is being
placed on the human.

## 7. Decision Principle

Codex should ask:

1. Is this action clearly safe, reversible, local, and verifiable?

   - If yes: Auto Allow.

2. Does this action violate a known invariant, safety rule, or phase boundary?

   - If yes: Auto Deny.

3. Is this action potentially valid but risky?

   - If yes: Evidence Gate.

4. Is the decision ambiguous, irreversible, or product-level?

   - If yes: Human Escalation.

If more than one category seems applicable, Codex should choose the stricter
category and explain why. For example, a local refactor may be reversible, but
if it changes a public API contract it is not Auto Allow; it is at least
Evidence Gate.

## 8. Phase 0 Autonomy Boundary

Phase 0 defines boundaries. It does not modify implementation.

Allowed in Phase 0:

- create boundary documents under `docs/agentic-engineering/`;
- read README and existing docs;
- inspect repository structure lightly;
- clarify deliverable boundaries;
- define principles;
- propose later tasks.

Denied in Phase 0:

- modify production code;
- refactor modules;
- change tests;
- change API behavior;
- generate baseline metrics;
- create `AGENTS.md`;
- create the full reusable standard;
- create Medium drafts;
- make architecture changes.

Evidence Gate in Phase 0:

- Any proposal that changes the previously defined project goal or deliverable
  categories must explain why.
- Any proposal to expand Phase 0 scope must identify which later phase it
  belongs to.

Human Escalation in Phase 0:

- If Codex finds that the charter and deliverables conflict.
- If the repository purpose is unclear after reading available docs.
- If Codex cannot distinguish reusable standard content from
  demonstration-specific content.

For Task 0.3, creating this document is Auto Allow: it is a local documentation
change under the Phase 0 boundary and is directly requested by the task.

## 9. What This Document Is Not

This document is not:

- the final detailed autonomy policy;
- a permission configuration file;
- a full execution standard;
- a code review checklist;
- a replacement for tests;
- a reason to ask humans more often.

It is only the Phase 0 boundary document for human and agent roles.

## 10. Relationship to Later Documents

This document feeds later work without replacing it.

`autonomy-policy.md` will later turn these principles into more detailed rules.
It should define concrete approval triggers, allowed action classes, denied
operations, evidence-before-action requirements, and escalation examples.

`evidence-gate-standard.md` will define required evidence for risky work. It
should specify the expected contents of evidence packages, including command
evidence, diff evidence, compatibility notes, rollback paths, and risk
statements.

`AGENTS.md` will eventually become the executable entrypoint for Codex. It
should translate the mature standards into concise repository instructions that
Codex can follow during normal work.

Baseline reports will show what happened before these boundaries existed. They
should describe the repository state and agent behavior without pretending that
the later standard was already in force.

Governed refactoring will validate whether these boundaries change Codex
behavior. The validation question is whether Codex can make more reliable
routine progress with less human synchronous intervention while still
preserving system invariants and producing usable evidence.
