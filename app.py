"""
NHS A&E and RTT Waiting Times — interactive Plotly Dash dashboard.

Run locally:
    python app.py
    # then open http://127.0.0.1:8050

The app reads from data/nhs_waiting.db (build it first with
`python -m src.ingest`). It is deployment-ready: gunicorn entrypoint is
`app:server` (see Procfile / README).
"""

import warnings

import pandas as pd
from dash import Dash, dcc, html, dash_table, Input, Output
import dash

from src import analysis, stats, charts
from src.charts import BLUE

warnings.simplefilter("ignore")

app = Dash(__name__, suppress_callback_exceptions=True,
           title="NHS Waiting Times")
server = app.server  # gunicorn entrypoint for deployment

# ── pre-computed headline stats (cheap, done once at startup) ─────────────────
KPI = analysis.kpi_cards()
_nat = analysis.national_performance("2015-01-01")
MK = stats.mann_kendall(_nat["pct_within_4hrs"].dropna())
TRUSTS = analysis.trust_list()
SPECIALTIES = analysis.rtt_specialties()
DEFAULT_SPECS = ["Trauma and Orthopaedic Service", "Ear Nose and Throat Service",
                 "Ophthalmology Service", "Gynaecology Service",
                 "General Surgery Service"]
DEFAULT_SPECS = [s for s in DEFAULT_SPECS if s in SPECIALTIES] or SPECIALTIES[:5]


# ── reusable bits ─────────────────────────────────────────────────────────────
def kpi_card(label, value, sub="", icon="", tone=""):
    cls = "kpi" + (f" {tone}" if tone else "")
    return html.Div(className=cls, children=[
        html.Div(icon, className="kpi-icon"),
        html.Div(label, className="kpi-label"),
        html.Div(value, className="kpi-value"),
        html.Div(sub, className="kpi-sub"),
    ])


def graph(fig, gid=None):
    kwargs = {"figure": fig, "config": {"displayModeBar": False},
              "className": "card"}
    if gid is not None:
        kwargs["id"] = gid
    return dcc.Graph(**kwargs)


# ── tab: national overview ────────────────────────────────────────────────────
def tab_overview():
    yoy = KPI["yoy"]
    yoy_txt = f"{yoy:+.1f} pts" if yoy is not None else "n/a"
    yoy_tone = "good" if (yoy or 0) >= 0 else "bad"
    yoy_icon = "📈" if (yoy or 0) >= 0 else "📉"
    return html.Div([
        html.Div(className="kpi-row", children=[
            kpi_card("Latest 4-hour performance",
                     f"{KPI['latest_pct']:.1f}%", KPI["latest_period"], "🚑"),
            kpi_card("Change vs a year ago", yoy_txt, "all A&E types",
                     yoy_icon, yoy_tone),
            kpi_card("Monthly attendances",
                     f"{KPI['latest_att']/1e6:.2f}m", KPI["latest_period"], "👥"),
            kpi_card("Best month on record",
                     f"{KPI['best'][1]:.1f}%", KPI["best"][0], "🏆", "good"),
            kpi_card("Worst month on record",
                     f"{KPI['worst'][1]:.1f}%", KPI["worst"][0], "⚠️", "bad"),
        ]),
        graph(charts.national_performance_chart()),
        graph(charts.attendance_chart()),
    ])


# ── tab: trends & statistics ──────────────────────────────────────────────────
def tab_trends():
    trend_txt = (f"Mann-Kendall test: {MK['trend'].upper()} "
                 f"(z = {MK['z']:.2f}, p {'< 0.001' if MK['p_value'] < 1e-3 else f'= {MK['p_value']:.3f}'}, "
                 f"Sen's slope = {MK['sen_slope']:.3f} pts/month over {MK['n']} months).")
    return html.Div([
        html.Div(className="callout", children=[
            html.B("Is the decline statistically significant?  "),
            html.Span(trend_txt),
        ]),
        graph(charts.decomposition_chart()),
        html.Div(className="grid-2", children=[
            graph(charts.seasonal_index_chart()),
            covid_table_component(),
        ]),
    ])


def covid_table_component():
    df = analysis.covid_comparison()
    df.columns = ["Phase", "Avg 4-hr performance (%)", "Avg monthly attendances"]
    df["Phase"] = df["Phase"].str.replace(r"^\d\s", "", regex=True)
    return html.Div(className="card", children=[
        html.H4("Pre / during / post-COVID comparison", className="card-title"),
        dash_table.DataTable(
            data=df.to_dict("records"),
            columns=[{"name": c, "id": c} for c in df.columns],
            style_cell={"fontFamily": "Arial", "fontSize": 13, "padding": "8px",
                        "textAlign": "left"},
            style_header={"backgroundColor": "#005EB8", "color": "white",
                          "fontWeight": "bold"},
            style_data_conditional=[{"if": {"row_index": "odd"},
                                     "backgroundColor": "#f4f8fb"}]),
    ])


# ── tab: trust explorer ───────────────────────────────────────────────────────
def tab_trust():
    return html.Div([
        html.Div(className="controls", children=[
            html.Label("Select an NHS trust:"),
            dcc.Dropdown(id="trust-dropdown", options=TRUSTS,
                         value="BARTS HEALTH NHS TRUST" if "BARTS HEALTH NHS TRUST"
                         in TRUSTS else TRUSTS[0], clearable=False),
        ]),
        html.Div(id="trust-graphs"),
        html.Hr(),
        graph(charts.worst_trusts_chart()),
    ])


