"""Streamlit workspace for Multilayer Honeycomb Lattice Dynamics."""
from __future__ import annotations

import os
from typing import Any, Mapping

import numpy as np

from physical_lab_lattice_dynamics import MODEL_TITLE, MODEL_VARIANT, LatticeConfig, build_lattice, integrate_case, normal_modes, result_summary
from physical_lab_lattice_workflow import build_lattice_manifest, render_report_markdown


def _config(st: Any) -> LatticeConfig:
    a,b,c,d=st.columns(4)
    nx=int(a.number_input("Cells x",2,10,4,1,key="pl_lat_nx")); ny=int(b.number_input("Cells y",2,10,4,1,key="pl_lat_ny")); layers=int(c.number_input("Layers",1,5,3,1,key="pl_lat_layers")); stacking=d.selectbox("Stacking",["AA","ABA","ABC"],index=1,key="pl_lat_stacking")
    a,b,c,d=st.columns(4)
    k_in=float(a.number_input("In-plane k",0.1,100.0,10.0,key="pl_lat_k_in")); alpha=float(b.number_input("Cubic anharmonicity",0.0,50.0,2.0,key="pl_lat_alpha")); k_inter=float(c.number_input("Interlayer shear k",0.01,50.0,3.0,key="pl_lat_k_inter")); strain=float(d.number_input("Affine x-geometry strain",-0.20,0.20,0.0,0.01,key="pl_lat_strain"))
    a,b,c,d=st.columns(4)
    defect=a.selectbox("Defect model",["none","mass","weak-bond","line-weak-bond"],key="pl_lat_defect"); drive=b.selectbox("Drive",["none","sin","pulse","beat","chirp"],index=1,key="pl_lat_drive"); amp=float(c.number_input("Drive amplitude",0.0,2.0,0.08,key="pl_lat_drive_amp")); freq=float(d.number_input("Drive angular frequency",0.05,20.0,1.0,key="pl_lat_drive_freq"))
    a,b,c,d=st.columns(4)
    damping=float(a.number_input("Local damping",0.0,2.0,0.02,key="pl_lat_damping")); inter_damping=float(b.number_input("Interlayer damping",0.0,2.0,0.01,key="pl_lat_inter_damping")); duration=float(c.number_input("Duration",0.5,60.0,12.0,key="pl_lat_duration")); samples=int(d.number_input("Uniform output samples",128,10000,1000,64,key="pl_lat_samples"))
    stochastic=st.toggle("Seeded reduced-unit Langevin mode",value=False,key="pl_lat_stochastic")
    temp=0.0; seed=12345; ldt=0.005
    if stochastic:
        a,b,c=st.columns(3); temp=float(a.number_input("Reduced temperature",0.0,5.0,0.05,key="pl_lat_temp")); seed=int(b.number_input("RNG seed",0,2_000_000_000,12345,key="pl_lat_seed")); ldt=float(c.number_input("Langevin step",0.0005,0.05,0.005,format="%.4f",key="pl_lat_ldt"))
        # Sample every fixed stochastic step so FFT sees a uniform grid.
        samples=min(10000,max(128,int(round(duration/ldt))+1))
        ldt=duration/max(samples-1,1)
    return LatticeConfig(nx=nx,ny=ny,layers=layers,stacking=stacking,strain_x=strain,k_in=k_in,alpha=alpha,k_inter=k_inter,damping=damping,interlayer_damping=inter_damping,defect_mode=defect,drive_mode=drive,drive_amplitude=amp,drive_frequency=freq,stochastic_mode=stochastic,temperature_reduced=temp,seed=seed,duration=duration,samples=samples,langevin_dt=ldt)


def _render_result(st: Any, result: Mapping[str, Any]) -> None:
    model=result["model"]; t=np.asarray(result["time"]); a=result["analysis"]; u=np.asarray(a["displacement"]); summary=result_summary(result)
    m1,m2,m3,m4=st.columns(4); m1.metric("Atoms",summary["atoms"]); m2.metric("Coordination",f"{summary['coordination_min']}–{summary['coordination_max']}"); m3.metric("Equilibrium residual",f"{summary['equilibrium_force_residual']:.2e}"); m4.metric("Pair-force imbalance",f"{summary['internal_force_imbalance']:.2e}")
    try:
        import plotly.graph_objects as go
        fig=go.Figure(); pos=model.positions
        for layer in range(model.config.layers):
            mask=model.layer_ids==layer; fig.add_trace(go.Scatter3d(x=pos[mask,0],y=pos[mask,1],z=np.full(np.count_nonzero(mask),layer*model.config.layer_spacing),mode="markers",name=f"Layer {layer+1}"))
        fig.update_layout(title="Periodic honeycomb reference geometry",scene=dict(xaxis_title="x",yaxis_title="y",zaxis_title="layer z (display only)",aspectmode="data"),height=480); st.plotly_chart(fig,width="stretch")
        fig2=go.Figure()
        for layer in range(model.config.layers): fig2.add_trace(go.Scatter(x=t,y=a["layer_kinetic_energy"][:,layer],mode="lines",name=f"Layer {layer+1}"))
        fig2.update_layout(title="Layer-resolved kinetic energy",xaxis_title="time",yaxis_title="reduced energy"); st.plotly_chart(fig2,width="stretch")
        spec=a["spectrum"]; fig3=go.Figure(go.Scatter(x=spec["frequency"],y=spec["amplitude"],mode="lines")); fig3.update_layout(title="Local vibration spectrum (not phonon dispersion)",xaxis_title="frequency",yaxis_title="windowed amplitude"); st.plotly_chart(fig3,width="stretch")
        fig4=go.Figure(); fig4.add_trace(go.Scatter(x=t,y=a["injected_work"],name="Injected work")); fig4.add_trace(go.Scatter(x=t,y=a["bottom_interlayer_work"],name="Bottom interlayer work")); fig4.update_layout(title="Work-flow diagnostics",xaxis_title="time",yaxis_title="reduced work"); st.plotly_chart(fig4,width="stretch")
    except Exception as exc: st.caption(f"Plotly rendering unavailable: {exc}")
    with st.expander("Structured summary",expanded=False): st.json(summary)


