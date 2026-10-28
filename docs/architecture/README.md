# Dr. Listener solution architecture

**Review date:** 2026-10-28. **Code baseline:** [`b8e1b875809587aaebcde5bf5726ec1407d15264`](https://github.com/darpan02-cypher/Dr.Listner/tree/b8e1b875809587aaebcde5bf5726ec1407d15264).

This architecture package is for contributors building, reviewing, operating, and maintaining Dr. Listener. It documents the working prototype and proposes an incremental design for a secure, scalable service. The documentation does not implement that service or establish clinical readiness.

Dr. Listener is currently a **synthetic-data research prototype**: a Streamlit interface, deterministic Python visit orchestration, specialist LLM agents, speech integration, and file-based evaluation. There is no application database, authenticated application API, tenant isolation, or checked-in deployment pipeline at this baseline.

## Read the design

| Document | What it answers |
| --- | --- |
| [Current system](CURRENT-SYSTEM.md) | What runs today, source structure, dependencies, workflows, integration contracts, and differences between demo and live paths |
| [Solution design](SOLUTION-DESIGN.md) | System context, proposed components, end-to-end interactions, data flow, scaling decisions, and trade-offs |
| [API contracts](API-CONTRACTS.md) | Proposed HTTP, event, and audio interfaces; authorization, ordering, idempotency, failures, and examples |
| [Data and security](DATA-AND-SECURITY.md) | Current Pydantic schemas and storage, proposed database model, trust boundaries, security risks, and privacy controls |
| [Operations and roadmap](OPERATIONS-AND-ROADMAP.md) | Current deployment, target infrastructure, dependency management, testing, observability, recovery, and phased delivery |
| [Architecture decisions](ARCHITECTURE-SPINE.md) | Stable decisions that keep independently developed components compatible |
| [Validation record](VALIDATION.md) | What was reviewed and checked, what was not tested, and known limitations |

## Status labels

- **CURRENT / ADOPTED:** supported by source at the baseline, or an existing project constraint. A documented constraint is not proof that every path enforces it.
- **PROPOSED:** a design recommendation for a future implementation. Routes, SQL entities, jobs, authentication, and deployment components bearing this label do not exist in the current application.
- **OPEN:** requires owner input or measurement before implementing that phase. Open production decisions do not prevent maintaining or contributing to the synthetic prototype.

[`src/schemas.py`](../../src/schemas.py) remains authoritative for implemented field names. [`SPEC.md`](../../SPEC.md) provides intended semantics, subject to the implementation differences recorded here. The older [architecture document](../Dr.Listner%20architecture%20document.docx), [project report](../PROJECT_REPORT.md), and [SRS](../../Project-SRS.docx) are historical inputs; this package does not silently rewrite them.

## Diagram index

The diagrams are editable Mermaid blocks in Markdown and render directly on GitHub. Keep each diagram beside its explanation; update its labels whenever an interface or ownership rule changes.

| View | Location |
| --- | --- |
| Current components and visit sequence | [Current system](CURRENT-SYSTEM.md) |
| Proposed context and service boundaries | [Solution design](SOLUTION-DESIGN.md#system-context-and-trust-boundaries) |
| Proposed processing and information flow | [Solution design](SOLUTION-DESIGN.md#end-to-end-data-flow) |
| Proposed end-of-visit sequence | [Solution design](SOLUTION-DESIGN.md#finalization-and-review) |
| Proposed visit lifecycle | [API contracts](API-CONTRACTS.md#visit-lifecycle) |
| Proposed database relationships | [Data and security](DATA-AND-SECURITY.md) |
| Proposed deployment | [Operations and roadmap](OPERATIONS-AND-ROADMAP.md) |
| Proposed dependency direction | [Architecture decisions](ARCHITECTURE-SPINE.md#design-paradigm) |

## Important findings

1. **DEMO is not a global network isolation switch.** The core `LLMClient` is cache-only in DEMO, but live audio and its direct Groq speaker-role classification use separate paths. Do not enable the microphone when demonstrating a network-free workflow.
2. **The audio service is not isolated per user.** A cached `LiveSTT` resource and loopback relay need redesign before a shared remote deployment.
3. **De-identification is incomplete as a system boundary.** Raw audio leaves the browser for Deepgram, role classification can receive raw text, and chart/export/baseline paths rely on synthetic data. A `synthetic: true` field cannot detect real patient information.
4. **Files and memory are the current state stores.** Cached responses and exports can contain evidence quotes. Hashing a cache filename does not anonymize its contents.
5. **Clinical performance is unproven.** Synthetic fixtures, planted gaps, mock tests, and readability measures are engineering evidence, not clinical validation.

See the supporting source references and mitigation priorities in the linked documents. No real patient data or credentials are needed to review this package.

## How contributors maintain this package

1. Start from the current source and tests, then change the affected current-system section in the same pull request as a behavior change. Update the baseline commit when conducting a new full review; retain the review date so readers can assess staleness.
2. For a design change, amend the relevant `AD-n` in [architecture decisions](ARCHITECTURE-SPINE.md), retain its ID, and record the reason in the pull request. Add a new ID for a new invariant. Change PROPOSED to ADOPTED only when the implementation and acceptance evidence exist.
3. Keep API field names, entity ownership, lifecycle states, diagrams, and tests consistent. An API addition needs authorization, idempotency, failure, and versioning behavior, not just a route name.
4. Render changed Mermaid blocks and check relative links. Never copy keys, patient information, raw prompts, or unreviewed model output into examples or screenshots.
5. Have a contributor familiar with the changed component review technical claims. Clinical content and any non-synthetic use need the separate domain and privacy review described in the roadmap.

## Repository access and publication

GitHub's contribution history and write permission are different things. Public repository readers can submit pull requests from a fork; collaborator access must be granted by the repository owner. At review time, the connected account `sairohiththummarakoti` had read access and no write/admin permission to `darpan02-cypher/Dr.Listner`.

The owner can invite that account from **Settings → Collaborators → Add people**; the invitee must accept. The access request accompanies the architecture pull request. Documentation in a pull request is reviewable, but it becomes part of the default branch only after the owner or an authorized maintainer merges it. See [GitHub's collaborator invitation guide](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository).
