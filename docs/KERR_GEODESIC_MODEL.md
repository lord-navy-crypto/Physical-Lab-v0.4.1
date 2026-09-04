# Kerr Geodesic Dynamics Model

Physical Lab now includes a relativistic-dynamics model inside the **Nonlinear Dynamics & Chaos** profile. The placement is based on shared numerical-dynamics tools (phase space, Poincaré-style sections, stability and solver diagnostics), not on a claim that the unperturbed Kerr geodesic problem is generically chaotic.

## Scientific scope

The implementation uses Boyer–Lindquist coordinates and geometric units

`G = c = M = 1`.

For a test particle or photon the separated Carter–Mino equations are written in terms of

- specific energy `E`,
- axial angular momentum `Lz`,
- Carter constant `Q`,
- radial potential `R(r)`,
- polar potential `Theta(theta)`.

The model supports:

1. bound timelike geodesics specified by periapsis, apoapsis and inclination,
2. prograde spherical null geodesics satisfying `R(r0)=0` and `dR/dr(r0)=0`,
3. Carter–Mino time integration with RK45,
4. 3D oblate-coordinate trajectory views,
5. radial and polar phase portraits,
6. Poincaré-style periapsis sections,
7. black-hole spin sweeps,
8. first-integral residual checks,
9. loose/tight solver-refinement audits,
10. a local radial-instability exponent for spherical photon orbits.

## Why the old generic MLE was replaced

The standard Kerr geodesic problem is integrable because the Hamilton–Jacobi equation separates and admits the Carter constant. A finite-time Euclidean shadow-distance calculation across mixed coordinates can therefore be misleading as a generic chaos metric.

Physical Lab instead reports a **local spherical-photon radial instability exponent** obtained from the curvature of the radial potential around the spherical orbit. This is explicitly labeled as a radial instability diagnostic, not as a generic maximal Lyapunov exponent for all Kerr geodesics.

## Spherical photon root strategy

The earlier standalone implementation solved the spherical-photon conditions with a free two-variable nonlinear root. That approach can become sensitive to initial guesses at high spin.

The Physical Lab implementation uses the analytic spherical-null constants `xi(r)=Lz/E` and `eta(r)=Q/E^2`, then solves the inclination-compatibility condition in one radial variable. A bounded two-variable root remains only as a fallback.

The deterministic test suite explicitly checks the prograde branch at `a/M=0.9`.

## Numerical verification

The model does not equate successful integration with physical validation. It reports numerical evidence including:

- radial first-integral residual `|p_r^2 - R|`,
- polar first-integral residual `|p_theta^2 - Theta|`,
- combined maximum residual,
- loose/tight solver comparison,
- horizon-guard termination status,
- function-evaluation count.

The default `1e-6` residual threshold is an editable numerical screening target, not a GR code-certification standard.

## Visualization boundary

The 3D plot maps Boyer–Lindquist coordinates to an oblate-coordinate visualization. It is useful for comparing orbit geometry but is **not** a Euclidean embedding of Kerr spatial geometry.

## Excluded physics

This first version intentionally excludes:

- gravitational self-force,
- radiation reaction / inspiral,
- accretion-flow dynamics,
- plasma dispersion or refraction,
- perturbed or non-Kerr metrics,
- gravitational-wave waveform generation,
- ray tracing to a distant camera or detector.

These are possible later fidelity layers and should not be implied by the current model.

## Platform integration

The workspace is rendered only for the `nonlinear-chaos` profile and is connected to:

- Physical Lab session/result state,
- `.physlab` project capture through existing project infrastructure,
- the unified Run & Diagnostics Log,
- Tauri resource packaging,
- Source Integrity deterministic validation.

Run diagnostics store bounded status/residual information rather than full trajectory payloads.

## Reference literature

The implementation follows the standard separated Kerr-geodesic structure used in the literature, including:

- B. Carter, separability and the Carter constant,
- W. Schmidt, *Celestial mechanics in Kerr spacetime* (2002), arXiv:gr-qc/0202090,
- R. Fujita and W. Hikida, analytic solutions and Mino-time treatment of bound Kerr geodesics,
- E. Teo, work on spherical photon and spherical timelike Kerr orbits.

The references define the physical model; Physical Lab's contribution here is the verified numerical implementation, interactive comparison workflow, diagnostic boundaries and integration into the larger computational-physics platform.
