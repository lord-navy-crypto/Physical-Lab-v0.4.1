# Kerr Geodesic Dynamics · Platform Workflow

Physical Lab keeps **Kerr Geodesic Dynamics** inside the existing **Nonlinear Dynamics & Chaos** profile, but treats it as its own scientific model variant: `kerr-geodesic`.

This document describes the platform layer above the numerical geodesic core. The purpose is reproducibility, persistent computation, V&V, bounded sensitivity analysis and project provenance. It does not turn the standard Kerr geodesic problem into a generic chaos claim.

## 1. Scientific boundary

The numerical core uses Boyer–Lindquist coordinates and geometric units

`G = c = M = 1`.

For the unperturbed Kerr metric, geodesic motion is integrable through the conserved energy `E`, axial angular momentum `Lz` and Carter constant `Q`. Physical Lab therefore uses Poincaré-style sections, orbit comparisons and stability diagnostics as **relativistic-dynamics / orbital-structure diagnostics**, not as automatic evidence of chaos.

Two geodesic classes are supported by this workflow:

- bound timelike geodesics, parameterized by periapsis, apoapsis and inclination;
- spherical null geodesics satisfying `R(r0)=0` and `dR/dr(r0)=0`.

The spherical-photon radial-instability exponent is a local instability diagnostic derived from radial-potential curvature. It is not presented as a generic phase-space maximum Lyapunov exponent for Kerr geodesics.

## 2. Layering

The model is deliberately split into layers:

```text
Kerr numerical core
    ↓
Interactive Kerr workspace
    ↓
Kerr Experiment adapter
    ↓
Persistent Compute Engine worker
    ↓
Verification / sensitivity campaign
    ↓
.physlab Project index
    ↓
Report / provenance / Local AI explanation
```

### Numerical core

`src-tauri/resources/ui/physical_lab_kerr_geodesics.py`

Owns the scientific equations, constants-of-motion solving, Carter–Mino integration, first-integral residuals and orbit diagnostics.

### Interactive workspace

`src-tauri/resources/ui/physical_lab_kerr_ui.py`

Supports exploratory single-orbit runs, massive/photon comparison, spin sweeps and solver-refinement views.

### Experiment / workflow adapter

`src-tauri/resources/ui/physical_lab_kerr_workflow.py`

Converts a valid `KerrOrbitConfig` into a `physical-lab-experiment-v1` manifest and provides the bounded Kerr verification campaign.

### Persistent worker UI

`src-tauri/resources/ui/physical_lab_kerr_platform_ui.py`

Registers the experiment, queues the worker-native campaign, exposes persistent job state, cancel/retry, project synchronization and report export.

## 3. Experiment identity

A Kerr experiment remains a standard Experiment Kernel manifest:

- schema: `physical-lab-experiment-v1`
- profile: `nonlinear-chaos`
- model title: `Kerr Geodesic Dynamics`
- model variant: `kerr-geodesic`
- model domain: `general-relativity-geodesic-dynamics`
- execution mode: `kerr-verification-campaign`

The stable experiment fingerprint includes scientific parameters, execution settings, requirements, uncertainty declaration and selected provenance fields. Runtime timestamps do not define scientific identity.

Typical parameter fields include:

- `spin_a_over_M`
- `inclination_deg`
- `particle_type`
- `periapsis_r_over_M`
- `apoapsis_r_over_M`
- `mino_time_span`
- `samples`
- `rtol`
- `atol`
- `horizon_guard_M`

Changing a scientific parameter changes the experiment fingerprint.

## 4. Worker-native Compute Engine execution

Physical Lab does not add an unrestricted Python runner for Kerr. The existing allow-listed `model-campaign` runner is retained.

The worker checks the manifest/runner configuration for the explicit model variant:

`kerr-geodesic`

Only that recognized variant is dispatched to the Kerr workflow. A normal `nonlinear-chaos` model campaign continues to run the established Duffing campaign.

This preserves the Compute Engine security and lifecycle contract:

- child process owns the scientific run;
- Streamlit reruns do not own computation lifetime;
- bounded local concurrency;
- durable `job.json` state;
- stage checkpoints;
- `worker.log`;
- cancellation;
- interrupted-job recovery;
- retry/requeue;
- persisted `result.json`.

Kerr-specific checkpoint progression is approximately:

```text
manifest-validated
→ kerr-base-run
→ kerr-refinement
→ kerr-sensitivity
→ kerr-spin-sweep
→ campaign-computed
→ result-persisted
→ complete
```

## 5. Verification metrics

The Kerr campaign reports model-specific metrics rather than publishing them into the generic Duffing scorecard.

### First-integral residual

The integrated solution is checked against the Carter first integrals:

`p_r^2 = R(r)`

`p_theta^2 = Theta(theta)`

