#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one release-hardening anchor in {path}: found {count}\nANCHOR:\n{old}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    readme = ROOT / "README.md"
    replace_once(
        readme,
        "**Physical Lab is a native macOS research workbench that turns seven computational-physics projects into one reproducible engineering workflow: requirement → model → automated campaign → verify → validate → compare → optimize → measure → calibrate → decide.**",
        "**Physical Lab is a native macOS Evidence-First Engineering Systems Workbench that turns seven computational-physics projects into one reproducible workflow: model / measurement → evidence → engineering decision → operations → quality / reliability → risk / economics → requirements / verification → human review.**",
    )
    replace_once(
        readme,
        "| What engineering questions can it answer? | Requirement margin, uncertainty budget, sensitivity, convergence, cost↔accuracy tradeoff, finite-ensemble robustness, measured/model discrepancy, Pareto design comparison, bounded calibration, batch planning |",
        "| What engineering questions can it answer? | Requirement margin, uncertainty budget, sensitivity, convergence, cost↔accuracy tradeoff, Pareto decisions, operations/capacity, quality & reliability evidence, risk & economics, requirements & verification planning, measured/model discrepancy, bounded calibration |",
    )
    replace_once(
        readme,
        "## Seven validated Lab interfaces\n",
        "## Evidence-First Engineering Systems Workbench\n\nPhysical Lab now uses one canonical `.physlab` Project state across the physics Labs and the engineering-review layers. The shared Evidence Center contains nine coordinated views:\n\n1. **Credibility Passport** — evidence coverage and graph traceability, without an aggregate credibility score.\n2. **Claims** — explicit claim-to-evidence readiness and freshness.\n3. **Cross-Checks** — declared method/source comparisons with tolerance and stale-evidence detection.\n4. **Engineering Decisions** — constraints, feasibility and Pareto trade studies with human selection rationale.\n5. **Operations** — declared resource capacity, task precedence, queue wait, utilization, makespan and dispatch-policy comparison.\n6. **Quality & Reliability** — replicate variation, descriptive factor contrasts, specification context and observed event/exposure summaries.\n7. **Risk & Economics** — explicit probability × consequence arithmetic and signed cash-flow present-worth calculations.\n8. **Requirements & Verification** — normative `shall` requirements, source/upstream trace IDs, test/analysis/inspection/demonstration planning, evidence freshness and human review notes.\n9. **Snapshots & Diff** — deterministic evidence snapshots and review-state change detection.\n\nThe architecture is deliberately evidence-first rather than score-first. Physical Lab does **not** emit one synthetic engineering score, machine truth verdict, automatic requirement PASS, risk acceptance, process qualification, safety approval, standards-compliance claim, or certification verdict.\n\nThe canonical product chain is:\n\n```text\nSimulation / Measurement\n        ↓\nProject Kernel + Measurement Evidence\n        ↓\nVerification / UQ / Evidence Graph\n        ↓\nClaims + Cross-Checks + Evidence Freshness\n        ↓\nEngineering Decisions\n        ↓\nOperations\n        ↓\nQuality & Reliability\n        ↓\nRisk & Economics\n        ↓\nRequirements & Verification\n        ↓\nHuman Review + Evidence Snapshot / Diff\n```\n\nNew projects live directly in canonical `projects/*.physlab` stores. The old workspace-alias mechanism has been retired; genuine legacy workspaces remain an explicit compatibility/migration boundary rather than a second active Project system.\n\nSee `docs/V010_RELEASE_READINESS.md` plus the individual Engineering Systems layer design notes under `docs/`.\n\n## Seven validated Lab interfaces\n",
    )

    changelog = ROOT / "CHANGELOG.md"
    replace_once(
        changelog,
        "All notable Physical Lab changes are recorded here. Version numbers follow SemVer (`MAJOR.MINOR.PATCH`).\n\n## [0.9.0] - 2026-09-04\n",
        "All notable Physical Lab changes are recorded here. Version numbers follow SemVer (`MAJOR.MINOR.PATCH`).\n\n## [Unreleased]\n\n### Added — Evidence-First Engineering Systems\n- **Credibility Passport + Evidence Graph** with explicit PRESENT / PARTIAL / MISSING factors and no aggregate credibility score.\n- **Claim-to-Evidence Matrix** and evidence freshness states, without machine truth/proof verdicts.\n- **Cross-Checks + Evidence Snapshots/Diff** for declared method/source corroboration and review-state change detection.\n- **Engineering Decision Layer** with explicit constraints, feasibility, Pareto non-dominance and human decision rationale.\n- **Operations Layer** with finite resource capacity, task precedence, queue wait, utilization, makespan and transparent dispatch-policy comparison.\n- **Quality & Reliability Layer** with descriptive variation, pooled replicate repeatability, factor contrasts, specification context and observed reliability-event/exposure evidence.\n- **Risk & Engineering Economics Layer** with user-declared probabilities/consequences and explicit signed cash-flow present-worth arithmetic.\n- **Requirements & Verification Planning** with normative `shall` requirements, source/upstream trace identifiers, test/analysis/inspection/demonstration methods, success criteria, evidence freshness and human review notes.\n- Shared nine-tab Evidence Center using the same canonical `.physlab` Project state across all engineering-review layers.\n\n### Changed — Project / desktop architecture\n- Unified new desktop projects on canonical `projects/*.physlab` storage.\n- Retired compatibility workspace-alias creation while preserving genuine legacy workspace discovery/bridge behavior.\n- Moved Rust project read, analysis, write, campaign, measurement, serial-capture and reproducibility-export paths to direct canonical/legacy resolvers rather than symlink aliases.\n- Separated non-project desktop runtime support from frozen `research_legacy_impl.rs`; the legacy implementation remains a regression/compatibility fixture rather than an active runtime module.\n\n### Release hardening\n- Added `scripts/v010_release_readiness_validation.py` and `docs/V010_RELEASE_READINESS.md`.\n- README now describes the actual Evidence-First Engineering Systems architecture instead of only the v0.9 campaign milestone.\n- Self-check now requires all Decision / Operations / Quality & Reliability / Risk & Economics / Requirements & Verification core and UI modules, Tauri resources, and Evidence Center tabs.\n- The release-hardening branch intentionally remains version `0.9.0`; version metadata advances only in a dedicated release PR after all contracts are green.\n\n### Scientific / professional boundary\nThese additions organize engineering evidence, planning, trade studies and human review. They do not establish scientific truth, experimental validation of every model, process capability, field reliability, calibrated risk, financial advice, formal product verification/validation, qualification, acceptance, safety approval, standards compliance, NASA endorsement, ABET accreditation, or certification.\n\n## [0.9.0] - 2026-09-04\n",
    )

    self_check = ROOT / "scripts" / "self_check.py"
    replace_once(
        self_check,
        "    'src-tauri/resources/ui/physical_lab_evidence_center_ui.py',\n    'src-tauri/resources/ui/physical_lab_project_surface_patch.py',\n",
        "    'src-tauri/resources/ui/physical_lab_evidence_center_ui.py',\n    'src-tauri/resources/ui/physical_lab_engineering_decisions.py',\n    'src-tauri/resources/ui/physical_lab_engineering_decision_ui.py',\n    'src-tauri/resources/ui/physical_lab_operations_planning.py',\n    'src-tauri/resources/ui/physical_lab_operations_ui.py',\n    'src-tauri/resources/ui/physical_lab_quality_reliability.py',\n    'src-tauri/resources/ui/physical_lab_quality_reliability_ui.py',\n    'src-tauri/resources/ui/physical_lab_risk_economics.py',\n    'src-tauri/resources/ui/physical_lab_risk_economics_ui.py',\n    'src-tauri/resources/ui/physical_lab_requirements_verification.py',\n    'src-tauri/resources/ui/physical_lab_requirements_verification_ui.py',\n    'src-tauri/resources/ui/physical_lab_project_surface_patch.py',\n",
    )
    replace_once(
        self_check,
        "    'resources/ui/physical_lab_evidence_center_ui.py',\n    'resources/ui/physical_lab_project_surface_patch.py',\n",
        "    'resources/ui/physical_lab_evidence_center_ui.py',\n    'resources/ui/physical_lab_engineering_decisions.py',\n    'resources/ui/physical_lab_engineering_decision_ui.py',\n    'resources/ui/physical_lab_operations_planning.py',\n    'resources/ui/physical_lab_operations_ui.py',\n    'resources/ui/physical_lab_quality_reliability.py',\n    'resources/ui/physical_lab_quality_reliability_ui.py',\n    'resources/ui/physical_lab_risk_economics.py',\n    'resources/ui/physical_lab_risk_economics_ui.py',\n    'resources/ui/physical_lab_requirements_verification.py',\n    'resources/ui/physical_lab_requirements_verification_ui.py',\n    'resources/ui/physical_lab_project_surface_patch.py',\n",
    )
    replace_once(
        self_check,
        "for needle in ['Credibility Passport','Claims','Cross-Checks','Snapshots & Diff','register_claim','register_cross_check','write_evidence_snapshot']:\n    assert needle in evidence_ui, needle\n",
        "for needle in ['Credibility Passport','Claims','Cross-Checks','Engineering Decisions','Operations','Quality & Reliability','Risk & Economics','Requirements & Verification','Snapshots & Diff','register_claim','register_cross_check','write_evidence_snapshot']:\n    assert needle in evidence_ui, needle\n",
    )
    replace_once(
        self_check,
        "print('Shared Project surface + Evidence Center: configured')\n",
        "print('Shared Project surface + Evidence Center: configured')\nprint('Engineering Systems layers: Decisions + Operations + Quality/Reliability + Risk/Economics + Requirements/Verification configured')\n",
    )

    print("v0.10 release-hardening guarded integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
