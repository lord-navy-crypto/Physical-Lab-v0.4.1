"""Experiment/Compute/Project adapter for Multilayer Honeycomb Lattice Dynamics."""
from __future__ import annotations

import math
import os
import platform
import sys
from dataclasses import asdict, replace
from typing import Any, Callable, Mapping

import numpy as np

from physical_lab_experiment_kernel import build_experiment_manifest, experiment_fingerprint, plain, validate_manifest
from physical_lab_lattice_dynamics import MODEL_SCHEMA, MODEL_TITLE, MODEL_VARIANT, PROFILE, LatticeConfig, build_lattice, conservative_config, coordination_numbers, equilibrium_residual, integrate_case, internal_force_imbalance, normal_modes, result_summary

WORKFLOW_SCHEMA = "physical-lab-honeycomb-workflow-v1"
CAMPAIGN_SCHEMA = "physical-lab-honeycomb-verification-campaign-v1"
PRESETS = {
    "compact": {"conservative_duration": 1.5, "characterization_duration": 2.0, "samples": 180, "max_atoms": 150, "stacking_sweep": ["AA", "ABA", "ABC"]},
    "standard": {"conservative_duration": 3.0, "characterization_duration": 4.0, "samples": 360, "max_atoms": 220, "stacking_sweep": ["AA", "ABA", "ABC"]},
}
DEFAULT_REQUIREMENTS = {
    "coordination_error_max": 0.0,
    "equilibrium_force_residual_max": 1e-10,
    "internal_force_imbalance_max": 1e-10,
    "conservative_energy_relative_drift_max": 1e-6,
    "refinement_relative_change_max": 5e-4,
    "negative_mode_eigenvalue_magnitude_max": 1e-8,
    "translation_zero_mode_count_error_max": 0.0,
}


def _finite(value: Any, name: str) -> float:
    x = float(value)
    if not math.isfinite(x): raise ValueError(f"{name} must be finite")
    return x


def config_parameters(config: LatticeConfig) -> dict[str, Any]:
    config.validate(); return plain(asdict(config))


def config_from_parameters(parameters: Mapping[str, Any]) -> LatticeConfig:
    defaults = asdict(LatticeConfig()); values = {k: parameters.get(k, v) for k, v in defaults.items()}
    for key in ("nx", "ny", "layers", "samples", "seed"): values[key] = int(values[key])
    values["stochastic_mode"] = bool(values["stochastic_mode"])
    cfg = LatticeConfig(**values); cfg.validate(); return cfg


def build_lattice_manifest(config: LatticeConfig, *, preset: str = "compact", requirements: Mapping[str, float] | None = None, source_commit: str | None = None) -> dict[str, Any]:
    if preset not in PRESETS: raise ValueError(f"unsupported lattice preset: {preset}")
    config.validate(); req = dict(DEFAULT_REQUIREMENTS)
    if requirements:
        for key, value in requirements.items():
            if key in req: req[key] = _finite(value, key)
    manifest = build_experiment_manifest(
        PROFILE,
        parameters=config_parameters(config),
        inputs={"units":"dimensionless reduced lattice units","degrees_of_freedom":"in-plane x/y displacement per site","periodic_boundary":True,"stacking_boundary":"AA/ABA/ABC are geometric registry proxies in this reduced model."},
        execution={"mode":"honeycomb-verification-campaign","preset":preset,"model_variant":MODEL_VARIANT},
        requirements=[{"metric":k,"operator":"<=","limit":float(v)} for k,v in req.items()],
        uncertainty={"mode":"deterministic-verification-with-optional-seeded-Langevin-process","probabilistic_uq":False,"boundary":"A seeded Langevin trajectory is a stochastic process realization, not an uncertainty distribution over material properties or a calibrated thermal experiment."},
        provenance={"source_profile":PROFILE,"source_commit":source_commit or os.environ.get("PHYSICAL_LAB_SOURCE_COMMIT") or None,"engine_mode":os.environ.get("PHYSICAL_LAB_ENGINE_MODE","safe"),"solver_backend":"SciPy DOP853 deterministic + fixed-step Euler-Maruyama optional Langevin","python":sys.version.split()[0],"platform":platform.platform(),"model_schema":MODEL_SCHEMA,"workflow_schema":WORKFLOW_SCHEMA},
    )
    manifest["model"] = {"title":MODEL_TITLE,"domain":"reduced-unit-condensed-matter-lattice-dynamics","profile_title":"Oscillation & Numerical Integration","variant":MODEL_VARIANT,"adapter_capabilities":["manifest","model-campaign"],"scientific_boundary":"Reduced-unit honeycomb lattice dynamics; not ab-initio graphene, not a calibrated interatomic potential, and local FFT is not q-resolved phonon dispersion."}
    manifest["experiment_sha256"] = experiment_fingerprint(manifest)
    check = validate_manifest(manifest)
    if not check["valid"]: raise ValueError("invalid honeycomb manifest: " + "; ".join(check["errors"]))
    return manifest