def _jobs(compute: Any) -> list[dict[str,Any]]:
    out=[]
    for row in compute.list_jobs(limit=100,profile="oscillation-integration"):
        if str((row.get("runner_config") or {}).get("model_variant") or "")==MODEL_VARIANT: out.append(row)
    return out


def _platform(st: Any, cfg: LatticeConfig) -> None:
    with st.expander("Experiment / Compute / Project workflow",expanded=False):
        try:
            import physical_lab_compute_engine as compute
            import physical_lab_project_kernel as project
        except Exception as exc: st.warning(f"Platform modules unavailable: {exc}"); return
        preset=st.selectbox("Verification campaign",["compact","standard"],key="pl_lat_campaign")
        manifest=build_lattice_manifest(cfg,preset=preset,source_commit=os.environ.get("PHYSICAL_LAB_SOURCE_COMMIT") or None); st.session_state["pl_lattice_manifest"]=manifest
        st.write({"model":MODEL_TITLE,"experiment_sha256":manifest["experiment_sha256"],"preset":preset})
        active=st.session_state.get("pl_active_project_path")
        a,b,c=st.columns(3)
        if a.button("Register experiment",disabled=not active,width="stretch",key="pl_lat_register"): project.register_experiment(str(active),manifest); st.success("Experiment registered.")
        if b.button("Queue verification",type="primary",width="stretch",key="pl_lat_queue"): compute.submit_job(manifest,runner="model-campaign",runner_config={"profile":"oscillation-integration","preset":preset,"model_variant":MODEL_VARIANT},priority=70); st.success("Verification queued."); st.rerun()
        if c.button("Sync project jobs",disabled=not active,width="stretch",key="pl_lat_sync"): st.success(str(project.sync_compute_jobs(str(active))))
        compute.start_queued_jobs(max_parallel=1); jobs=_jobs(compute)
        if not jobs: st.caption("No lattice Compute Engine jobs yet."); return
        import pandas as pd
        st.dataframe(pd.DataFrame([{"id":r.get("id"),"status":r.get("status"),"progress":r.get("progress"),"stage":r.get("stage")} for r in jobs[:12]]),hide_index=True,width="stretch")
        selected=st.selectbox("Inspect lattice job",[str(r["id"]) for r in jobs],key="pl_lat_job"); record=compute.read_job(selected) or {}; x,y,z=st.columns(3)
        if x.button("Refresh",width="stretch",key="pl_lat_refresh"): st.rerun()
        if y.button("Cancel",disabled=record.get("status") not in {"queued","running"},width="stretch",key="pl_lat_cancel"): compute.cancel_job(selected); st.rerun()
        if z.button("Requeue",disabled=record.get("status") not in {"failed","interrupted","cancelled"},width="stretch",key="pl_lat_requeue"): compute.requeue_job(selected); st.rerun()
        result=compute.read_result(selected)
        if result and isinstance(result.get("result"),Mapping):
            campaign=result["result"]; st.session_state["pl_lattice_campaign_result"]=campaign; st.metric("Campaign screening",str((campaign.get("screening") or {}).get("status") or "REVIEW")); st.json(campaign.get("metrics") or {})
            st.download_button("Download lattice V&V report",render_report_markdown(manifest,campaign),file_name="physical-lab-honeycomb-lattice-report.md",mime="text/markdown",key="pl_lat_report")


def render_lattice_workspace(st: Any, profile: str) -> None:
    if profile!="oscillation-integration": return
    st.markdown("---"); st.markdown(f"## Physical Lab · {MODEL_TITLE}"); st.caption("Reduced-unit periodic multilayer honeycomb lattice dynamics. Correct equilibrium bond lengths, pairwise force symmetry, finite-cell normal modes, deterministic DOP853 and optional seeded Langevin dynamics. Not an ab-initio graphene potential.")
    cfg=_config(st)
    a,b=st.columns([2,1])
    if a.button("Run interactive lattice model",type="primary",width="stretch",key="pl_lat_run"):
        with st.spinner("Integrating lattice dynamics..."): result=integrate_case(cfg)
        st.session_state["pl_lattice_result"]=result; st.session_state["pl_lattice_result_summary"]=result_summary(result); st.success("Lattice integration completed.")
    if b.button("Normal-mode audit",width="stretch",key="pl_lat_modes"):
        modes=normal_modes(build_lattice(cfg)); st.session_state["pl_lattice_modes"]={"zero_mode_count":modes["zero_mode_count"],"negative_mode_count":modes["negative_eigenvalue_count"],"first_positive_frequencies":modes["first_positive_frequencies"][:16],"boundary":modes["boundary"]}
    result=st.session_state.get("pl_lattice_result")
    if isinstance(result,Mapping): _render_result(st,result)
    modes=st.session_state.get("pl_lattice_modes")
    if isinstance(modes,Mapping): st.json(modes)
    _platform(st,cfg)
