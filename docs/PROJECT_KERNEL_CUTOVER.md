# Physical Lab Project Kernel Cutover

Physical Lab historically had two project stores: a Rust desktop `workspaces/*.physlab` surface and the newer canonical Python `projects/*.physlab` Project/Experiment/Evidence Kernel.

This cutover changes **new desktop project storage** to canonical `projects/*.physlab` while preserving the mature Data Bridge, Run, Pipeline and Campaign commands through a temporary compatibility handle.

## Safety boundary

- New projects use canonical fields: `project_id`, `project_version`, `created_at`, `updated_at`, `experiments`, `jobs`, `results`.
- Historical `workspaces/*.physlab` source directories remain untouched and are handled by the one-way migration bridge.
- Desktop operational directories (`datasets`, `runs`, `figures`, `exports`, `pipelines`, `campaigns`) may live inside a canonical project, but their contents are **not** automatically canonical Experiment Kernel or Compute Engine evidence.
- A compatibility symlink under `workspaces/` routes mature Rust commands to the canonical directory during the transition. The physical data remains under `projects/`.
- The compatibility layer never converts a legacy or shell run into a scientific verification/validation claim.

## Follow-on

The remaining transition step is to make measurement imports write the canonical Measurement Registry directly and then retire the compatibility symlink once all Rust research commands use the canonical resolver internally.
