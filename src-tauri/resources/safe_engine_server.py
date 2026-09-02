#!/usr/bin/env python3
"""Physical Lab safe-mode analytical server.

This server intentionally avoids fragile compiled physics engines such as RADIA.
It uses only the Python standard library so the accelerator-physics Labs retain a
useful fallback when a native engine is missing or ABI-incompatible.
"""
from __future__ import annotations

import argparse
import html
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HC_EV_M = 1.2398419843320026e-6
E_REST_GEV = 0.00051099895


def fval(q, name, default, lo=None, hi=None):
    try:
        value = float(q.get(name, [str(default)])[0])
    except (TypeError, ValueError):
        value = float(default)
    if not math.isfinite(value):
        value = float(default)
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def ival(q, name, default, lo=None, hi=None):
    try:
        value = int(float(q.get(name, [str(default)])[0]))
    except (TypeError, ValueError):
        value = int(default)
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def line_svg(points, *, x_label: str, y_label: str, title: str, width: int = 920, height: int = 300) -> str:
    """Small dependency-free SVG line chart for analytical safe mode."""
    clean=[(float(x),float(y)) for x,y in points if math.isfinite(float(x)) and math.isfinite(float(y))]
    if len(clean)<2:
        return ""
    xs=[p[0] for p in clean]; ys=[p[1] for p in clean]
    xmin,xmax=min(xs),max(xs); ymin,ymax=min(ys),max(ys)
    if xmax==xmin: xmax=xmin+1.0
    if ymax==ymin: ymax=ymin+1.0
    left,right,top,bottom=72,24,42,56
    pw=width-left-right; ph=height-top-bottom
    def sx(x): return left+(x-xmin)/(xmax-xmin)*pw
    def sy(y): return top+ph-(y-ymin)/(ymax-ymin)*ph
    path=" ".join(("M" if i==0 else "L")+f" {sx(x):.2f} {sy(y):.2f}" for i,(x,y) in enumerate(clean))
    grid=[]
    labels=[]
    for i in range(5):
        fx=i/4
        x=xmin+fx*(xmax-xmin); px=left+fx*pw
        y=ymin+fx*(ymax-ymin); py=top+ph-fx*ph
        grid.append(f"<line x1='{px:.2f}' y1='{top}' x2='{px:.2f}' y2='{top+ph}' class='gridline'/>")
        grid.append(f"<line x1='{left}' y1='{py:.2f}' x2='{left+pw}' y2='{py:.2f}' class='gridline'/>")
        labels.append(f"<text x='{px:.2f}' y='{height-28}' class='tick' text-anchor='middle'>{x:.4g}</text>")
        labels.append(f"<text x='{left-10}' y='{py+4:.2f}' class='tick' text-anchor='end'>{y:.4g}</text>")
    return f"""<div class='chart'><div class='chart-title'>{html.escape(title)}</div><svg viewBox='0 0 {width} {height}' role='img' aria-label='{html.escape(title)}'>{''.join(grid)}<path d='{path}' class='curve'/>{''.join(labels)}<text x='{left+pw/2:.2f}' y='{height-5}' class='axis' text-anchor='middle'>{html.escape(x_label)}</text><text x='15' y='{top+ph/2:.2f}' class='axis' text-anchor='middle' transform='rotate(-90 15 {top+ph/2:.2f})'>{html.escape(y_label)}</text></svg></div>"""


