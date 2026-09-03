# Research Note — 2D Ising Finite-Size Scaling

## Question

How well do finite lattice Monte Carlo scans recover the known 2D zero-field Ising critical temperature and the thermodynamic-limit susceptibility scaling χ_max ∼ L^{γ/ν} with γ/ν = 7/4?

## Why this workflow matters

Finite-size scaling is the bridge between a practical Monte Carlo study and an exact Onsager result. It tests sampler quality, equilibration, temperature-grid design and scientific honesty about pre-asymptotic lattices.

## Reproducible protocol

1. Open **Ising Monte Carlo Lab** inside Physical Lab (Safe mode is sufficient; no fragile native engine is required).
2. Set dimension = 2 and external field h ≈ 0 so the Onsager references apply.
3. In the Advanced Suite, open **Finite-size scaling**.
4. Choose a lattice sequence (for example 8,12,16,24,32) and a temperature window that brackets the expected critical region near T_c ≈ 2.269.
5. Run the scan. Preserve:
   - T at χ peak for each L
   - χ peak versus L
   - observed γ/ν from the log–log fit
   - the exact Onsager T_c and the guide γ/ν = 1.75
6. Optionally inspect the order-parameter collapse guide using β/ν = 1/8.
7. Save a Run Vault snapshot and/or export the Content Validation Battery JSON.
8. If a Research Workspace project is active, keep the same parameters and seed notes in the project provenance.

## What counts as evidence

- χ-peak locations approaching Onsager T_c as L increases
- an observed γ/ν that moves toward 1.75 as lattices and budgets improve
- seed-stability or ESS diagnostics showing the peak is not pure Monte Carlo noise
- an explicit statement when the scan is still pre-asymptotic

## What this note does *not* claim

A single short lattice sequence does not prove the Onsager exponents. Disagreement with γ/ν = 1.75 usually means the scan is pre-asymptotic, under-equilibrated, or too coarsely gridded—not that the exact exponents are wrong.
