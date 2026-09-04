"""Multilayer honeycomb lattice dynamics core for Physical Lab.

Scientific boundary
-------------------
This is a reduced-unit lattice-dynamics model, not an ab-initio or empirically
calibrated graphene potential. The authoritative baseline uses a periodic
honeycomb bond network, equilibrium-length central anharmonic springs, and
pairwise registry-matched interlayer shear springs. Optional defects, damping,
drive, and seeded Langevin forcing are explicit model choices.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Mapping

import numpy as np
from scipy.integrate import solve_ivp

PROFILE = "oscillation-integration"
MODEL_VARIANT = "multilayer-honeycomb-lattice"
MODEL_TITLE = "Multilayer Honeycomb Lattice Dynamics"
MODEL_SCHEMA = "physical-lab-honeycomb-lattice-v1"


@dataclass(frozen=True)
class LatticeConfig:
    nx: int = 4
    ny: int = 4
    layers: int = 3
    stacking: str = "ABA"
    bond_length: float = 1.0
    layer_spacing: float = 0.35
    strain_x: float = 0.0
    mass: float = 1.0
    k_in: float = 10.0
    alpha: float = 2.0
    k_inter: float = 3.0
    beta_inter: float = 1.0
    damping: float = 0.02
    interlayer_damping: float = 0.01
    defect_mode: str = "none"
    defect_mass_multiplier: float = 2.0
    defect_bond_scale: float = 0.4
    drive_mode: str = "sin"
    drive_amplitude: float = 0.08
    drive_frequency: float = 1.0
    uniform_force_x: float = 0.0
    stochastic_mode: bool = False
    temperature_reduced: float = 0.0
    seed: int = 12345
    initial_displacement: float = 0.01
    duration: float = 20.0
    samples: int = 1200
    rtol: float = 1e-9
    atol: float = 1e-11
    max_step: float = 0.02
    langevin_dt: float = 0.005

    def validate(self) -> None:
        if not (2 <= int(self.nx) <= 10 and 2 <= int(self.ny) <= 10):
            raise ValueError("nx and ny must be between 2 and 10")
        if not (1 <= int(self.layers) <= 5):
            raise ValueError("layers must be between 1 and 5")
        if self.stacking not in {"AA", "ABA", "ABC"}:
            raise ValueError("stacking must be AA, ABA, or ABC")
        if self.defect_mode not in {"none", "mass", "weak-bond", "line-weak-bond"}:
            raise ValueError("unsupported defect_mode")
        if self.drive_mode not in {"none", "sin", "pulse", "beat", "chirp"}:
            raise ValueError("unsupported drive_mode")
        positive = {
            "bond_length": self.bond_length,
            "layer_spacing": self.layer_spacing,
            "mass": self.mass,
            "k_in": self.k_in,
            "k_inter": self.k_inter,
            "duration": self.duration,
            "rtol": self.rtol,
            "atol": self.atol,
            "max_step": self.max_step,
            "langevin_dt": self.langevin_dt,
        }
        for name, value in positive.items():
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        nonnegative = {
            "alpha": self.alpha,
            "beta_inter": self.beta_inter,
            "damping": self.damping,
            "interlayer_damping": self.interlayer_damping,
            "temperature_reduced": self.temperature_reduced,
            "drive_amplitude": self.drive_amplitude,
            "initial_displacement": self.initial_displacement,
            "defect_mass_multiplier": self.defect_mass_multiplier,
            "defect_bond_scale": self.defect_bond_scale,
        }
        for name, value in nonnegative.items():
            if not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if abs(float(self.strain_x)) > 0.25:
            raise ValueError("|strain_x| must be <= 0.25")
        if int(self.samples) < 64 or int(self.samples) > 20000:
            raise ValueError("samples must be between 64 and 20000")
        if self.stochastic_mode and self.temperature_reduced > 0 and self.damping <= 0:
            raise ValueError("Langevin temperature requires positive local damping")


@dataclass
class LatticeModel:
    config: LatticeConfig
    positions: np.ndarray
    layer_ids: np.ndarray
    sublattice: np.ndarray
    cell: np.ndarray
    masses: np.ndarray
    inplane_i: np.ndarray
    inplane_j: np.ndarray
    inplane_r0: np.ndarray
    inplane_scale: np.ndarray
    inter_i: np.ndarray
    inter_j: np.ndarray
    inter_rest: np.ndarray
    defect_mask: np.ndarray


def _cell_vectors(bond: float) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.array([math.sqrt(3.0) * bond, 0.0], dtype=float),
        np.array([math.sqrt(3.0) * bond / 2.0, 1.5 * bond], dtype=float),
    )


def _stack_shift(layer: int, stacking: str, delta: np.ndarray) -> np.ndarray:
    if stacking == "AA":
        return np.zeros(2, dtype=float)
    if stacking == "ABA":
        return np.zeros(2, dtype=float) if layer % 2 == 0 else delta.copy()
    return (layer % 3) * delta


def min_image(delta: np.ndarray, cell: np.ndarray) -> np.ndarray:
    arr = np.asarray(delta, dtype=float)
    inv_t = np.linalg.inv(cell).T
    frac = arr @ inv_t
    frac -= np.round(frac)
    return frac @ cell.T


def _unstrained_geometry(config: LatticeConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    a1, a2 = _cell_vectors(float(config.bond_length))
    basis = (np.array([0.0, 0.0]), np.array([0.0, float(config.bond_length)]))
    delta = (a1 + a2) / 3.0
    positions: list[np.ndarray] = []
    layers: list[int] = []
    subs: list[int] = []
    for layer in range(int(config.layers)):
        shift = _stack_shift(layer, config.stacking, delta)
        for ix in range(int(config.nx)):
            for iy in range(int(config.ny)):
                origin = ix * a1 + iy * a2 + shift
                for sub, b in enumerate(basis):
                    positions.append(origin + b)
                    layers.append(layer)
                    subs.append(sub)
    cell = np.column_stack([int(config.nx) * a1, int(config.ny) * a2])
    return np.asarray(positions), np.asarray(layers, dtype=int), np.asarray(subs, dtype=int), cell


def _find_inplane_pairs(positions: np.ndarray, layer_ids: np.ndarray, cell: np.ndarray, bond_length: float) -> tuple[np.ndarray, np.ndarray]:
    pi: list[int] = []
    pj: list[int] = []
    tolerance = max(1e-10, 1e-7 * float(bond_length))
    for layer in sorted(set(int(x) for x in layer_ids.tolist())):
        idx = np.where(layer_ids == layer)[0]
        for offset, i in enumerate(idx):
            js = idx[offset + 1 :]
            if js.size == 0:
                continue
            rel = min_image(positions[js] - positions[i], cell)
            dist = np.linalg.norm(rel, axis=1)
            for j in js[np.abs(dist - bond_length) <= tolerance]:
                pi.append(int(i)); pj.append(int(j))
    return np.asarray(pi, dtype=int), np.asarray(pj, dtype=int)


def _nearest_interlayer_pairs(positions: np.ndarray, layer_ids: np.ndarray, cell: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ii: list[int] = []
    jj: list[int] = []
    rest: list[np.ndarray] = []
    max_layer = int(np.max(layer_ids)) if len(layer_ids) else -1
    for layer in range(max_layer):
        lower = np.where(layer_ids == layer)[0]
        upper = np.where(layer_ids == layer + 1)[0]
        for i in lower:
            rel = min_image(positions[upper] - positions[i], cell)
            k = int(np.argmin(np.sum(rel * rel, axis=1)))
            ii.append(int(i)); jj.append(int(upper[k])); rest.append(rel[k])
    return np.asarray(ii, dtype=int), np.asarray(jj, dtype=int), np.asarray(rest, dtype=float).reshape((-1, 2))


def _defect_mask(positions: np.ndarray, layer_ids: np.ndarray, cell: np.ndarray, config: LatticeConfig) -> np.ndarray:
    mask = np.zeros(len(positions), dtype=bool)
    if config.defect_mode == "none":
        return mask
    target_layer = int(config.layers) // 2
    idx = np.where(layer_ids == target_layer)[0]
    frac = positions[idx] @ np.linalg.inv(cell).T
    frac -= np.floor(frac)
    d2 = np.sum((frac - np.array([0.5, 0.5])) ** 2, axis=1)
    if config.defect_mode in {"mass", "weak-bond"}:
        mask[idx[np.argsort(d2)[:2]]] = True
    else:
        dy = np.abs(frac[:, 1] - 0.5)
        mask[idx[dy <= max(0.5 / int(config.ny), 0.08)]] = True
    return mask


def build_lattice(config: LatticeConfig) -> LatticeModel:
    config.validate()
    base_pos, layer_ids, sublattice, base_cell = _unstrained_geometry(config)
    in_i, in_j = _find_inplane_pairs(base_pos, layer_ids, base_cell, float(config.bond_length))
    affine = np.array([[1.0 + float(config.strain_x), 0.0], [0.0, 1.0]], dtype=float)
    positions = base_pos @ affine.T
    cell = affine @ base_cell
    in_rel = min_image(positions[in_j] - positions[in_i], cell)
    in_r0 = np.linalg.norm(in_rel, axis=1)
    inter_i, inter_j, inter_rest = _nearest_interlayer_pairs(positions, layer_ids, cell)
    dmask = _defect_mask(positions, layer_ids, cell, config)
    masses = np.full(len(positions), float(config.mass), dtype=float)
    in_scale = np.ones(len(in_i), dtype=float)
    if config.defect_mode == "mass":
        masses[dmask] *= max(float(config.defect_mass_multiplier), 1e-12)
    elif config.defect_mode in {"weak-bond", "line-weak-bond"}:
        in_scale[dmask[in_i] | dmask[in_j]] *= float(config.defect_bond_scale)
    return LatticeModel(config, positions, layer_ids, sublattice, cell, masses, in_i, in_j, in_r0, in_scale, inter_i, inter_j, inter_rest, dmask)


def coordination_numbers(model: LatticeModel) -> np.ndarray:
    degree = np.zeros(len(model.positions), dtype=int)
    np.add.at(degree, model.inplane_i, 1); np.add.at(degree, model.inplane_j, 1)
    return degree


def _drive_value(config: LatticeConfig, t: float) -> float:
    amp, omega = float(config.drive_amplitude), float(config.drive_frequency)
    if config.drive_mode == "none": return 0.0
    if config.drive_mode == "sin": return amp * math.sin(omega * t)
    if config.drive_mode == "pulse": return amp if 0.20 * config.duration <= t <= 0.35 * config.duration else 0.0
    if config.drive_mode == "beat": return amp * (math.sin(0.8 * omega * t) + math.sin(1.2 * omega * t))
    phase = omega * t + 0.5 * (0.10 * omega / max(config.duration, 1e-12)) * t * t
    return amp * math.sin(phase)


def force_components(model: LatticeModel, u: np.ndarray, v: np.ndarray, t: float, *, include_dissipation: bool = True, include_external: bool = True) -> dict[str, np.ndarray]:
    cfg, n = model.config, len(model.positions)
    pos = model.positions + np.asarray(u, dtype=float)
    f_in = np.zeros((n, 2), dtype=float)
    if len(model.inplane_i):
        rel = min_image(pos[model.inplane_j] - pos[model.inplane_i], model.cell)
        r = np.linalg.norm(rel, axis=1); ext = r - model.inplane_r0
        mag = model.inplane_scale * (float(cfg.k_in) * ext + float(cfg.alpha) * ext ** 3)
        f = mag[:, None] * rel / np.maximum(r[:, None], 1e-14)
        np.add.at(f_in, model.inplane_i, f); np.add.at(f_in, model.inplane_j, -f)
    f_inter = np.zeros((n, 2), dtype=float)
    if len(model.inter_i):
        rel = min_image(pos[model.inter_j] - pos[model.inter_i], model.cell)
        q = rel - model.inter_rest; q2 = np.sum(q * q, axis=1)
        f = (float(cfg.k_inter) + float(cfg.beta_inter) * q2)[:, None] * q
        np.add.at(f_inter, model.inter_i, f); np.add.at(f_inter, model.inter_j, -f)
        if include_dissipation and cfg.interlayer_damping > 0:
            fd = float(cfg.interlayer_damping) * (np.asarray(v)[model.inter_j] - np.asarray(v)[model.inter_i])
            np.add.at(f_inter, model.inter_i, fd); np.add.at(f_inter, model.inter_j, -fd)
    f_local = np.zeros((n, 2), dtype=float)
    if include_dissipation and cfg.damping > 0:
        f_local -= float(cfg.damping) * model.masses[:, None] * np.asarray(v)
    f_external = np.zeros((n, 2), dtype=float)
    if include_external:
        if cfg.uniform_force_x != 0: f_external[:, 0] += float(cfg.uniform_force_x)
        if cfg.drive_mode != "none" and cfg.drive_amplitude != 0:
            f_external[model.layer_ids == int(cfg.layers) - 1, 1] += _drive_value(cfg, float(t))
    return {"inplane": f_in, "interlayer": f_inter, "local_damping": f_local, "external": f_external, "total": f_in + f_inter + f_local + f_external}


def equilibrium_residual(model: LatticeModel) -> float:
    z = np.zeros((len(model.positions), 2), dtype=float)
    return float(np.max(np.linalg.norm(force_components(model, z, z, 0.0, include_dissipation=False, include_external=False)["total"], axis=1)))


def internal_force_imbalance(model: LatticeModel, displacement_scale: float = 1e-3) -> float:
    rng = np.random.default_rng(20260904)
    u = rng.normal(scale=float(displacement_scale), size=(len(model.positions), 2)); v = np.zeros_like(u)
    comp = force_components(model, u, v, 0.0, include_dissipation=False, include_external=False)
    return float(np.linalg.norm(np.sum(comp["total"], axis=0)))


def potential_energy(model: LatticeModel, u: np.ndarray) -> float:
    cfg, pos = model.config, model.positions + np.asarray(u, dtype=float)
    total = 0.0
    if len(model.inplane_i):
        rel = min_image(pos[model.inplane_j] - pos[model.inplane_i], model.cell)
        ext = np.linalg.norm(rel, axis=1) - model.inplane_r0
        total += float(np.sum(model.inplane_scale * (0.5 * float(cfg.k_in) * ext ** 2 + 0.25 * float(cfg.alpha) * ext ** 4)))
    if len(model.inter_i):
        rel = min_image(pos[model.inter_j] - pos[model.inter_i], model.cell); q = rel - model.inter_rest; q2 = np.sum(q * q, axis=1)
        total += float(np.sum(0.5 * float(cfg.k_inter) * q2 + 0.25 * float(cfg.beta_inter) * q2 ** 2))
    return total


def _rhs(model: LatticeModel, t: float, state: np.ndarray) -> np.ndarray:
    n = len(model.positions); u = state[:2*n].reshape(n,2); v = state[2*n:].reshape(n,2)
    return np.concatenate([v.ravel(), (force_components(model,u,v,t)["total"] / model.masses[:,None]).ravel()])


def _initial_state(model: LatticeModel) -> np.ndarray:
    state = np.zeros(4 * len(model.positions), dtype=float)
    amp = float(model.config.initial_displacement)
    if amp != 0.0:
        site = int(np.where(model.layer_ids == int(model.config.layers)-1)[0][0]); state[2*site+1] = amp
    return state


def _deterministic_integrate(model: LatticeModel) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    cfg = model.config; t_eval = np.linspace(0.0, float(cfg.duration), int(cfg.samples))
    sol = solve_ivp(lambda t,y:_rhs(model,t,y),(0.0,float(cfg.duration)),_initial_state(model),method="DOP853",t_eval=t_eval,rtol=float(cfg.rtol),atol=float(cfg.atol),max_step=float(cfg.max_step))
    if not sol.success: raise RuntimeError(f"DOP853 failed: {sol.message}")
    return t_eval, sol.y.T, {"solver":"DOP853","nfev":int(sol.nfev),"status":"completed"}


def _langevin_integrate(model: LatticeModel) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    cfg = model.config; dt = float(cfg.langevin_dt); steps = max(1,int(math.ceil(float(cfg.duration)/dt)))
    sample_steps = np.unique(np.rint(np.linspace(0,steps,int(cfg.samples))).astype(int)); times = sample_steps*dt
    state = _initial_state(model); n = len(model.positions); rng = np.random.default_rng(int(cfg.seed)); rows=[]; next_sample=0
    for step in range(steps+1):
        if next_sample < len(sample_steps) and step == int(sample_steps[next_sample]): rows.append(state.copy()); next_sample += 1
        if step == steps: break
        t=step*dt; u=state[:2*n].reshape(n,2); v=state[2*n:].reshape(n,2)
        a=force_components(model,u,v,t)["total"] / model.masses[:,None]
        if cfg.temperature_reduced > 0 and cfg.damping > 0:
            noise=np.sqrt(2.0*float(cfg.damping)*float(cfg.temperature_reduced)/model.masses)[:,None]*math.sqrt(dt)*rng.normal(size=v.shape)
        else: noise=0.0
        v_new=v+a*dt+noise; u_new=u+v_new*dt; state=np.concatenate([u_new.ravel(),v_new.ravel()])
    return np.asarray(times), np.asarray(rows), {"solver":"Euler-Maruyama (seeded reduced-unit Langevin)","steps":steps,"seed":int(cfg.seed),"status":"completed"}


def _layer_kinetic(model: LatticeModel, velocities: np.ndarray) -> np.ndarray:
    out=np.zeros((len(velocities),int(model.config.layers)),dtype=float)
    for layer in range(int(model.config.layers)):
        mask=model.layer_ids==layer
        out[:,layer]=0.5*np.sum(model.masses[mask][None,:,None]*velocities[:,mask,:]**2,axis=(1,2))
    return out


def _work_traces(model: LatticeModel, t: np.ndarray, u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    p_input=np.zeros(len(t)); p_bottom=np.zeros(len(t)); bottom=model.layer_ids==0
    for k,tk in enumerate(t):
        comp=force_components(model,u[k],v[k],float(tk)); p_input[k]=float(np.sum(comp["external"]*v[k]))
        if model.config.layers>1: p_bottom[k]=float(np.sum(comp["interlayer"][bottom]*v[k,bottom]))
    def cum(p):
        out=np.zeros_like(p)
        if len(p)>1: out[1:]=np.cumsum(0.5*(p[1:]+p[:-1])*np.diff(t))
        return out
    return cum(p_input),cum(p_bottom)


def _relative_drift(values: np.ndarray) -> float:
    arr=np.asarray(values,dtype=float); return float(np.max(np.abs(arr-arr[0]))/max(abs(float(arr[0])),1e-14))


def local_vibration_spectrum(t: np.ndarray, signal: np.ndarray) -> dict[str, Any]:
    tt=np.asarray(t,dtype=float); yy=np.asarray(signal,dtype=float)
    if len(tt)<8: raise ValueError("at least 8 uniform samples are required")
    dt=float(np.mean(np.diff(tt)))
    if np.max(np.abs(np.diff(tt)-dt))>1e-7*max(1.0,abs(dt)): raise ValueError("local_vibration_spectrum requires uniform sampling")
    centered=yy-float(np.mean(yy)); amp=np.abs(np.fft.rfft(centered*np.hanning(len(centered)))); freq=np.fft.rfftfreq(len(centered),d=dt)
    order=np.argsort(amp[1:])[::-1][:8]+1 if len(amp)>1 else np.array([],dtype=int)
    return {"frequency":freq,"amplitude":amp,"peaks":[{"frequency":float(freq[i]),"amplitude":float(amp[i])} for i in order],"label":"local vibration spectrum; not q-resolved phonon dispersion"}


def analyze_result(model: LatticeModel, t: np.ndarray, states: np.ndarray) -> dict[str, Any]:
    n=len(model.positions); u=states[:,:2*n].reshape(len(states),n,2); v=states[:,2*n:].reshape(len(states),n,2)
    layer_ke=_layer_kinetic(model,v); kinetic=np.sum(layer_ke,axis=1); potential=np.asarray([potential_energy(model,row) for row in u]); total=kinetic+potential
    injected,bottom_work=_work_traces(model,t,u,v); site=int(np.where(model.layer_ids==int(model.config.layers)-1)[0][0]); spectrum=local_vibration_spectrum(t,u[:,site,1])
    vx=np.mean(np.abs(v[:,:,0]),axis=1); vy=np.mean(np.abs(v[:,:,1]),axis=1); anis=(vx-vy)/np.maximum(vx+vy,1e-14)
    input_work=float(injected[-1]); transfer=float(bottom_work[-1]/input_work) if abs(input_work)>1e-12 else None
    conservative=(model.config.damping==0 and model.config.interlayer_damping==0 and model.config.drive_mode=="none" and model.config.uniform_force_x==0 and not model.config.stochastic_mode)
    return {"displacement":u,"velocity":v,"layer_kinetic_energy":layer_ke,"kinetic_energy":kinetic,"potential_energy":potential,"total_energy":total,"anisotropy":anis,"injected_work":injected,"bottom_interlayer_work":bottom_work,"net_interlayer_work_over_input":transfer,"spectrum":spectrum,"conservative_energy_relative_drift":_relative_drift(total) if conservative else None,"conservative_baseline":conservative}


def integrate_case(config: LatticeConfig) -> dict[str, Any]:
    model=build_lattice(config); t,states,solver=_langevin_integrate(model) if config.stochastic_mode else _deterministic_integrate(model)
    return {"schema":MODEL_SCHEMA,"config":config,"model":model,"time":t,"states":states,"solver":solver,"analysis":analyze_result(model,t,states)}


def harmonic_dynamical_matrix(model: LatticeModel) -> np.ndarray:
    n=len(model.positions); K=np.zeros((2*n,2*n),dtype=float)
    if len(model.inplane_i):
        rel0=min_image(model.positions[model.inplane_j]-model.positions[model.inplane_i],model.cell); unit=rel0/np.maximum(np.linalg.norm(rel0,axis=1)[:,None],1e-14)
        for p,(i,j) in enumerate(zip(model.inplane_i,model.inplane_j)):
            block=float(model.config.k_in)*float(model.inplane_scale[p])*np.outer(unit[p],unit[p]); si=slice(2*int(i),2*int(i)+2); sj=slice(2*int(j),2*int(j)+2)
            K[si,si]+=block; K[sj,sj]+=block; K[si,sj]-=block; K[sj,si]-=block
    I=np.eye(2)
    for i,j in zip(model.inter_i,model.inter_j):
        block=float(model.config.k_inter)*I; si=slice(2*int(i),2*int(i)+2); sj=slice(2*int(j),2*int(j)+2)
        K[si,si]+=block; K[sj,sj]+=block; K[si,sj]-=block; K[sj,si]-=block
    mvec=np.repeat(model.masses,2); invsqrt=1.0/np.sqrt(mvec)
    return invsqrt[:,None]*K*invsqrt[None,:]


def normal_modes(model: LatticeModel) -> dict[str, Any]:
    eig=np.linalg.eigvalsh(harmonic_dynamical_matrix(model)); eig.sort(); freq=np.sqrt(np.maximum(eig,0.0))/(2.0*math.pi); positive=freq[eig>1e-8]
    return {"eigenvalues":eig,"frequencies_cycles_per_time":freq,"zero_mode_count":int(np.count_nonzero(np.abs(eig)<=1e-8)),"negative_eigenvalue_count":int(np.count_nonzero(eig<-1e-9)),"most_negative_eigenvalue":float(np.min(eig)),"first_positive_frequencies":[float(x) for x in positive[:24]],"boundary":"Finite periodic-cell harmonic normal modes; not q-resolved phonon dispersion."}


def result_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    model=result["model"]; analysis=result["analysis"]; modes=normal_modes(model); degree=coordination_numbers(model)
    return {"model":MODEL_TITLE,"variant":MODEL_VARIANT,"atoms":int(len(model.positions)),"layers":int(model.config.layers),"stacking":model.config.stacking,"inplane_bonds":int(len(model.inplane_i)),"interlayer_pairs":int(len(model.inter_i)),"coordination_min":int(np.min(degree)),"coordination_max":int(np.max(degree)),"equilibrium_force_residual":equilibrium_residual(model),"internal_force_imbalance":internal_force_imbalance(model),"conservative_energy_relative_drift":analysis["conservative_energy_relative_drift"],"final_layer_kinetic_energy":[float(x) for x in analysis["layer_kinetic_energy"][-1]],"final_anisotropy":float(analysis["anisotropy"][-1]),"injected_work":float(analysis["injected_work"][-1]),"bottom_interlayer_work":float(analysis["bottom_interlayer_work"][-1]),"net_interlayer_work_over_input":analysis["net_interlayer_work_over_input"],"dominant_local_spectrum_peaks":analysis["spectrum"]["peaks"][:5],"zero_mode_count":modes["zero_mode_count"],"negative_mode_count":modes["negative_eigenvalue_count"],"first_positive_mode_frequencies":modes["first_positive_frequencies"][:8],"solver":dict(result["solver"]),"scientific_boundary":"Reduced-unit multilayer lattice dynamics. Local FFT is not a phonon dispersion; interlayer coupling is a registry-matched shear proxy, not an ab-initio vdW potential."}


def conservative_config(config: LatticeConfig, *, duration: float | None = None) -> LatticeConfig:
    return replace(config,damping=0.0,interlayer_damping=0.0,drive_mode="none",drive_amplitude=0.0,uniform_force_x=0.0,stochastic_mode=False,temperature_reduced=0.0,duration=float(duration if duration is not None else config.duration))
