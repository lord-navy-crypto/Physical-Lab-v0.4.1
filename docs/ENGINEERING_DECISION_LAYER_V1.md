# Physical Lab Engineering Decision Layer v1

## Purpose

Physical Lab is an evidence-first engineering-physics workbench. The Engineering Decision Layer connects simulation, measurement, uncertainty, verification/validation evidence, and reproducibility records to explicit engineering alternatives and trade studies.

The intended chain is:

`Simulation / Measurement → Project Evidence → Engineering Metrics → Constraints → Pareto Trade Study → Evidence Freshness Review → Human Decision Record`

This is deliberately different from adding another solver or assigning a synthetic design score. Physical Lab preserves the distinction between scientific evidence, engineering analysis, and human engineering judgment.

## Why this connects Physics to Industrial & Operations Engineering

Industrial and Operations Engineering studies how data, mathematical models, uncertainty, resources, and constraints can support decisions about complex systems. The University of Michigan IOE curriculum explicitly groups optimization, stochastic processes, decision analysis, design of experiments, queueing, simulation, performance measurement, quality engineering, and statistical quality control among its core areas of study.

Physical Lab already produces many of the inputs those methods need:

| Physical Lab capability | IOE interpretation |
| --- | --- |
| Simulation campaigns and parameter sweeps | experiments / scenarios / alternatives |
| Monte Carlo and uncertainty records | stochastic-system evidence |
| Measurement registry and calibration evidence | data pedigree and quality evidence |
| Cross-checks and robustness metrics | model comparison and quality/reliability evidence |
| Campaign queues and `maxParallel` | operations/resource-capacity state |
| Reproducibility packages and source fingerprints | process traceability |
| Evidence snapshots and stale detection | decision-data freshness |
| Engineering Decision Layer | constraint screening, Pareto trade study, human decision record |

This makes the connection substantive rather than cosmetic: physics produces evidence about candidate systems, while IOE methods structure how alternatives, uncertainty, resources, and decisions are compared.

## Why this also connects to broader Engineering

ABET defines engineering design as an iterative decision-making process that develops requirements, generates multiple solutions, evaluates them against constraints, considers risks, and makes trade-offs. Its Industrial Engineering criteria include operations research, probability, statistics, engineering economy, productivity analysis, human factors, and design/analysis/improvement of integrated systems. Its Systems Engineering criteria explicitly include decision analysis, risk analysis, trade-off analysis, optimization, modeling, simulation, sensitivity analysis, and requirements engineering.

NASA systems-engineering guidance similarly treats trade studies as structured comparisons of alternative system designs against goals, requirements, constraints, measures, data sources, uncertainty/sensitivity, and selection rules.

The Engineering Decision Layer therefore uses a general engineering structure:

1. **Decision question** — what engineering choice is being examined?
2. **Alternatives** — at least two explicitly named candidate designs/processes/configurations.
3. **Metrics** — declared quantities with explicit `minimize` or `maximize` direction.
4. **Hard constraints** — declared `<=` or `>=` feasibility limits.
5. **Evidence references** — every alternative must point to current Physical Lab project evidence.
6. **Freshness** — changed or missing evidence blocks an alternative from current Pareto review.
7. **Pareto analysis** — no hidden weighting and no aggregate score; the system only identifies nondominated feasible alternatives under the declared metrics.
8. **Human decision record** — a reviewer records the selected alternative and rationale; Physical Lab stores the state and fingerprint but does not endorse the choice.

## Discipline-level examples

### Engineering Physics / Applied Physics

A radiation or magnet design can expose field quality, spectral properties, robustness, uncertainty, and resource/cost proxies as decision metrics. Physics establishes the behavior; the decision layer organizes design alternatives and constraints.

### Mechanical Engineering

Oscillation, modal, thermal, or nonlinear-system results can become mass, response, damping, stability, energy, manufacturability, or cost metrics. Trade studies compare configurations without replacing mechanical design judgment.