def page(title: str, body: str) -> bytes:
    css = """
    :root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0d1118;color:#edf2f7;font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',sans-serif}.wrap{max-width:1380px;margin:0 auto;padding:34px clamp(18px,3vw,44px) 70px}.banner{border:1px solid #5b4b23;background:#262012;color:#efd58d;border-radius:13px;padding:13px 15px;font-size:12px;line-height:1.58;margin-bottom:20px}.panel{border:1px solid #2b3544;background:#141b25;border-radius:16px;padding:20px;margin-bottom:18px}h1{font-size:27px;margin:0 0 8px}h2{font-size:17px;margin:0 0 13px}.sub{color:#91a0b2;font-size:12px;line-height:1.6}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}.field label{display:block;color:#9aa8ba;font-size:11px;margin-bottom:6px}.field input{width:100%;border:1px solid #354052;background:#0f151e;color:#eef2f7;border-radius:10px;padding:11px 10px;font-size:14px}.btn{margin-top:16px;border:0;border-radius:10px;background:#eef2f7;color:#11161d;font-weight:700;padding:11px 17px;cursor:pointer;min-height:42px}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:11px;margin-bottom:18px}.metric{border:1px solid #293443;background:#10161e;border-radius:13px;padding:15px;min-height:98px}.metric span{display:block;color:#8392a5;font-size:10px;line-height:1.3;margin-bottom:7px}.metric strong{font-size:18px;line-height:1.25;word-break:break-word}.two{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(260px,.55fr);gap:16px;align-items:start}.chart{border:1px solid #293443;background:#10161e;border-radius:14px;padding:12px 12px 4px;margin-top:6px}.chart-title{font-weight:650;font-size:13px;padding:3px 4px 6px;color:#dce6f1}.chart svg{display:block;width:100%;height:auto}.gridline{stroke:#273342;stroke-width:1}.curve{fill:none;stroke:#7dd3fc;stroke-width:3}.tick{fill:#8493a6;font-size:10px}.axis{fill:#aebaca;font-size:11px}table{width:100%;border-collapse:collapse;font-size:11px}th,td{border-bottom:1px solid #26303e;padding:8px;text-align:right}th:first-child,td:first-child{text-align:left}.note{color:#8796aa;font-size:11px;line-height:1.6;margin-top:12px}.formula{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#0f151e;border:1px solid #293443;border-radius:10px;padding:11px;font-size:11px;color:#c8d6e5;overflow-wrap:anywhere}@media(max-width:900px){.two{grid-template-columns:1fr}.wrap{padding-top:24px}}
    """
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{css}</style></head><body><div class='wrap'>{body}</div></body></html>".encode()


def magnet_page(q):
    period_mm = fval(q, 'period_mm', 50.0, 1.0, 1000.0)
    b0 = fval(q, 'b0', 0.15, 0.0, 20.0)
    periods = ival(q, 'periods', 20, 1, 500)
    gap_mm = fval(q, 'gap_mm', 12.0, 0.1, 500.0)
    period_m = period_mm / 1000.0
    k = 0.934 * b0 * (period_mm / 10.0)
    length_m = period_m * periods
    rows=[]
    for i in range(17):
        z=-period_m + 2*period_m*i/16
        by=b0*math.sin(2*math.pi*z/period_m)
        rows.append(f"<tr><td>{z*1000:.3f}</td><td>{by:.6f}</td></tr>")
    body=f"""
    <h1>RADIA Magnet Studio — Safe Mode</h1>
    <div class='banner'><strong>Safe / non-fragile-engine mode.</strong> RADIA is not imported. This page uses an ideal planar-undulator analytical model so the Lab remains usable when the native RADIA extension is unavailable. It does not reproduce finite-block geometry, material relaxation, fringe fields, manufacturing errors, or a 3-D RADIA solve.</div>
    <div class='panel'><h2>Ideal undulator inputs</h2><form><div class='grid'>
      <div class='field'><label>Period λu (mm)</label><input name='period_mm' value='{period_mm:g}'></div>
      <div class='field'><label>Peak field B0 (T)</label><input name='b0' value='{b0:g}'></div>
      <div class='field'><label>Periods</label><input name='periods' value='{periods}'></div>
      <div class='field'><label>Nominal gap (mm)</label><input name='gap_mm' value='{gap_mm:g}'></div>
    </div><button class='btn'>Recalculate</button></form></div>
    <div class='metrics'>
      <div class='metric'><span>Undulator K</span><strong>{k:.5f}</strong></div>
      <div class='metric'><span>Magnetic length</span><strong>{length_m:.4f} m</strong></div>
      <div class='metric'><span>Peak field</span><strong>{b0:.5f} T</strong></div>
      <div class='metric'><span>Nominal gap</span><strong>{gap_mm:.3f} mm</strong></div>
    </div>
    <div class='panel'><h2>Ideal on-axis field</h2>{line_svg([(-period_mm + 2*period_mm*i/64, b0*math.sin(2*math.pi*(-period_mm + 2*period_mm*i/64)/period_mm)) for i in range(65)], x_label='z (mm)', y_label='By (T)', title='Ideal sinusoidal on-axis field')}<details><summary>Show sampled field table</summary><table><thead><tr><th>z (mm)</th><th>By (T)</th></tr></thead><tbody>{''.join(rows)}</tbody></table></details><div class='note'>Model: By(z)=B0 sin(2πz/λu), K≈0.934 B0[T] λu[cm]. Full mode should be used whenever real magnetic geometry or RADIA-based field solving matters.</div></div>
    """
    return page('RADIA Magnet Studio Safe Mode',body)


