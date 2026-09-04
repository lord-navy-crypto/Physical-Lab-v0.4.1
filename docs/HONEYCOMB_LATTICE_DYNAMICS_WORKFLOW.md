# Multilayer Honeycomb Lattice Dynamics · Physical Lab

## Purpose

This model rebuilds the earlier multilayer honeycomb vibration script as a bounded Physical Lab model inside **Oscillation & Numerical Integration**.

It is intentionally described as a **reduced-unit lattice-dynamics model**. It is not an ab-initio graphene calculation, not a calibrated empirical interatomic potential, and not experimental validation.

## Architecture

```text
interactive lattice parameters
        ↓
LatticeConfig
        ↓
periodic honeycomb geometry + pair topology
        ↓
DOP853 deterministic dynamics
or seeded fixed-step Langevin dynamics
        ↓
finite-cell normal modes + local spectrum + work diagnostics
        ↓
physical-lab-experiment-v1
        ↓
Persistent Compute Engine
        ↓
verification campaign
        ↓
.physlab Project / report / diagnostics
```

## Scientific repairs from the standalone script

### Honeycomb geometry

The baseline uses nearest-neighbor bond length `d=1` in reduced units with primitive vectors

```text
a1 = (sqrt(3)d, 0)
a2 = (sqrt(3)d/2, 3d/2)
```

and a two-site basis. Periodic minimum-image distances are evaluated in the oblique simulation cell. For supported `nx, ny >= 2`, each site has exactly three in-plane nearest neighbors.

This replaces the inconsistent combination in the earlier script where the generated A/B separation and `nn_dist = a0*sqrt(3)/3` used different conventions.

### Equilibrium bond force

The in-plane potential is written in bond extension `x = r-r0`:

```text
U = 1/2 k x^2 + 1/4 alpha x^4
```

so the reference lattice is an actual force equilibrium. The earlier `-k*r-alpha*r^3` form exerted force even at the intended reference geometry.

### Pair-force symmetry

Every conservative in-plane and interlayer interaction is accumulated as an equal-and-opposite pair contribution. The verification campaign explicitly checks net internal-force imbalance under a small deterministic displacement.

### Interlayer coupling

Adjacent layers use a registry-matched **in-plane shear spring proxy**. It is not labelled van der Waals friction and it is not an ab-initio interlayer potential. `AA`, `ABA`, and `ABC` are geometric registry proxies used to compare finite-cell response.

### Defects

The production model does not call a one-direction external force a crystal defect. Supported defect proxies modify model structure instead:

- mass substitution,
- weakened local bonds,
- weakened line of bonds.

### Noise and thermal mode

Random numbers are never sampled inside an adaptive `solve_ivp` RHS. Deterministic runs use DOP853. Optional thermalized runs use a fixed-step, seeded Euler–Maruyama reduced-unit Langevin process tied to the local viscous damping coefficient.

A single seeded trajectory is a stochastic process realization. It is not probabilistic UQ over material parameters.

### Frequency analysis

DOP853 returns values on a uniform `t_eval` grid before spectral analysis. The signal is mean-removed, multiplied by a Hann window, and processed with `rFFT`.

The result is deliberately called a **local vibration spectrum**. It is not a q-resolved phonon dispersion.

### Finite-cell normal modes

The harmonic dynamical matrix is assembled from the linearized pair springs and mass weighted before symmetric eigensolution. A free periodic cell should retain two global in-plane translation zero modes. Negative eigenvalues beyond tolerance are treated as a REVIEW condition.

This produces finite-cell normal modes. Future q-resolved work should build a Bloch dynamical matrix or `S(q,ω)` workflow rather than relabel the local FFT.

## Energy and work language

The earlier `layer0 kinetic energy / layer2 kinetic energy` quantity is not promoted as energy-transmission efficiency. Physical Lab instead reports:

- layer-resolved kinetic energy,
- total kinetic + pair-potential energy,
- cumulative external injected work,
- cumulative interlayer work on the bottom layer,
- signed `bottom interlayer work / injected work` when the denominator is meaningful.

The ratio is not constrained to 0–100% and is not a certified efficiency.

## Verification campaign

The persistent worker campaign checks:

1. honeycomb coordination error,
2. equilibrium force residual,
3. internal pair-force imbalance,
4. conservative energy drift after a real initial displacement,
5. DOP853 refinement sensitivity,
6. negative harmonic-mode eigenvalues,
7. expected two translation zero modes,
8. bounded AA/ABA/ABC mode characterization,
9. bounded defect-mode characterization.

`PASS / REVIEW` is an editable computational screening layer. It is not a statement about experimental graphene, thermal conductivity, manufacturing readiness, or material certification.

## Original controls mapped into the new model

| Earlier concept | Physical Lab treatment |
|---|---|
| `STACK_MODE` | AA / ABA / ABC geometric registry proxy |
| cubic in-plane force | equilibrium-length anharmonic pair spring |
| cubic interlayer force | registry-matched interlayer shear proxy |
| viscous damping | retained as explicit dissipative model term |
| `van der Waals friction` | renamed pairwise interlayer viscous coupling |
| point/line defect force | replaced by mass/bond structural defect proxies |
| sinusoidal / pulse / beat | preserved; chirp also available |
| Gaussian RHS noise | replaced by seeded fixed-step Langevin mode |
| electric-field term `mE` | renamed optional uniform reduced-unit body force |
| `-eps * layer_id` strain | replaced by explicit affine reference-geometry strain |
| single-site FFT called phonon spectrum | local vibration spectrum |
| kinetic-energy ratio called efficiency | work and layer-energy diagnostics |

## Next scientific upgrades

High-value future extensions are:

- Bloch dynamical matrix and `ω(q)` dispersion,
- density of states,
- velocity-autocorrelation spectrum,
- `S(q,ω)` from space-time trajectories,
- calibrated force constants and physical unit system,
- out-of-plane flexural degrees of freedom,
- richer interlayer registry potentials,
- Green–Kubo / non-equilibrium heat-flow models,
- measurement/digital-twin mapping once real vibration data and calibration metadata exist.