### Electrical / Computer Engineering

Signal quality, latency, power, error, stability, throughput, component count, and uncertainty can become declared metrics. Measurement and simulation evidence remain traceable to the same project.

### Industrial & Operations Engineering

Campaigns can be treated as experimental/scenario alternatives; later Operations Layer work can add capacity, queueing, resource utilization, schedule, and experiment-priority analysis. DOE/quality outputs can feed robustness and repeatability metrics into the decision study.

### Systems Engineering

The layer directly supports requirements/constraints, alternatives, trade-offs, sensitivity inputs, evidence traceability, and human decision rationale across a project lifecycle.

### Manufacturing / Quality Engineering

DOE, statistical variation, tolerance studies, yield/reliability proxies, process time, and resource cost can be compared alongside physics-based performance. The decision layer does not claim production qualification or process certification.

## What v1 computes

For each alternative, v1 reports one of:

- `FEASIBLE` — current evidence exists and all declared hard constraints pass.
- `INFEASIBLE` — current evidence exists but at least one declared hard constraint fails.
- `STALE` — one or more referenced evidence fingerprints changed after study registration.
- `EVIDENCE_MISSING` — one or more referenced project records no longer resolve.

Only `FEASIBLE` alternatives are eligible for the current Pareto frontier.

A feasible alternative is Pareto-dominated when another eligible alternative is no worse in every declared metric and strictly better in at least one. The frontier is therefore conditional on the declared metrics, constraints, and current evidence. It is not a universal optimum.

## Why Physical Lab does not default to weighted scoring

A weighted score can be useful when weights are legitimately elicited from decision owners, but automatically inventing weights would silently encode engineering preferences. Physical Lab v1 therefore defaults to constraint screening and Pareto dominance. Future weighting methods, if added, should require explicit user-supplied weights and retain the unweighted Pareto view.

## Next engineering layers

### Operations Layer

Planned direction:

- solver / instrument / reviewer resource capacities;
- campaign and experiment durations;
- precedence/dependency constraints;
- queue waiting time and utilization;
- explicit dispatch policies and scenario comparison;
- no unsupported claim of globally optimal scheduling.

### Quality & Reliability Layer

Planned direction:

- DOE result ingestion;
- repeatability/reproducibility summaries;
- sensitivity and robustness evidence;
- reliability/failure-event records;
- uncertainty-aware decision metrics;
- no automatic safety or certification verdict.

Together these extend the workbench from `physics result` to `engineering system decision` while retaining evidence provenance.

## Scientific and standards boundary

Physical Lab uses public engineering vocabulary as design guidance. It does **not** claim ABET accreditation, NASA process compliance, NASA-STD-7009 compliance, ASME compliance, certification, safety approval, or experimental validation merely because these records exist.

Constraint feasibility and Pareto dominance are mathematical properties of the user-declared study. The final engineering selection remains a human responsibility and may depend on requirements, risks, stakeholders, regulations, costs, safety considerations, or domain knowledge not represented in the project.

## Authoritative references

- University of Michigan Industrial & Operations Engineering, **Areas of study**: https://ioe.engin.umich.edu/undergraduate/major-in-ioe/areas-of-study/
- University of Michigan Industrial & Operations Engineering, **Stochastic systems**: https://ioe.engin.umich.edu/research/methodologies/stochastic-systems/
- ABET, **Criteria for Accrediting Engineering Programs, 2025–2026**: https://www.abet.org/accreditation/accreditation-criteria/criteria-for-accrediting-engineering-programs-2025-2026/
- NASA, **Systems Engineering Handbook – Appendix / Trade Study terminology**: https://www.nasa.gov/reference/system-engineering-handbook-appendix/
- NASA, **Systems Engineering Handbook**, Decision Analysis section: https://www.nasa.gov/wp-content/uploads/2018/09/nasa_systems_engineering_handbook_0.pdf
