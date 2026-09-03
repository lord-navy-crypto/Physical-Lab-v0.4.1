"""Physical Lab digital-twin scientific core.

Pure-Python reference math for sensor calibration, measurement/model comparison,
affine inverse fitting, phase-space statistics, and residual-guided sampling.
The functions are intentionally independent of Streamlit, Tauri, Arduino models,
and RADIA so every UI/adapter can share the same validated definitions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Iterable, Sequence

_EPS = 1e-15


def _finite_pairs(a: Iterable[float], b: Iterable[float]) -> tuple[list[float], list[float]]:
    aa, bb = [], []
    for x, y in zip(a, b):
        try:
            x = float(x); y = float(y)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            aa.append(x); bb.append(y)
    if len(aa) < 2:
        raise ValueError("At least two finite paired samples are required")
    return aa, bb


def _mean(x: Sequence[float]) -> float:
    return sum(x) / len(x)


def _sample_variance(x: Sequence[float]) -> float:
    if len(x) < 2:
        return 0.0
    m = _mean(x)
    return sum((v - m) ** 2 for v in x) / (len(x) - 1)


def _sample_covariance(x: Sequence[float], y: Sequence[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("Covariance requires paired samples")
    mx, my = _mean(x), _mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (len(x) - 1)


def _regression(x: Sequence[float], y: Sequence[float]) -> tuple[float, float, float, float, float, float]:
    """Return slope, intercept, rmse, r2, slope_se, intercept_se for y≈a*x+b."""
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("Regression requires paired samples")
    mx, my = _mean(x), _mean(y)
    sxx = sum((v - mx) ** 2 for v in x)
    if sxx <= _EPS:
        raise ValueError("Independent values have zero variance")
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    slope = sxy / sxx
    intercept = my - slope * mx
    residuals = [yy - (slope * xx + intercept) for xx, yy in zip(x, y)]
    sse = sum(r * r for r in residuals)
    rmse = math.sqrt(sse / len(x))
    syy = sum((v - my) ** 2 for v in y)
    r2 = 1.0 - sse / syy if syy > _EPS else (1.0 if sse <= _EPS else float("nan"))
    if len(x) > 2:
        sigma2 = sse / (len(x) - 2)
        slope_se = math.sqrt(max(0.0, sigma2 / sxx))
        intercept_se = math.sqrt(max(0.0, sigma2 * (1.0 / len(x) + mx * mx / sxx)))
    else:
        slope_se = float("nan")
        intercept_se = float("nan")
    return slope, intercept, rmse, r2, slope_se, intercept_se


@dataclass(frozen=True)
class CalibrationResult:
    n: int
    slope: float
    offset: float
    rmse: float
    r2: float
    slope_standard_error: float
    offset_standard_error: float
    residual_standard_deviation: float
    model: str = "reference = slope * raw + offset"
    caveat: str = "Calibration uncertainty describes this fitted dataset; it does not include unmodeled sensor drift, hysteresis, temperature dependence, or reference-standard uncertainty."

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FieldComparison:
    n: int
    mae: float
    rmse: float
    bias: float
    max_abs_error: float
    relative_rmse: float | None
    r2: float | None
    measured_peak_abs: float
    model_peak_abs: float
    measured_integral: float
    model_integral: float
    integral_difference: float
    residual_standard_deviation: float
    caveat: str = "Position and field units are inherited from the supplied data. A numerical agreement metric does not prove the model or measurement is physically correct."

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AffineModelFit:
    n: int
    scale: float
    offset: float
    rmse_before: float
    rmse_after: float
    r2_after: float
    improvement_fraction: float | None
    model: str = "measured ≈ scale * model + offset"
    caveat: str = "This is an affine discrepancy calibration, not inference of physical geometry or material parameters. Use a validated forward-model adapter before interpreting fitted values physically."

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PhasePlaneStats:
    n: int
    mean_q: float
    mean_p: float
    var_q: float
    var_p: float
    covariance_qp: float
    rms_emittance: float
    twiss_alpha: float | None
    twiss_beta: float | None
    twiss_gamma: float | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BeamPhaseSpaceResult:
    x_plane: PhasePlaneStats
    y_plane: PhasePlaneStats
    normalized_x_emittance: float | None
    normalized_y_emittance: float | None
    beta_gamma: float | None
    caveat: str = "RMS emittance is computed from the supplied coordinate/momentum-like columns. Units and canonical-vs-angle conventions must be defined by the dataset; normalized emittance is only reported when beta*gamma is explicitly supplied."

    def to_dict(self) -> dict:
        return {
            "x_plane": self.x_plane.to_dict(),
            "y_plane": self.y_plane.to_dict(),
            "normalized_x_emittance": self.normalized_x_emittance,
            "normalized_y_emittance": self.normalized_y_emittance,
            "beta_gamma": self.beta_gamma,
            "caveat": self.caveat,
        }


def fit_linear_calibration(raw: Iterable[float], reference: Iterable[float]) -> CalibrationResult:
    x, y = _finite_pairs(raw, reference)
    slope, offset, rmse, r2, slope_se, offset_se = _regression(x, y)
    residuals = [yy - (slope * xx + offset) for xx, yy in zip(x, y)]
    residual_sd = math.sqrt(_sample_variance(residuals))
    return CalibrationResult(len(x), slope, offset, rmse, r2, slope_se, offset_se, residual_sd)


def apply_linear_calibration(raw: Iterable[float], slope: float, offset: float) -> list[float]:
    if not math.isfinite(float(slope)) or not math.isfinite(float(offset)):
        raise ValueError("Calibration slope and offset must be finite")
    out = []
    for value in raw:
        value = float(value)
        out.append(float("nan") if not math.isfinite(value) else slope * value + offset)
    return out


def _trapz(x: Sequence[float], y: Sequence[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("Trapezoidal integration requires at least two paired samples")
    pairs = sorted(zip(x, y), key=lambda p: p[0])
    total = 0.0
    for (x0, y0), (x1, y1) in zip(pairs[:-1], pairs[1:]):
        total += 0.5 * (y0 + y1) * (x1 - x0)
    return total


def compare_field_series(position: Iterable[float], measured: Iterable[float], model: Iterable[float]) -> FieldComparison:
    triples = []
    for z, a, b in zip(position, measured, model):
        try:
            z = float(z); a = float(a); b = float(b)
        except (TypeError, ValueError):
            continue
        if math.isfinite(z) and math.isfinite(a) and math.isfinite(b):
            triples.append((z, a, b))
    if len(triples) < 2:
        raise ValueError("At least two finite position/measured/model rows are required")
    triples.sort(key=lambda row: row[0])
    z = [r[0] for r in triples]; m = [r[1] for r in triples]; p = [r[2] for r in triples]
    residual = [a - b for a, b in zip(m, p)]
    n = len(z)
    mae = sum(abs(r) for r in residual) / n
    rmse = math.sqrt(sum(r*r for r in residual) / n)
    bias = _mean(residual)
    max_abs = max(abs(r) for r in residual)
    model_scale = sum(abs(v) for v in p) / n
    relative = rmse / model_scale if model_scale > _EPS else None
    pm = _mean(p)
    ss_tot = sum((v - pm) ** 2 for v in p)
    ss_res = sum(r*r for r in residual)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > _EPS else None
    mi = _trapz(z, m); pi = _trapz(z, p)
    return FieldComparison(
        n=n, mae=mae, rmse=rmse, bias=bias, max_abs_error=max_abs,
        relative_rmse=relative, r2=r2,
        measured_peak_abs=max(abs(v) for v in m), model_peak_abs=max(abs(v) for v in p),
        measured_integral=mi, model_integral=pi, integral_difference=mi-pi,
        residual_standard_deviation=math.sqrt(_sample_variance(residual)),
    )


def fit_model_affine(measured: Iterable[float], model: Iterable[float]) -> AffineModelFit:
    model_values, measured_values = _finite_pairs(model, measured)
    scale, offset, rmse_after, r2, _, _ = _regression(model_values, measured_values)
    before_residual = [a-b for a,b in zip(measured_values, model_values)]
    rmse_before = math.sqrt(sum(r*r for r in before_residual) / len(before_residual))
    improvement = None if rmse_before <= _EPS else 1.0 - rmse_after / rmse_before
    return AffineModelFit(len(model_values), scale, offset, rmse_before, rmse_after, r2, improvement)


def phase_plane_stats(q: Iterable[float], p: Iterable[float]) -> PhasePlaneStats:
    qv, pv = _finite_pairs(q, p)
    var_q = _sample_variance(qv); var_p = _sample_variance(pv); cov = _sample_covariance(qv, pv)
    determinant = max(0.0, var_q * var_p - cov * cov)
    emit = math.sqrt(determinant)
    if emit > _EPS:
        alpha = -cov / emit
        beta = var_q / emit
        gamma = var_p / emit
    else:
        alpha = beta = gamma = None
    return PhasePlaneStats(len(qv), _mean(qv), _mean(pv), var_q, var_p, cov, emit, alpha, beta, gamma)


def analyze_beam_phase_space(
    x: Iterable[float], px: Iterable[float], y: Iterable[float], py: Iterable[float], *, beta_gamma: float | None = None
) -> BeamPhaseSpaceResult:
    xplane = phase_plane_stats(x, px)
    yplane = phase_plane_stats(y, py)
    bg = None
    if beta_gamma is not None:
        bg = float(beta_gamma)
        if not math.isfinite(bg) or bg <= 0:
            raise ValueError("beta_gamma must be positive and finite when supplied")
    return BeamPhaseSpaceResult(
        x_plane=xplane, y_plane=yplane,
        normalized_x_emittance=None if bg is None else bg * xplane.rms_emittance,
        normalized_y_emittance=None if bg is None else bg * yplane.rms_emittance,
        beta_gamma=bg,
    )


def suggest_residual_measurement_points(
    position: Iterable[float], measured: Iterable[float], model: Iterable[float], *, count: int = 3, minimum_spacing_fraction: float = 0.08
) -> list[dict[str, float]]:
    """Heuristic residual-guided sampling, deliberately not labeled information gain."""
    rows = []
    for z, a, b in zip(position, measured, model):
        try: z=float(z); a=float(a); b=float(b)
        except (TypeError, ValueError): continue
        if math.isfinite(z) and math.isfinite(a) and math.isfinite(b): rows.append((z,a,b))
    if len(rows) < 3:
        raise ValueError("At least three finite rows are required")
    rows.sort(key=lambda r:r[0])
    z=[r[0] for r in rows]; residual=[r[1]-r[2] for r in rows]
    span=max(z)-min(z); min_spacing=max(0.0, float(minimum_spacing_fraction))*span
    scores=[]
    scale=max(max(abs(r) for r in residual), _EPS)
    for i,(zz,rr) in enumerate(zip(z,residual)):
        if i==0:
            grad=abs((residual[1]-residual[0])/(z[1]-z[0])) if z[1]!=z[0] else 0.0
        elif i==len(z)-1:
            grad=abs((residual[-1]-residual[-2])/(z[-1]-z[-2])) if z[-1]!=z[-2] else 0.0
        else:
            dz=z[i+1]-z[i-1]; grad=abs((residual[i+1]-residual[i-1])/dz) if dz!=0 else 0.0
        grad_scale=span if span>_EPS else 1.0
        score=abs(rr)/scale + 0.35*grad*grad_scale/scale
        scores.append((score,zz,rr))
    selected=[]
    for score,zz,rr in sorted(scores, reverse=True):
        if all(abs(zz-s["position"]) >= min_spacing for s in selected):
            selected.append({"position":zz,"residual":rr,"score":score})
        if len(selected)>=max(1,int(count)): break
    return selected
