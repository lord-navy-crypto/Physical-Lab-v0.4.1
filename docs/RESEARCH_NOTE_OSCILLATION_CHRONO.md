# Research Note — Oscillator versus PyChrono Cross-Check

## Question

For a force-free linear harmonic oscillator, how closely do (1) Physical Lab’s NumPy/SciPy RK4 integrator, (2) the analytic solution, and (3) a discovered Project Chrono / PyChrono runtime agree?

## Why this workflow matters

This is the first validated adapter path that *consumes* PyChrono from inside Physical Lab without making Chrono a hard dependency of the Oscillation Lab. It separates three layers:

1. Lab numerical correctness against an analytic reference
2. optional native-engine interop against the same analytic problem
3. dependency discovery (Runtime Center / `PHYSICAL_LAB_PYCHRONO_PYTHON`)

## Reproducible protocol

1. Ensure Runtime Center can discover a working PyChrono Conda/environment interpreter, or set `PHYSICAL_LAB_PYCHRONO_PYTHON`.
2. Open **Oscillation & Integration**.
3. In the Advanced Suite, open **PyChrono cross-check**.
4. Choose duration and dt for a force-free case (γ = 0, F0 = 0).
5. Run the cross-check and record:
   - Lab RK4 versus analytic max |Δu|
   - Lab versus PyChrono max/RMS |Δu| when Chrono is available
   - the exact PyChrono interpreter path and engine version string
6. Export/download the comparison figures and keep a Run Vault snapshot.
7. If Chrono is missing, still record the Lab-versus-analytic result; do not invent a Chrono residual.

## What counts as evidence

- Lab-versus-analytic error consistent with the chosen dt and RK4 order
- when Chrono is present, a documented residual with an explicit statement that link/constraint modelling differences can dominate
- provenance for the Chrono interpreter path

## What this note does *not* claim

Agreement on this 1-DOF spring test does not certify Chrono::Modal, multi-body mechanisms, or general nonlinear contact. Chrono::Modal remains an interchange/adapter boundary until a separately validated modal provider is wired.