def is_lattice_manifest(manifest: Mapping[str, Any], runner_config: Mapping[str, Any] | None = None) -> bool:
    model, execution = manifest.get("model"), manifest.get("execution")
    candidates = {str((model or {}).get("variant") if isinstance(model,Mapping) else ""),str((execution or {}).get("model_variant") if isinstance(execution,Mapping) else ""),str((runner_config or {}).get("model_variant") or "")}
    return MODEL_VARIANT in candidates


def _bounded_config(config: LatticeConfig, preset: str, *, duration_key: str) -> LatticeConfig:
    p = PRESETS[preset]; nx,ny,layers = int(config.nx),int(config.ny),int(config.layers)
    while 2*nx*ny*layers > int(p["max_atoms"]):
        if nx >= ny and nx > 2: nx -= 1
        elif ny > 2: ny -= 1
        elif layers > 1: layers -= 1
        else: break
    duration = min(float(config.duration), float(p[duration_key])); samples = min(int(config.samples), int(p["samples"])); stochastic = bool(config.stochastic_mode); langevin_dt=float(config.langevin_dt)
    if stochastic:
        max_steps=max(64,samples-1); langevin_dt=max(duration/max_steps,float(config.langevin_dt)); samples=int(round(duration/langevin_dt))+1; samples=max(64,min(samples,int(p["samples"]))); langevin_dt=duration/max(samples-1,1)
    return replace(config,nx=nx,ny=ny,layers=layers,duration=duration,samples=samples,max_step=min(float(config.max_step),0.025 if preset=="compact" else 0.015),rtol=min(float(config.rtol),1e-9),atol=min(float(config.atol),1e-11),langevin_dt=langevin_dt)


def _refinement_metric(base_config: LatticeConfig) -> dict[str, Any]:
    loose_cfg=replace(base_config,rtol=1e-7,atol=1e-9,max_step=max(base_config.max_step,0.03)); tight_cfg=replace(base_config,rtol=1e-10,atol=1e-12,max_step=min(base_config.max_step,0.015))
    loose=integrate_case(loose_cfg); tight=integrate_case(tight_cfg); a=np.asarray(loose["analysis"]["displacement"],dtype=float); b=np.asarray(tight["analysis"]["displacement"],dtype=float); scale=max(1e-12,float(np.max(np.abs(b))))
    return {"relative_change_max":float(np.max(np.abs(a-b))/scale),"loose_nfev":int(loose["solver"].get("nfev",0)),"tight_nfev":int(tight["solver"].get("nfev",0))}


def _screen(metrics: Mapping[str,float], requirements: Mapping[str,float]) -> dict[str, Any]:
    rows=[]; status="PASS"
    for key,limit in requirements.items():
        value=float(metrics[key]); margin=float(limit)-value; row_status="PASS" if margin>=0 else "REVIEW"
        if row_status!="PASS": status="REVIEW"
        rows.append({"metric":key,"value":value,"limit":float(limit),"operator":"<=","signed_margin":margin,"status":row_status})
    return {"status":status,"requirements":rows,"boundary":"PASS/REVIEW is a computational screening result for this reduced model, not material certification or experimental validation."}


