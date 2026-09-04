# Physical Lab · New Model Refinement Studio

## Purpose

The Refinement Studio is a shared scientific-evidence layer for the recently promoted Physical Lab models:

- `kerr-geodesic`
- `sun-jupiter-saturn-dynamics`
- `multilayer-honeycomb-lattice`

It does **not** replace their numerical solvers or create a new top-level Lab. It adds bounded analyses that are useful only after the corresponding solver/model assumptions are already explicit.

## Shared architecture

```text
Model parameters
  -> authoritative model solver / Bloch eigensolver
  -> existing Experiment/Compute/Project evidence
  -> model-specific refinement analysis
  -> Model Evidence Contract
  -> Local AI structured context / Markdown report / .physlab report index
```

The Evidence Contract uses schema `physical-lab-model-evidence-v1` and records:

- model variant
- experiment fingerprint when available
- existing computational screening status
- model fidelity level
- supported claims
- unsupported claims
- uncertainty/sensitivity class
- refinement boundary
- evidence SHA-256

The evidence hash is a reproducibility identifier for the contract content. It is not a scientific-quality score.

## Kerr frequency structure

For a massive bound Kerr geodesic, the Studio estimates Mino-time frequencies from the existing turning-point diagnostics:

\[
\Omega_r = \frac{2\pi}{\Lambda_r},\qquad
\Omega_\theta = \frac{2\pi}{\Lambda_\theta},\qquad
\Omega_\phi \approx \left\langle \frac{d\phi}{d\lambda}\right\rangle.
\]

It reports ratios such as `Omega_r/Omega_theta` and the nearest rational with denominator <= 12. A small detuning means only that the finite-run frequency ratio is close to a low-order rational.

**Boundary:** standard unperturbed Kerr geodesics are integrable. Near-rational frequency ratios are not chaos evidence, self-force resonance capture, or astrophysical parameter inference.

## Sun-Jupiter-Saturn 5:2 structure

The rebuilt orbital model starts close to circular motion, where a longitude of periapsis can be numerically ill-defined. For that reason the first refinement uses a deliberately conservative geometric proxy:

\[
\psi = 2\lambda_J^{\rm projected} - 5\lambda_S^{\rm projected}.
\]

The Studio reports:

- wrapped and unwrapped phase
- finite-window phase drift
- a circular concentration statistic
- a beat-period proxy from the fitted drift
- mean/std of the osculating period ratio
- detrended eccentricity spectra

**Boundary:** this is a projected-longitude commensurability diagnostic, not a canonical disturbing-function resonant angle. Finite-window concentration does not prove resonance capture.

## Honeycomb phonon transport structure

The Studio differentiates the verified harmonic Bloch dispersion along the chosen `Gamma-K-M-Gamma` path:

\[
v_g^{\rm path}=\frac{d\omega}{dq_{\rm path}} = 2\pi\frac{df}{dq_{\rm path}}.
\]

It also reports adjacent-branch gap minima and a bounded affine-strain sweep.

High-symmetry path corners are excluded from the global group-velocity maximum because the path direction changes there.

**Boundary:** these are reduced-unit, path-projected harmonic quantities. They are not SI material velocities, ab-initio graphene results, or anharmonic thermal-transport coefficients. A small branch gap does not by itself prove an avoided-crossing mechanism.

## Project and Local AI integration

The Studio stores its structured refinement/evidence dictionaries under `pl_...` Streamlit session keys, so the existing read-only Local AI bridge can see them through its structured session-state context. The local model remains advisory and cannot change solver parameters.

A user may also save the generated Markdown evidence report into the active `.physlab/reports/` directory. The report is added to the project's report index with its own SHA-256 and `computational-refinement-evidence` classification.

## Validation

`scripts/new_model_refinement_validation.py` checks:

- Kerr frequency diagnostic boundaries and rational approximation
- deterministic Evidence Contract hashing
- Sun-Jupiter-Saturn finite-window phase proxy and spectral output
- honeycomb path group velocity and Bloch stability conditions
- packaging and engineering-facade wiring

These checks verify implementation consistency. They do not convert simulation evidence into experimental validation or certification.
