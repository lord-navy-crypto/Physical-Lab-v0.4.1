"""Physical Lab UI enhancement layer for embedded Streamlit simulations.

Loaded only when Physical Lab prepends this directory to PYTHONPATH.  It does
not change scientific calculations; it improves control ergonomics, responsive
layout, plot readability, and headline-result presentation.
"""
from __future__ import annotations

import html
import os
from typing import Any

PROFILE = os.environ.get("PHYSICAL_LAB_UI_PROFILE", "").strip()
ENABLED_PROFILES = {
    "numerical-methods",
    "ising-monte-carlo",
    "random-walk-monte-carlo",
    "nonlinear-chaos",
    "oscillation-integration",
    "kerr-geodesics",
    "solar-system-dynamics",
    "honeycomb-lattice",
    "radiation-platform",
    "radia-magnet-studio",
}

if PROFILE in ENABLED_PROFILES:
    try:
        import streamlit as st
    except Exception:
        st = None

    if st is not None and not getattr(st, "_physical_lab_ui_patched", False):
        st._physical_lab_ui_patched = True
        _original_set_page_config = st.set_page_config
        _original_markdown = st.markdown
        _original_dataframe = st.dataframe
        _original_plotly_chart = st.plotly_chart
        _original_pyplot = st.pyplot

        BASE_CSS = r"""
        <style>
        /* Physical Lab simulation UI v2 */
        .block-container {
          max-width: 1680px !important;
          padding-top: 1.35rem !important;
          padding-left: clamp(1rem, 2.7vw, 2.8rem) !important;
          padding-right: clamp(1rem, 2.7vw, 2.8rem) !important;
          padding-bottom: 5rem !important;
        }
        section[data-testid="stSidebar"] {
          min-width: 350px !important;
          max-width: 410px !important;
        }
        section[data-testid="stSidebar"] > div {
          width: 100% !important;
        }
        div[data-testid="stHorizontalBlock"] {
          flex-wrap: wrap !important;
          gap: .8rem !important;
          align-items: stretch !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
          min-width: min(100%, 235px) !important;
          flex: 1 1 235px !important;
        }
        div[data-testid="stMetric"] {
          min-height: 118px !important;
          border: 1px solid rgba(128,128,128,.20) !important;
          border-radius: 16px !important;
          padding: .9rem 1rem !important;
          background: color-mix(in srgb, var(--background-color, white) 96%, #edf2f7 4%) !important;
          box-shadow: 0 5px 18px rgba(20,32,50,.045) !important;
        }
        div[data-testid="stMetricLabel"] {
          white-space: normal !important;
          line-height: 1.25 !important;
          min-height: 2.15em !important;
        }
        div[data-testid="stMetricValue"] {
          font-size: clamp(1.25rem, 1.8vw, 1.75rem) !important;
          line-height: 1.2 !important;
          white-space: normal !important;
          overflow: visible !important;
          text-overflow: clip !important;
          word-break: break-word !important;
        }
        div[data-testid="stPlotlyChart"], div[data-testid="stPyplot"] {
          margin-top: .55rem !important;
          margin-bottom: 1.9rem !important;
          border-radius: 14px !important;
        }
        div[data-testid="stDataFrame"] {
          margin-top: .55rem !important;
          margin-bottom: 1.55rem !important;
          border-radius: 12px !important;
          overflow: hidden !important;
        }
        div[data-baseweb="tab-list"] {
          gap: .35rem !important;
          flex-wrap: wrap !important;
        }
        button[data-baseweb="tab"] {
          min-height: 42px !important;
          padding-left: .85rem !important;
          padding-right: .85rem !important;
        }
        div[data-testid="stExpander"] {
          border-radius: 13px !important;
          margin-bottom: .7rem !important;
        }
        .stButton > button, .stDownloadButton > button {
          min-height: 42px !important;
          border-radius: 10px !important;
        }
        [data-testid="stNumberInput"], [data-testid="stSelectbox"],
        [data-testid="stSlider"], [data-testid="stTextInput"] {
          margin-bottom: .42rem !important;
        }
        h1 { letter-spacing: -.025em !important; }
        h2 { margin-top: 2.1rem !important; }
        h3 { margin-top: 1.45rem !important; }
        .pl-result-grid {
          display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
          gap:.75rem; margin:.55rem 0 1.55rem 0;
        }
        .pl-result-card {
          border:1px solid rgba(128,128,128,.20); border-radius:14px;
          padding:.85rem .95rem; min-width:0;
          background:color-mix(in srgb, var(--background-color, white) 97%, #edf2f7 3%);
        }
        .pl-result-label {font-size:.82rem; opacity:.72; line-height:1.25; margin-bottom:.34rem;}
        .pl-result-value {font-size:1.18rem; font-weight:650; line-height:1.25; overflow-wrap:anywhere;}
        .pl-result-unit {font-size:.78rem; opacity:.64; margin-top:.35rem; line-height:1.25;}
        .pl-ui-note {
          border-left:4px solid #6b7280; border-radius:9px; padding:.62rem .78rem;
          margin:.45rem 0 .8rem 0; background:rgba(127,127,127,.07); font-size:.86rem;
        }
        @media (max-width: 850px) {
          section[data-testid="stSidebar"] { min-width: 300px !important; }
          div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            min-width: min(100%, 200px) !important; flex-basis:200px !important;
          }
        }
        </style>
        """

        PRESETS: dict[str, dict[str, dict[str, Any]]] = {
            "numerical-methods": {
                "Stable float64": {
                    "method_label": "Range-reduced Taylor (recommended)", "dtype": "float64",
                    "x_min": -20.0, "x_max": 20.0, "scan_points": 900,
                    "max_terms": 100, "reference_precision_digits": 80,
                },
                "Float32 stress test": {
                    "method_label": "Range-reduced Taylor (recommended)", "dtype": "float32",
                    "x_min": -40.0, "x_max": 40.0, "scan_points": 1200,
                    "max_terms": 120, "reference_precision_digits": 80,
                },
                "Raw cancellation stress": {
                    "method_label": "Raw Taylor (instability diagnostic)", "dtype": "float64",
                    "x_min": -80.0, "x_max": 80.0, "scan_points": 1400,
                    "max_terms": 160, "reference_precision_digits": 100,
                },
            },
            "ising-monte-carlo": {
                "Ordered phase": {"size": 32, "temperature": 1.5, "eq_sweeps": 600, "mc_sweeps": 1400},
                "Near critical": {"size": 32, "temperature": 2.269185, "eq_sweeps": 1000, "mc_sweeps": 2200},
                "Disordered phase": {"size": 32, "temperature": 3.5, "eq_sweeps": 500, "mc_sweeps": 1200},
            },
            "random-walk-monte-carlo": {
                "2D diffusion": {"rw_dimension": 2, "rw_steps": 1000, "rw_walkers": 10000},
                "3D diffusion": {"rw_dimension": 3, "rw_steps": 1500, "rw_walkers": 12000},
                "High-dimensional": {"rw_dimension": 10, "rw_steps": 1200, "rw_walkers": 16000},
            },
            "nonlinear-chaos": {
                "Asymmetric baseline": {
                    "theta1_0": 1.57079632679, "theta2_0": 1.27079632679,
                    "trajectory_duration": 20.0, "trajectory_dt": 0.01,
                },
                "Strong divergence": {
                    "theta1_0": 2.20, "theta2_0": 1.15,
                    "trajectory_duration": 30.0, "trajectory_dt": 0.005,
                    "lyap_duration": 40.0, "lyap_dt": 0.003,
                },
                "Fast exploratory": {
                    "trajectory_duration": 10.0, "trajectory_dt": 0.02,
                    "drive_a_points": 40, "kapitza_points": 50, "flip_resolution": 36,
                },
            },
            "oscillation-integration": {
                "Free oscillator": {"gamma": 0.0, "force_amplitude": 0.0, "u0": 1.0, "v0": 0.0},
                "Underdamped": {"gamma": 1.0, "force_amplitude": 0.0, "u0": 1.0, "v0": 0.0},
                "Near resonance": {
                    "gamma": 0.35, "force_amplitude": 0.8,
                    "force_frequency": 6.15, "duration": 24.0, "dt": 0.015,
                },
            },
            "radia-magnet-studio": {
                "Planar baseline": {
                    "cfg_device": "Planar", "cfg_period_mm": 50.0, "cfg_periods": 20,
                    "cfg_gap_mm": 12.0, "cfg_blocks_per_period": 4, "cfg_errors_enabled": False,
                },
                "Manufacturing sensitivity": {
                    "cfg_device": "Planar", "cfg_period_mm": 50.0, "cfg_periods": 20,
                    "cfg_gap_mm": 12.0, "cfg_errors_enabled": True, "cfg_field_error_pct": 1.0,
                    "cfg_longitudinal_error_mm": 0.05, "cfg_transverse_error_mm": 0.05,
                    "cfg_angle_error_deg": 0.5, "cfg_compare_ideal": True,
                },
                "Helical baseline": {
                    "cfg_device": "Helical", "cfg_period_mm": 50.0, "cfg_periods": 20,
                    "cfg_gap_mm": 12.0, "cfg_blocks_per_period": 8, "cfg_errors_enabled": False,
                },
            },
        }

        QUALITY: dict[str, dict[str, dict[str, Any]]] = {
            "numerical-methods": {
                "Fast preview": {"scan_points": 400, "max_terms": 80, "convergence_terms": 30},
                "Standard": {"scan_points": 1000, "max_terms": 120, "convergence_terms": 50},
                "Deep": {"scan_points": 3000, "max_terms": 180, "convergence_terms": 100},
            },
            "ising-monte-carlo": {
                "Fast preview": {"eq_sweeps": 200, "mc_sweeps": 500, "comparison_eq": 120, "comparison_mc": 220},
                "Standard": {"eq_sweeps": 500, "mc_sweeps": 1200, "comparison_eq": 250, "comparison_mc": 500},
                "Deep": {"eq_sweeps": 1200, "mc_sweeps": 3500, "comparison_eq": 600, "comparison_mc": 1600},
            },
            "random-walk-monte-carlo": {
                "Fast preview": {"rw_walkers": 3000},
                "Standard": {"rw_walkers": 12000},
                "Deep": {"rw_walkers": 50000},
            },
            "nonlinear-chaos": {
                "Fast preview": {"trajectory_dt": 0.02, "drive_a_points": 40, "kapitza_points": 50, "mass_points": 24, "flip_resolution": 32},
                "Standard": {"trajectory_dt": 0.01, "drive_a_points": 80, "kapitza_points": 100, "mass_points": 45, "flip_resolution": 60},
                "Deep": {"trajectory_dt": 0.005, "drive_a_points": 140, "kapitza_points": 160, "mass_points": 80, "flip_resolution": 90},
            },
            "oscillation-integration": {
                "Fast preview": {"dt": 0.04, "convergence_points": 5, "resonance_points": 50, "nonlinear_points": 24},
                "Standard": {"dt": 0.02, "convergence_points": 7, "resonance_points": 100, "nonlinear_points": 40},
                "Deep": {"dt": 0.008, "convergence_points": 10, "resonance_points": 220, "nonlinear_points": 90},
            },
            "radia-magnet-studio": {
                "Fast preview": {"cfg_axis_samples": 500, "cfg_make_2d": False, "cfg_make_3d": False, "cfg_seg_n": 1, "cfg_geometry_limit": 300},
                "Standard": {"cfg_axis_samples": 1000, "cfg_make_2d": True, "cfg_make_3d": True, "cfg_seg_n": 1, "cfg_geometry_limit": 600},
                "Deep": {"cfg_axis_samples": 2400, "cfg_make_2d": True, "cfg_make_3d": True, "cfg_seg_n": 2, "cfg_geometry_limit": 900},
            },
        }

        PROFILE_LABELS = {
            "numerical-methods": "Numerical error",
            "ising-monte-carlo": "Ising Monte Carlo",
            "random-walk-monte-carlo": "Random walk / MC",
            "nonlinear-chaos": "Nonlinear chaos",
            "oscillation-integration": "Oscillation",
            "kerr-geodesics": "Kerr black hole geodesics",
            "solar-system-dynamics": "Sun–Jupiter–Saturn dynamics",
            "honeycomb-lattice": "Multilayer honeycomb lattice",
            "radiation-platform": "Radiation workflow",
            "radia-magnet-studio": "RADIA Magnet Studio",
        }

        def _render_preset_tools() -> None:
            with st.sidebar:
                st.markdown("#### Physical Lab · Experiment controls")
                st.caption(f"Enhanced layout · {PROFILE_LABELS.get(PROFILE, PROFILE)}")
                options = PRESETS.get(PROFILE)
                if options:
                    selected = st.selectbox(
                        "Quick preset",
                        list(options),
                        key=f"__pl_preset_{PROFILE}",
                        help="Presets change model parameters only after you press Apply. You can edit every value afterward.",
                    )
                    if st.button("Apply preset", key=f"__pl_apply_{PROFILE}", width="stretch"):
                        for key, value in options[selected].items():
                            st.session_state[key] = value
                        st.success(f"Applied: {selected}")
                else:
                    st.caption("Use the staged controls below. Full physics parameters remain available; the enhanced view focuses on readability rather than hiding inputs.")
                quality_options = QUALITY.get(PROFILE)
                if quality_options:
                    quality_name = st.selectbox(
                        "Computation quality",
                        list(quality_options),
                        index=1 if len(quality_options) > 1 else 0,
                        key=f"__pl_quality_{PROFILE}",
                        help="Changes only numerical workload/resolution controls, not the underlying physical model parameters.",
                    )
                    if st.button("Apply quality", key=f"__pl_quality_apply_{PROFILE}", width="stretch"):
                        for key, value in quality_options[quality_name].items():
                            st.session_state[key] = value
                        st.success(f"Quality: {quality_name}")
                st.caption("Large parameter groups and result columns now wrap automatically instead of squeezing values into narrow cards.")
                st.divider()

        def _enhanced_set_page_config(*args: Any, **kwargs: Any):
            # Run-Vault restores are staged at the end of the previous Streamlit run.
            # Applying them here happens before the upstream app creates its widgets,
            # which avoids Streamlit's post-instantiation session-state restriction.
            pending = st.session_state.pop("__pl_restore_pending", None)
            if isinstance(pending, dict):
                for key, value in pending.items():
                    if isinstance(key, str) and key and not key.startswith("__"):
                        try:
                            st.session_state[key] = value
                        except Exception:
                            pass
            result = _original_set_page_config(*args, **kwargs)
            _original_markdown(BASE_CSS, unsafe_allow_html=True)
            _render_preset_tools()
            return result

        def _result_cards_from_frame(data: Any) -> bool:
            try:
                import pandas as pd
            except Exception:
                return False
            if not isinstance(data, pd.DataFrame) or data.empty:
                return False

            # Vertical key-result tables used by Ising, Chaos, and Oscillation.
            schemas = [
                ("Key quantity", "Value", "Unit / meaning"),
                ("Quantity", "Value (full)", "Unit / meaning"),
            ]
            for label_col, value_col, unit_col in schemas:
                if {label_col, value_col}.issubset(data.columns) and len(data) <= 14:
                    cards = []
                    for _, row in data.iterrows():
                        label = html.escape(str(row.get(label_col, "")))
                        value = html.escape(str(row.get(value_col, "")))
                        unit = html.escape(str(row.get(unit_col, ""))) if unit_col in data.columns else ""
                        cards.append(
                            f'<div class="pl-result-card"><div class="pl-result-label">{label}</div>'
                            f'<div class="pl-result-value">{value}</div>'
                            f'<div class="pl-result-unit">{unit}</div></div>'
                        )
                    _original_markdown('<div class="pl-result-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)
                    return True

            # One-row summary tables used by the Random Walk studio.
            if len(data) == 1 and 2 <= len(data.columns) <= 9:
                row = data.iloc[0]
                cards = []
                for col in data.columns:
                    label = html.escape(str(col).replace("_", " ").title())
                    value = html.escape(str(row[col]))
                    cards.append(
                        f'<div class="pl-result-card"><div class="pl-result-label">{label}</div>'
                        f'<div class="pl-result-value">{value}</div></div>'
                    )
                _original_markdown('<div class="pl-result-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)
                return True
            return False

        def _enhanced_dataframe(data=None, *args: Any, **kwargs: Any):
            if data is not None and _result_cards_from_frame(data):
                return None
            if "width" not in kwargs and "use_container_width" not in kwargs:
                kwargs["width"] = "stretch"
            return _original_dataframe(data, *args, **kwargs)

        def _enhanced_plotly_chart(figure_or_data, *args: Any, **kwargs: Any):
            try:
                figure = figure_or_data
                current_height = getattr(getattr(figure, "layout", None), "height", None)
                update = {
                    "margin": {"l": 58, "r": 30, "t": 68, "b": 58},
                    "font": {"size": 13},
                    "hoverlabel": {"font": {"size": 13}},
                }
                if not current_height or current_height < 480:
                    update["height"] = 520
                figure.update_layout(**update)
                if len(getattr(figure, "data", [])) > 1:
                    legend = getattr(figure.layout, "legend", None)
                    orientation = getattr(legend, "orientation", None) if legend is not None else None
                    if not orientation:
                        figure.update_layout(legend={"orientation": "h", "y": 1.10, "x": 0})
            except Exception:
                pass
            kwargs.setdefault("width", "stretch")
            config = dict(kwargs.get("config") or {})
            config.setdefault("displaylogo", False)
            config.setdefault("responsive", True)
            kwargs["config"] = config
            return _original_plotly_chart(figure_or_data, *args, **kwargs)

        def _enhanced_pyplot(fig=None, *args: Any, **kwargs: Any):
            if fig is not None:
                try:
                    width, height = fig.get_size_inches()
                    if width < 9.5:
                        fig.set_size_inches(10.2, max(float(height), 5.6), forward=True)
                    fig.set_constrained_layout(True)
                except Exception:
                    pass
            kwargs.setdefault("use_container_width", True)
            return _original_pyplot(fig, *args, **kwargs)

        st.set_page_config = _enhanced_set_page_config
        st.dataframe = _enhanced_dataframe
        st.plotly_chart = _enhanced_plotly_chart
        st.pyplot = _enhanced_pyplot