@app.callback(Output("trust-graphs", "children"),
              Input("trust-dropdown", "value"))
def update_trust(org_name):
    df = analysis.trust_timeseries(org_name).copy()
    df = df.sort_values("period", ascending=False).head(12)
    table = df.assign(
        Month=df["period"].dt.strftime("%b %Y"),
        **{"Type-1 attendances": df["att_type1"].map("{:,.0f}".format),
           "% within 4hrs": df["pct_within_4hrs_t1"].round(1),
           "Emergency admissions": df["emergency_admissions"].map("{:,.0f}".format)}
    )[["Month", "Type-1 attendances", "% within 4hrs", "Emergency admissions"]]
    return html.Div([
        graph(charts.trust_chart(org_name)),
        html.Div(className="grid-2", children=[
            graph(charts.trust_attendance_chart(org_name)),
            html.Div(className="card", children=[
                html.H4("Last 12 months", className="card-title"),
                dash_table.DataTable(
                    data=table.to_dict("records"),
                    columns=[{"name": c, "id": c} for c in table.columns],
                    style_cell={"fontFamily": "Arial", "fontSize": 12,
                                "padding": "6px", "textAlign": "right"},
                    style_cell_conditional=[{"if": {"column_id": "Month"},
                                             "textAlign": "left"}],
                    style_header={"backgroundColor": "#005EB8", "color": "white",
                                  "fontWeight": "bold"}),
            ]),
        ]),
    ])


# ── tab: regional ─────────────────────────────────────────────────────────────
def tab_regional():
    return html.Div([
        html.P("How the 4-hour standard varies across the seven NHS England "
               "regions. Greener = closer to the 95% target.", className="lead"),
        graph(charts.regional_heatmap_chart()),
        graph(charts.regional_latest_bar()),
    ])


# ── tab: RTT ──────────────────────────────────────────────────────────────────
def tab_rtt():
    return html.Div([
        graph(charts.rtt_national_chart()),
        graph(charts.rtt_specialty_bar()),
        html.Div(className="controls", children=[
            html.Label("Compare specialties (18-week breach trend):"),
            dcc.Dropdown(id="spec-dropdown", options=SPECIALTIES,
                         value=DEFAULT_SPECS, multi=True),
        ]),
        dcc.Graph(id="rtt-trend", config={"displayModeBar": False},
                  className="card"),
    ])


@app.callback(Output("rtt-trend", "figure"), Input("spec-dropdown", "value"))
def update_rtt(specialties):
    specialties = specialties or DEFAULT_SPECS
    return charts.rtt_trend_chart(specialties)


# ── tab: correlation ──────────────────────────────────────────────────────────
def tab_correlation():
    fig, res = charts.correlation_chart()
    if res.get("r") is not None:
        direction = "positive" if res["r"] > 0 else "negative"
        note = (f"Across {res['n']} trusts there is a statistically significant "
                f"{direction} correlation (r = {res['r']:.2f}, "
                f"p {'< 0.001' if res['p_value'] < 1e-3 else f'= {res['p_value']:.3f}'}) "
                "between A&E 4-hour performance and RTT 18-week performance — trusts "
                "that struggle on emergency flow tend to struggle on elective waits too.")
    else:
        note = "Not enough overlapping trusts to compute a correlation."
    return html.Div([
        html.Div(className="callout", children=[html.B("Finding:  "), html.Span(note)]),
        graph(fig),
    ])


# ── layout ────────────────────────────────────────────────────────────────────
app.layout = html.Div(className="app", children=[
    html.Header(className="header", children=[
        html.Div([
            html.H1("NHS England Waiting Times"),
            html.P("A&E 4-hour performance and RTT 18-week waits · 2015–2026",
                   className="subtitle"),
        ]),
        html.Div(className="header-stat", children=[
            html.Span(f"{KPI['latest_pct']:.1f}%"),
            html.Small(f"4-hr performance · {KPI['latest_period']}"),
        ]),
    ]),
    dcc.Tabs(id="tabs", value="overview", className="tabs", children=[
        dcc.Tab(label="🏥  National overview", value="overview"),
        dcc.Tab(label="📊  Trends & statistics", value="trends"),
        dcc.Tab(label="🏨  Trust explorer", value="trust"),
        dcc.Tab(label="🗺️  Regional", value="regional"),
        dcc.Tab(label="🩺  RTT specialties", value="rtt"),
        dcc.Tab(label="🔗  A&E ↔ RTT correlation", value="corr"),
    ]),
    dcc.Loading(html.Main(id="tab-content", className="content"),
                type="circle", color=BLUE),
    html.Footer(className="footer", children=[
        "Source: NHS England published A&E and RTT statistics · ",
        "Built with Python, SQLite, pandas, statsmodels & Plotly Dash",
    ]),
])


@app.callback(Output("tab-content", "children"), Input("tabs", "value"))
def render_tab(tab):
    return {
        "overview": tab_overview,
        "trends": tab_trends,
        "trust": tab_trust,
        "regional": tab_regional,
        "rtt": tab_rtt,
        "corr": tab_correlation,
    }[tab]()


if __name__ == "__main__":
    app.run(debug=True, port=8050)