def execute_lattice_manifest(manifest: Mapping[str, Any], *, runner_config: Mapping[str, Any] | None = None, cancel_check: Callable[[],bool] | None = None, progress_callback: Callable[[str,float,Mapping[str,Any]],None] | None = None) -> dict[str, Any]:
    if not is_lattice_manifest(manifest,runner_config): raise ValueError("manifest is not a multilayer honeycomb lattice experiment")
    check=validate_manifest(manifest)
    if not check["valid"]: raise ValueError("invalid manifest: "+"; ".join(check["errors"]))
    preset=str((runner_config or {}).get("preset") or (manifest.get("execution") or {}).get("preset") or "compact")
    if preset not in PRESETS: raise ValueError(f"unsupported lattice preset: {preset}")
    cfg=config_from_parameters(manifest.get("parameters") or {})
    def stop():
        if cancel_check and cancel_check(): raise InterruptedError("honeycomb verification campaign cancelled")
    def progress(stage,fraction,payload=None):
        if progress_callback: progress_callback(stage,fraction,plain(dict(payload or {})))
    stop(); progress("geometry-audit",0.08); model=build_lattice(cfg); degree=coordination_numbers(model); coordination_error=float(np.max(np.abs(degree-3))); eq_residual=equilibrium_residual(model); imbalance=internal_force_imbalance(model)
    stop(); progress("conservative-baseline",0.22); base_cfg=conservative_config(_bounded_config(cfg,preset,duration_key="conservative_duration"),duration=PRESETS[preset]["conservative_duration"]); base=integrate_case(base_cfg); base_summary=result_summary(base); energy_drift=float(base_summary["conservative_energy_relative_drift"] or 0.0)
    stop(); progress("solver-refinement",0.42); refinement=_refinement_metric(base_cfg)
    stop(); progress("normal-modes",0.58); modes=normal_modes(model); negative_magnitude=max(0.0,-float(modes["most_negative_eigenvalue"])); zero_error=float(abs(int(modes["zero_mode_count"])-2))
    stop(); progress("characterization",0.70); char_cfg=_bounded_config(cfg,preset,duration_key="characterization_duration"); characterization=integrate_case(char_cfg); char_summary=result_summary(characterization)
    stop(); progress("stacking-sweep",0.84); stacking_rows=[]
    for stacking in PRESETS[preset]["stacking_sweep"]:
        smodes=normal_modes(build_lattice(replace(cfg,stacking=stacking))); positive=smodes["first_positive_frequencies"]; stacking_rows.append({"stacking":stacking,"first_positive_frequency":float(positive[0]) if positive else None,"zero_mode_count":int(smodes["zero_mode_count"]),"negative_mode_count":int(smodes["negative_eigenvalue_count"])})
    stop(); progress("defect-audit",0.92); defect_rows=[]
    for defect in ("none","mass","weak-bond"):
        dmodel=build_lattice(replace(cfg,defect_mode=defect)); dmodes=normal_modes(dmodel); positive=dmodes["first_positive_frequencies"]; defect_rows.append({"defect_mode":defect,"first_positive_frequency":float(positive[0]) if positive else None,"defect_sites":int(np.count_nonzero(dmodel.defect_mask))})
    metrics={"coordination_error_max":coordination_error,"equilibrium_force_residual_max":float(eq_residual),"internal_force_imbalance_max":float(imbalance),"conservative_energy_relative_drift_max":energy_drift,"refinement_relative_change_max":float(refinement["relative_change_max"]),"negative_mode_eigenvalue_magnitude_max":negative_magnitude,"translation_zero_mode_count_error_max":zero_error}
    requirements=dict(DEFAULT_REQUIREMENTS)
    for row in manifest.get("requirements") or []:
        if isinstance(row,Mapping) and row.get("metric") in requirements: requirements[str(row["metric"])]=float(row["limit"])
    screening=_screen(metrics,requirements); progress("complete",1.0,{"screening_status":screening["status"]})
    return {"schema":CAMPAIGN_SCHEMA,"model_variant":MODEL_VARIANT,"profile":PROFILE,"experiment_sha256":manifest.get("experiment_sha256"),"preset":preset,"metrics":metrics,"screening":screening,"geometry":{"atoms":int(len(model.positions)),"inplane_bonds":int(len(model.inplane_i)),"interlayer_pairs":int(len(model.inter_i)),"coordination_min":int(np.min(degree)),"coordination_max":int(np.max(degree))},"conservative_baseline":base_summary,"refinement":refinement,"normal_modes":{"zero_mode_count":int(modes["zero_mode_count"]),"negative_mode_count":int(modes["negative_eigenvalue_count"]),"most_negative_eigenvalue":float(modes["most_negative_eigenvalue"]),"first_positive_frequencies":modes["first_positive_frequencies"][:12],"boundary":modes["boundary"]},"characterization":char_summary,"stacking_sweep":stacking_rows,"defect_audit":defect_rows,"scientific_boundary":"This is a reduced-unit finite-cell lattice model. Stacking and interlayer shear are geometric/phenomenological proxies; local FFT is not phonon dispersion."}


def render_report_markdown(manifest: Mapping[str, Any], campaign: Mapping[str, Any]) -> str:
    lines=["# Physical Lab · Multilayer Honeycomb Lattice Dynamics","",f"- Experiment SHA-256: `{manifest.get('experiment_sha256')}`",f"- Screening: **{(campaign.get('screening') or {}).get('status','REVIEW')}**",f"- Profile: `{PROFILE}`",f"- Model variant: `{MODEL_VARIANT}`","","## Scientific boundary","",str(campaign.get("scientific_boundary") or ""),"","The model uses dimensionless reduced units. It is not an ab-initio graphene calculation, not a calibrated material model, and its local time-series FFT is not q-resolved phonon dispersion.","","## Verification metrics","","| Metric | Value | Limit | Status |","|---|---:|---:|---|"]
    for row in (campaign.get("screening") or {}).get("requirements") or []: lines.append(f"| {row.get('metric')} | {float(row.get('value',0.0)):.6g} | {float(row.get('limit',0.0)):.6g} | {row.get('status')} |")
    lines += ["","## Geometry","","```json",str(plain(campaign.get("geometry") or {})),"```","","## Normal-mode audit","","```json",str(plain(campaign.get("normal_modes") or {})),"```","","## Stacking characterization","","```json",str(plain(campaign.get("stacking_sweep") or [])),"```","","## Interpretation boundary","","PASS means the configured numerical/structural screening criteria passed for this model. It does not establish a real material's phonon spectrum, thermal conductivity, or experimental validity.",""]
    return "\n".join(lines)