The normalized maximum residual is a numerical-consistency diagnostic.

### Turning / spherical constraint residual

For a massive bound orbit, Physical Lab checks the requested radial turning conditions and polar turning condition:

- `R(r_p) ≈ 0`
- `R(r_a) ≈ 0`
- `Theta(theta_min) ≈ 0`

For a spherical photon orbit it checks:

- `R(r0) ≈ 0`
- `R'(r0) ≈ 0`
- `Theta(theta_min) ≈ 0`

### Solver-refinement response

A loose/tight integration pair compares stable observables such as radial bounds and mean azimuthal Mino-time rate. Physical Lab does not demand pointwise long-time trajectory identity as a convergence criterion.

### Horizon margin

The minimum radial coordinate is compared with the outer horizon radius `r+`. The signed distance is reported in units of `M`.

## 6. PASS / REVIEW screening

Default computational screening thresholds are:

| Metric | Default screening requirement |
|---|---:|
| first-integral residual | `<= 1e-6` |
| turning/spherical constraint residual | `<= 1e-8` |
| solver-refinement relative change | `<= 5e-4` |
| minimum horizon margin | `>= 0.10 M` |

These are editable **Physical Lab computational screening defaults**. They are not general-relativity standards, observatory requirements, certification limits or experimental-validation criteria.

A PASS means only that all configured computational screening checks passed. Otherwise the campaign reports REVIEW with signed margins.

## 7. Deterministic tolerance envelope

The compact and standard campaigns perturb nearby model inputs in a bounded way.

Possible perturbations include:

- spin `a/M`;
- inclination;
- periapsis and apoapsis for massive bound orbits.

The response of stable observables is summarized as local relative change.

This is intentionally called a **deterministic local tolerance envelope**. It is not:

- a probability distribution;
- Monte Carlo manufacturing yield;
- a confidence interval;
- measurement uncertainty;
- astrophysical posterior inference.

A probabilistic UQ claim would require an explicitly justified distribution/model for uncertain inputs and an appropriate propagation method.

## 8. Spin-response characterization

Each campaign includes a bounded spin sweep at fixed geodesic class and inclination. The sweep is useful for comparing quantities such as:

- radial bounds;
- mean azimuthal Mino-time rate;
- spherical-photon radial instability.

It is a parameter study, not an inferred black-hole spin measurement.

## 9. Optional physical mass scaling

The solver remains dimensionless regardless of whether the UI attaches a black-hole mass.

When a user provides a mass in solar masses, Physical Lab records only a presentation/provenance conversion:

- one geometric length `M = GM/c^2`;
- one geometric time `M = GM/c^3`.

The supplied solar mass does **not** change the dimensionless geodesic trajectory or constants of motion.

This separation is important because a dimensionless orbit can be rescaled to different physical black-hole masses without rerunning the geometric-unit equations.

## 10. .physlab Project integration

The Kerr workflow reuses the existing Project Kernel rather than creating a Kerr-specific storage tree.

A project may register the Kerr experiment manifest through the normal Experiment Kernel fingerprint. Matching Compute Engine jobs/results are then indexed by the existing project synchronization path.

The project remains an index/provenance layer:

```text
.physlab Project
→ Experiment manifest
→ Compute job
→ Persisted result
→ Report reference
```

Large trajectory arrays stay in their scientific/compute stores rather than being duplicated into project metadata.

## 11. Report output

A completed Kerr campaign can generate a Markdown verification report containing:

- experiment fingerprint;
- model assumptions;
- base constants and orbit summary;
- verification metrics;
- requirement limits;
- signed margins;
- PASS/REVIEW status;
- V&V/UQ boundary.

The report is a reproducibility and engineering-review artifact. It is not a publication claim and does not convert simulation into experiment.

## 12. Local AI boundary

Local AI may explain the structured Kerr context, including:

- `a/M` spin;
- inclination convention;
- `r/M` radial quantities;
- Carter constants;
- numerical tolerances;
- experiment fingerprint;
- campaign metrics and screening result;
- optional physical scale.

The local model remains advisory. It cannot apply parameter changes, execute arbitrary scientific code or override solver/project evidence.

## 13. Deterministic CI

`kerr_geodesic_validation.py` protects the numerical model itself.

`kerr_platform_workflow_validation.py` protects the platform contract by exercising:

- stable experiment identity;
- Kerr model metadata;
- physical scale conversion;
- PASS/REVIEW logic;
- the actual persistent worker specialization;
- checkpoint/result persistence;
- bounded compact campaign;
- report generation;
- Tauri packaging and facade wiring.

Together the tests separate two questions:

1. **Does the Kerr numerical model still satisfy its physics/numerical contracts?**
2. **Can Physical Lab still reproduce, queue, persist, review and package that model correctly?**

Both must remain true.