def radiation_page(q):
    period_mm=fval(q,'period_mm',50.0,1.0,1000.0)
    k=fval(q,'k',0.7003,0.0,50.0)
    energy_gev=fval(q,'energy_gev',3.0,0.001,1000.0)
    harmonic=ival(q,'harmonic',1,1,99)
    theta_mrad=fval(q,'theta_mrad',0.0,0.0,1000.0)
    periods=ival(q,'periods',20,2,500)
    gamma=energy_gev/E_REST_GEV
    period_m=period_mm/1000.0
    theta=theta_mrad/1000.0
    denom=2*gamma*gamma*harmonic
    wavelength=period_m*(1+k*k/2+(gamma*theta)**2)/denom
    photon_ev=HC_EV_M/wavelength if wavelength>0 else float('inf')
    freq=299792458.0/wavelength if wavelength>0 else float('inf')
    rel_linewidth=1.0/periods
    angle_max=max(0.5, theta_mrad*2.0, 2.0/max(gamma,1.0)*1000.0)
    angle_points=[]
    for i in range(81):
        am=angle_max*i/80
        a=am/1000.0
        lam=period_m*(1+k*k/2+(gamma*a)**2)/denom
        angle_points.append((am,HC_EV_M/lam if lam>0 else 0.0))
    body=f"""
    <h1>Radiation Platform — Safe Mode</h1>
    <div class='banner'><strong>Safe / non-fragile-engine mode.</strong> No RADIA field map is used. This calculator evaluates the ideal planar-undulator resonance relation. It is suitable for quick estimates and fallback operation, not for a replacement of the full magnet → trajectory → radiation workflow.</div>
    <div class='panel'><h2>Ideal resonance inputs</h2><form><div class='grid'>
      <div class='field'><label>Electron energy (GeV)</label><input name='energy_gev' value='{energy_gev:g}'></div>
      <div class='field'><label>Period λu (mm)</label><input name='period_mm' value='{period_mm:g}'></div>
      <div class='field'><label>Undulator K</label><input name='k' value='{k:g}'></div>
      <div class='field'><label>Harmonic n</label><input name='harmonic' value='{harmonic}'></div>
      <div class='field'><label>Observation angle (mrad)</label><input name='theta_mrad' value='{theta_mrad:g}'></div>
      <div class='field'><label>Undulator periods N</label><input name='periods' value='{periods}'></div>
    </div><button class='btn'>Recalculate</button></form></div>
    <div class='metrics'>
      <div class='metric'><span>Lorentz γ</span><strong>{gamma:,.1f}</strong></div>
      <div class='metric'><span>Resonant wavelength</span><strong>{wavelength*1e9:.6g} nm</strong></div>
      <div class='metric'><span>Photon energy</span><strong>{photon_ev:.6g} eV</strong></div>
      <div class='metric'><span>Frequency</span><strong>{freq:.5e} Hz</strong></div>
      <div class='metric'><span>Approx. finite-N relative linewidth</span><strong>{100*rel_linewidth:.3g}%</strong></div>
    </div>
    <div class='two'>
      <div class='panel'><h2>Observation-angle trend</h2>{line_svg(angle_points, x_label='Observation angle (mrad)', y_label='Photon energy (eV)', title='Ideal resonance energy versus angle')}</div>
      <div class='panel'><h2>What controls the result</h2><div class='formula'>λₙ = λᵤ / (2γ²n) · [1 + K²/2 + γ²θ²]</div><div class='note'>Higher electron energy raises photon energy roughly as γ². Increasing K or observation angle increases the resonant wavelength. The 1/N linewidth shown above is an ideal finite-period scale estimate, not a detector or beamline resolution.</div></div>
    </div>
    <div class='panel'><div class='note'>Full mode should be used for real field errors, detailed trajectories, polarization, finite-device effects, spectral intensity, beam properties, or RADIA-derived magnetic geometry.</div></div>
    """
    return page('Radiation Platform Safe Mode',body)


class Handler(BaseHTTPRequestHandler):
    module=''
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query)
        if self.module=='radia-magnet-studio': data=magnet_page(q)
        elif self.module=='radiation-platform': data=radiation_page(q)
        else: data=page('Physical Lab Safe Mode',"<h1>Safe Mode</h1><div class='banner'>This Lab has no fragile external physics engine. Physical Lab normally launches its standard scientific Python implementation.</div>")
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def log_message(self, *_): pass


def main():
    p=argparse.ArgumentParser(); p.add_argument('--module',required=True); p.add_argument('--port',type=int,required=True); a=p.parse_args()
    Handler.module=a.module
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
    server.serve_forever()

if __name__=='__main__': main()
