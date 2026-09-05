# Physical Lab Project Kernel Cutover

This branch is moving the desktop shell from legacy `workspaces/*.physlab` creation to the canonical `projects/*.physlab` Project Kernel.

Safety rules:

- New desktop projects must use the canonical `physical-lab-project-v1` document shape (`project_id`, `project_version`, snake_case timestamps, experiment/job/result indexes).
- Legacy `workspaces/*.physlab` sources remain readable during the compatibility period and are never rewritten in place.
- Operational desktop directories such as `datasets`, `runs`, `pipelines`, and `campaigns` may coexist inside a canonical `.physlab` directory; their presence does not make their contents canonical experiment/result evidence.
- Legacy run/campaign/pipeline payloads are not silently promoted to canonical Experiment Kernel or Compute Engine records.
- The migration bridge remains the source-preserving path for historical workspaces.
