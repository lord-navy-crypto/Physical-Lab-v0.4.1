# Multilayer Honeycomb Lattice · Bloch Phonon Analysis

## Purpose

Physical Lab's `Multilayer Honeycomb Lattice Dynamics` model now contains two deliberately separate analysis paths:

```text
time-domain reduced lattice dynamics
    DOP853 / seeded Langevin
    local displacement / work / energy / local FFT

and

periodic harmonic bulk reference
    Bloch dynamical matrix D(q)
    Γ → K → M → Γ dispersion
    Brillouin-zone sampled DOS
    mode participation / polarization
```

Keeping these paths separate is intentional. A local time-series FFT is not a phonon dispersion, while a harmonic Bloch eigenproblem does not include the finite-amplitude anharmonic, damping, drive, stochastic, or localized-defect effects used by the time-domain model.

## Scientific boundary

The Bloch result is a **reduced-unit harmonic lattice model**. It is not:

- density-functional theory,
- an ab-initio graphene calculation,
- an empirical carbon potential such as Tersoff/AIREBO/REBO,
- a calibrated multilayer van-der-Waals force-constant model,
- experimental validation,
- a prediction of real graphene frequencies in THz.

The in-plane model is the same nearest-neighbor central harmonic spring baseline used by the verified lattice core. The interlayer term is the same registry-matched isotropic shear proxy used by the finite-cell model.

## Primitive cell and degrees of freedom

Each layer contains two honeycomb basis sites, A and B, each with in-plane x/y displacement. Therefore a model with `L` layers has

```text
4L Bloch degrees of freedom
4L phonon branches
```

The Bloch matrix is mass weighted and Hermitian.

For a spring connecting basis site `α` in the reference cell and `β` in lattice-translated cell `R`, the harmonic block contributes

```text
D_αα += K / m_α
D_ββ += K / m_β
D_αβ -= K exp(i q·R) / sqrt(m_α m_β)
D_βα  = D_αβ†
```

The current reduced model uses one common site mass, so the mass factors simplify.

## In-plane honeycomb benchmark

For an unstrained monolayer with nearest-neighbor central harmonic spring constant `k` and mass `m`, the three bond unit vectors satisfy

```text
Σ n_j n_j^T = 3/2 I.
```

At Γ the analytic eigenvalues are therefore

```text
0, 0, 3k/m, 3k/m.
```

The two zero eigenvalues are the rigid in-plane translations. The two optical frequencies are

```text
f_opt = sqrt(3k/m) / (2π)
```

in cycles per reduced time. This is a deterministic CI benchmark.

## Reciprocal lattice and reference path

The reciprocal basis is generated from the strained primitive vectors using

```text
B = 2π A^{-T}.
```

For the unstrained hexagonal reference, Physical Lab uses

```text
Γ = (0, 0)
K = (2 b1 + b2) / 3
M = (b1 + b2) / 2
```

and renders

```text
Γ → K → M → Γ.
```

Each path endpoint is included exactly once, so the plotted K and M ticks correspond to actual solved q points rather than nearby interpolation samples.

When affine strain is non-zero, the same fractional reciprocal coordinates are retained as **reference points**. The crystal no longer has the exact unstrained hexagonal symmetry, so the UI explicitly warns that K/M need not remain true symmetry points.

## Harmonic dispersion

For every q point, Physical Lab solves

```text
D(q) e_n(q) = λ_n(q) e_n(q)
```

and reports

```text
f_n(q) = sqrt(max(λ_n, 0)) / (2π).
```

Tiny negative eigenvalues within floating-point tolerance are treated as numerical roundoff for the plotted frequency, while a separate negative-eigenvalue metric remains available for verification.

The campaign verifies:

- Bloch Hermiticity residual,
- maximum negative-eigenvalue magnitude,
- Γ translation-zero-mode count,
- the analytic monolayer Γ benchmark.

## Phonon density of states

The DOS calculation uniformly samples a reciprocal primitive-cell parallelogram:

```text
q = (i/N) b1 + (j/N) b2
```

and accumulates all branch frequencies into a normalized histogram.

The reported histogram is normalized so that

```text
∫ g(f) df ≈ 1.
```

The campaign includes `dos_normalization_error_max` as a deterministic numerical check.

This is the DOS of the reduced harmonic model, not a real-material vibrational DOS.

## Mode character

At Γ, K, or M, a user may select a branch and inspect:

- frequency,
- eigenvalue,
- layer participation,
- A/B sublattice participation,
- longitudinal fraction relative to q when q ≠ 0.

The absolute complex eigenvector phase is gauge dependent. Participation magnitudes are the appropriate gauge-invariant quantities exposed by the UI.

## Defects and Bloch periodicity

Localized defects are intentionally **not** inserted into the primitive-cell Bloch matrix.

The workflow therefore separates:

```text
pristine periodic bulk
    → Bloch dispersion / DOS

localized defect model
    → finite supercell normal modes / time-domain dynamics
```

This avoids the false claim that a single local defect can be represented by a pristine primitive-cell Bloch calculation.

A future supercell band-folding / unfolding system could make defect-band calculations possible, but that is not claimed in this version.

## Anharmonicity and temperature

The cubic coefficients `alpha` and `beta_inter`, damping, external driving and Langevin temperature do not enter the harmonic Bloch matrix.

Therefore the current dispersion does **not** include:

- phonon-phonon interactions,
- temperature-dependent frequency renormalization,
- linewidths or lifetimes,
- thermal conductivity,
- anharmonic scattering rates.

These require a different physical layer and should not be inferred from the present harmonic result.

## Compute Engine workflow

The persistent lattice verification campaign now follows approximately:

```text
geometry audit
→ conservative time-domain baseline
→ solver refinement
→ finite-cell normal modes
→ Bloch dispersion + DOS
→ analytic Γ benchmark
→ time-domain characterization
→ stacking sweep
→ localized defect audit
→ PASS / REVIEW
```

The worker remains the existing allow-listed `model-campaign` runner. No arbitrary execution capability is added.

## PASS / REVIEW boundary

PASS means that configured computational screening requirements were met, including structural topology, equilibrium force residual, pair-force balance, conservative integration drift, refinement, finite-cell mode stability, Bloch Hermiticity, Γ benchmark and DOS normalization.

PASS does **not** mean that a real material has been experimentally validated, that the reduced interlayer coupling is quantitatively accurate, or that the frequencies correspond to graphene measurements.

## Next scientific expansion

The natural next layer is a time/space correlation analysis, kept separate from the harmonic Bloch eigenproblem:

```text
velocity autocorrelation function (VACF)
→ vibrational spectral density

u(r,t) or v(r,t)
→ spatial + temporal Fourier transform
→ S(q,ω)
```

After that, higher-fidelity force models or imported force-constant matrices could be added with explicit provenance and model-to-model comparison instead of silently replacing the reduced baseline.
