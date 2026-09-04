#!/usr/bin/env python3
"""Deterministic integration validation for Multilayer Honeycomb Lattice Dynamics."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]; UI_DIR=ROOT/"src-tauri"/"resources"/"ui"; sys.path.insert(0,str(UI_DIR))
TAURI_PATH=ROOT/"src-tauri"/"tauri.conf.json"; ENGINEERING_PATH=UI_DIR/"physical_lab_engineering.py"; WORKER_PATH=UI_DIR/"physical_lab_job_worker.py"

import physical_lab_job_worker as worker
import physical_lab_project_kernel as project
import physical_lab_lattice_dynamics as core
import physical_lab_lattice_workflow as workflow


def main()->None:
    cfg=core.LatticeConfig(duration=0.8,samples=128,damping=0.0,interlayer_damping=0.0,drive_mode="none",rtol=1e-10,atol=1e-12,max_step=0.015)
    model=core.build_lattice(cfg); degree=core.coordination_numbers(model)
    assert len(model.positions)==96
    assert len(model.inplane_i)==144
    assert np.all(degree==3)
    assert core.equilibrium_residual(model)<1e-14
    assert core.internal_force_imbalance(model)<1e-10

    result=core.integrate_case(cfg); summary=core.result_summary(result)
    assert result["solver"]["solver"]=="DOP853"
    assert summary["conservative_energy_relative_drift"]<1e-8
    assert summary["coordination_min"]==3 and summary["coordination_max"]==3
    assert summary["negative_mode_count"]==0
    assert summary["zero_mode_count"]==2
    modes=core.normal_modes(model)
    assert modes["zero_mode_count"]==2
    assert modes["negative_eigenvalue_count"]==0
    assert len(modes["first_positive_frequencies"])>0
    assert "not q-resolved" in modes["boundary"]

    # Seeded stochastic mode uses a fixed integration grid; repeated seed is reproducible.
    scfg=core.LatticeConfig(nx=2,ny=2,layers=2,duration=0.2,samples=101,stochastic_mode=True,temperature_reduced=0.02,damping=0.05,interlayer_damping=0.0,drive_mode="none",langevin_dt=0.002,seed=77)
    s1=core.integrate_case(scfg); s2=core.integrate_case(scfg)
    assert np.allclose(s1["time"],s2["time"])
    assert np.allclose(s1["states"],s2["states"])
    assert "not q-resolved" in s1["analysis"]["spectrum"]["label"]

    manifest_a=workflow.build_lattice_manifest(cfg,preset="compact",source_commit="validation-sha")
    manifest_b=workflow.build_lattice_manifest(cfg,preset="compact",source_commit="validation-sha")
    assert manifest_a["experiment_sha256"]==manifest_b["experiment_sha256"]
    assert manifest_a["model"]["variant"]==core.MODEL_VARIANT
    assert workflow.is_lattice_manifest(manifest_a)
    changed=workflow.build_lattice_manifest(core.LatticeConfig(**{**cfg.__dict__,"stacking":"ABC"}),preset="compact",source_commit="validation-sha")
    assert changed["experiment_sha256"]!=manifest_a["experiment_sha256"]

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PHYSICAL_LAB_DATA_DIR"]=tmp
        project_dir,_=project.create_project("Honeycomb CI",research_question="Synthetic reduced-unit lattice integration test")
        exp=project.register_experiment(project_dir,manifest_a); assert exp["experiment_sha256"]==manifest_a["experiment_sha256"]
        job_dir=Path(tmp)/"compute-jobs"/"job-honeycomb-ci"; job_dir.mkdir(parents=True)
        (job_dir/"manifest.json").write_text(json.dumps(manifest_a),encoding="utf-8")
        (job_dir/"job.json").write_text(json.dumps({"schema":"physical-lab-job-v1","id":"job-honeycomb-ci","profile":core.PROFILE,"experiment_sha256":manifest_a["experiment_sha256"],"runner":"model-campaign","runner_config":{"profile":core.PROFILE,"preset":"compact","model_variant":core.MODEL_VARIANT},"status":"queued","progress":0.0,"stage":"queued","created_at":"2026-09-04T00:00:00Z","updated_at":"2026-09-04T00:00:00Z","attempt":0}),encoding="utf-8")
        output=worker.execute_job(job_dir); record=json.loads((job_dir/"job.json").read_text()); persisted=json.loads((job_dir/"result.json").read_text())
        assert record["status"]=="succeeded"; assert persisted["model_variant"]==core.MODEL_VARIANT
        campaign=output["result"]; assert campaign["schema"]==workflow.CAMPAIGN_SCHEMA; assert campaign["screening"]["status"] in {"PASS","REVIEW"}
        assert campaign["geometry"]["coordination_min"]==3 and campaign["geometry"]["coordination_max"]==3
        assert len(campaign["stacking_sweep"])==3 and len(campaign["defect_audit"])==3
        assert campaign["metrics"]["conservative_energy_relative_drift_max"]<1e-6
        assert (job_dir/"checkpoint.json").exists()
        assert project.register_job_reference(project_dir,record,result=output)
        pdoc=project.open_project(project_dir); assert "job-honeycomb-ci" in pdoc["jobs"] and "job-honeycomb-ci" in pdoc["results"]
        report=workflow.render_report_markdown(manifest_a,campaign); assert manifest_a["experiment_sha256"] in report; assert "not an ab-initio" in report; assert "not q-resolved" in report

    tauri=TAURI_PATH.read_text(); assert "physical_lab_lattice_dynamics.py" in tauri and "physical_lab_lattice_workflow.py" in tauri and "physical_lab_lattice_ui.py" in tauri
    facade=ENGINEERING_PATH.read_text(); assert "render_lattice_workspace" in facade and "oscillation-integration" in facade
    worker_source=WORKER_PATH.read_text(); assert "execute_lattice_manifest" in worker_source and "honeycomb-" in worker_source
    print("Honeycomb lattice dynamics validation: PASS")


if __name__=="__main__": main()
