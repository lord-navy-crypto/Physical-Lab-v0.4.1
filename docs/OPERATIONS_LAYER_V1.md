# Physical Lab Operations Layer v1

## Purpose

The Operations Layer connects Physical Lab's project workflow to Industrial & Operations Engineering by treating engineering work as explicit tasks competing for finite resources over time.

The project chain becomes:

`Physics / Measurement → Evidence → Engineering Decision → Operations Plan → Queue / Capacity Metrics → Human Planning Judgment`

The layer is intentionally transparent. It simulates declared non-preemptive dispatch rules and reports their consequences; it does not claim a globally optimal schedule.

## IOE connection

University of Michigan Industrial & Operations Engineering describes operations research and analytics as methods for describing, predicting, and optimizing system performance using mathematics, statistics, and computation. Its stated topics include decision analysis, optimization, queueing theory, simulation, stochastic systems, and scheduling. Michigan IOE also describes combinatorial optimization as covering applications such as scheduling.

Those ideas map naturally to Physical Lab:

| Physical Lab object | Operations / IOE interpretation |
| --- | --- |
| Solver/runtime slot | finite service capacity |
| Instrument | constrained engineering resource |
| Human reviewer | constrained human-system resource |
| Experiment / simulation / measurement / analysis | task or job |
| Task duration | service / processing time |
| Release time | availability / arrival constraint |
| Dependencies | precedence constraints |
| Priority | declared dispatch preference |
| Campaign `maxParallel` | capacity / concurrency constraint |
| Waiting time | queue delay |
| Flow time | time in system |
| Makespan | completion horizon |
| Resource utilization | busy capacity / available capacity |

## v1 model

An operations plan contains:

1. **Resources** with explicit integer capacities.
2. **Tasks** with duration, release time, priority, resource requirements, and dependencies.
3. **Acyclic precedence**; cycles are rejected.
4. **Capacity guards**; a task cannot request more units than exist.
5. **Non-preemptive execution**; a started task holds its declared resources until completion.
6. **Explicit dispatch policy** selected by the reviewer.

Supported policies:

- `priority_fifo` — higher declared priority first, then release/input order.
- `fifo` — release/input order.
- `shortest_processing_time` — shorter declared duration first, then priority/order.

## Reported metrics

For every task:

- eligible time;
- start and finish time;
- waiting time after it becomes eligible;
- flow time from release to completion;
- allocated resources;
- dependencies.

For the plan:

- makespan;
- total and average waiting time;
- average flow time;
- per-resource utilization.

The policy comparison reports these quantities for every supported policy and intentionally contains no `recommended_policy` or `optimal_policy` field.

## Why no automatic best policy

Operations problems are multi-objective. A dispatch policy may reduce average queue waiting while delaying a high-priority prerequisite and increasing the overall completion horizon. Another policy may complete the critical downstream chain earlier while making independent jobs wait longer.

Physical Lab therefore reports the trade-off instead of collapsing it into one unexplained score. If later versions add optimization models, objective functions and weights must be explicit and the baseline policy comparison should remain visible.

## Relationship to Engineering Decision Layer

The Operations Layer is complementary to the Engineering Decision Layer:

- Decision Layer asks **which design alternatives remain feasible and nondominated?**
- Operations Layer asks **how does declared capacity and dispatch logic affect execution of engineering work?**

Operations metrics can later become evidence-backed decision metrics, for example:

- turnaround time;
- compute or instrument utilization;
- experiment throughput;
- queue delay;
- campaign completion time;
- reviewer workload.

This allows a design that performs well physically but requires excessive laboratory or compute capacity to be identified as an engineering trade-off rather than treated as a purely physics problem.

## Broader engineering relevance

### Engineering Physics

Repeated simulations, parameter scans, measurement campaigns, and verification runs can be modeled as capacity-constrained engineering work rather than independent scripts.

### Mechanical / Electrical Engineering

Bench testing, solver runs, design reviews, calibration, instrumentation, and prototype analysis often share limited equipment and personnel. The same task/resource model applies.

### Systems Engineering

Precedence, resource availability, technical reviews, test activities, and analysis milestones are part of the system lifecycle and can be represented in one project-local operations model.

### Manufacturing / Quality

Process steps, inspection, test stations, engineering review, and analysis capacity can be represented with the same queue/capacity vocabulary. Future Quality & Reliability work can feed statistical process and failure evidence into these plans.

## Next steps

Future Operations work should add, in bounded increments:

- resource-capacity scenarios;
- explicit campaign/job import adapters;
- stochastic processing-time scenarios;
- failure/downtime scenarios;
- queue distributions rather than only deterministic durations;
- user-declared objective functions for optimization;
- scheduling algorithms only when their assumptions and optimality conditions are explicit.

## Boundary

The Operations Layer is a planning/simulation model. Durations, priorities, release times, dependencies, and capacities are declarations, not measured facts unless separately supported by project evidence.

A tested policy performing better on one modeled metric does not prove that it is globally optimal, operationally safe, economically preferred, scientifically valid, or suitable under unmodeled uncertainty and human factors.

Physical Lab does not claim ABET accreditation, NASA process compliance, certification, or production qualification through this feature.

## Authoritative references

- University of Michigan IOE, Areas of Study: https://ioe.engin.umich.edu/undergraduate/major-in-ioe/areas-of-study/
- University of Michigan IOE, Operations Research and Analytics: https://ioe.engin.umich.edu/graduate/masters-programs/industrial-and-operations-engineering-masters/masters-program-curriculum/operations-research-analytics/
- University of Michigan IOE, Optimization methodology: https://ioe.engin.umich.edu/research/methodologies/optimization/
- University of Michigan IOE, Methodologies: https://ioe.engin.umich.edu/research/methodologies/
