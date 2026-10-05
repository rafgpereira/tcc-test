# Specification Quality Checklist: Extração, Validação e Persistência do Dataset Experimental

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-18
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- **Implementation details**: the spec names the source dataset, C++ compilation standards
  (gnu++20 → gnu++11), GCC-based flag adaptation, streaming reads and the SHA-256 algorithm.
  These are not design choices made here: they are requirements stated in the feature
  description and in `docs/metodologia-referencia.md` / the Constitution, so they are kept as
  domain constraints. No programming language, library, schema tool, container tool or code
  structure for the pipeline itself is prescribed. Success criteria contain no tool names.
- **Clarification markers**: none were needed. Gaps that had a reasonable default were
  resolved as documented assumptions/decisions (spec section "Divergências e Decisões sobre a
  Metodologia", D1–D6). D1–D5 were reviewed and confirmed/decided by the authors on
  2026-09-18 (D2: drop the Windows-only linker stack flag and apply a 256 MiB runtime stack
  limit; D5: no hard quota, alert if any macro-category has fewer than 30 problems).
- **Carry-over to planning**: D2 must be honored consistently by the later evaluation sandbox.
- **Engine + AC validation (D7)**: the reference solution (AC) now goes through the same
  execution engine as the incorrect submissions (FR-010b, FR-011, FR-011a); the engine is
  verified with known-verdict programs first (FR-010a, US2, SC-013); a per-problem
  `validacao.json` (FR-021a) and a re-execution audit (FR-015a, SC-014) make this checkable.
  `validacao.json` and the re-execution audit are additions beyond the original methodology
  file structure and can be dropped if the authors judge them out of scope.
- **AC failure policy (D8)**: any AC failure in the engine (selection or audit) halts that
  problem immediately and records it in `validacao.json` for manual triage; no tolerance
  threshold, no automatic replacement of the AC, no waiting to accumulate (FR-011b, SC-015).
  FR-021a and FR-015a were kept by the authors.
- **Plan-review decisions (2026-09-19)**: D9 file-I/O eligibility criterion (FR-004(h)), D10
  measured dataset numbers, D11 seed 42; D6 (manifest in `manifests/`) and D7 (engine in its own
  package) confirmed. Spec sections and the scenario/edge-case lists were updated accordingly.
- **Retroactive audit (2026-09-19, Principle XI / constitution v1.2.0)**: plan items 5 and 7–10
  ("to reflect") and the data measured during planning were propagated into the spec (D12,
  FR-001, FR-018b, FR-026, D2) and the methodology; documentation requirements added as
  FR-031, FR-032, SC-016 (D14); operational engine rules are tracked as proposals (D13).
- **Analysis remediation (2026-09-19)**: after `/speckit-analyze`, the authors approved fixes for
  U1, U2, I1, I2, A1, G1, I3, I4, I5 and C1 (constitution amended to v1.2.1 instead of a
  per-feature deviation), plus the `data/work/` `0700` permission (D15). SC-001 now says six file
  types; FR-031/FR-032/SC-016 are tied to `scripts/check_docs_sync.py`. U3, U4, U5, G2, U6, D1,
  I6, U7, G3 and A2 were intentionally left open.
- **Second remediation (2026-09-19)**: U8 (C6 ignores struck-through and legend text), U9 (C2 scoped
  per module: full two-way check only for the CLI owner), I8 (`.gitignore` copied into the image and
  mounted read-only by the override, `repo_root` fixture), A3 (stamp revision = host
  `git rev-parse --short=7 HEAD`, `+dirty` rejected at closing; script loaded by
  `importlib`) and I6 (quickstart range) applied.
