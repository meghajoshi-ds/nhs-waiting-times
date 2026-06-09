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

from src import analysis, stats, charts, decision
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
DEC_SPECIALTIES = decision.specialties()
REGION_OPTIONS = decision.regions()
REFRESH = decision.last_refresh()
SCOT = analysis.scotland_kpis()
SCOT_BOARDS = analysis.scotland_board_list()
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


# ── tab: find the shortest wait (decision support) ────────────────────────────
def tab_decision():
    return html.Div([
        html.P("Don't just see the wait — act on it. Pick a specialty and (optionally) "
               "your region to find the fastest providers, how far they beat the "
               "national average, whether they're improving, and the weeks you could "
               "save by choosing one.", className="lead"),
        html.Div(className="controls grid-2", children=[
            html.Div([
                html.Label("Specialty"),
                dcc.Dropdown(id="dec-specialty", options=DEC_SPECIALTIES,
                             value="Ear Nose and Throat Service"
                             if "Ear Nose and Throat Service" in DEC_SPECIALTIES
                             else DEC_SPECIALTIES[0], clearable=False),
            ]),
            html.Div([
                html.Label("Region"),
                dcc.Dropdown(id="dec-region", options=REGION_OPTIONS,
                             value="ALL", clearable=False),
            ]),
        ]),
        dcc.Loading(html.Div(id="decision-output"), type="dot", color=BLUE),
    ])


def _arrow(direction, delta):
    if direction == "improving":
        return f"▼ {abs(delta):.1f} wks (improving)"
    if direction == "worsening":
        return f"▲ {abs(delta):.1f} wks (worsening)"
    return "– stable"


@app.callback(Output("decision-output", "children"),
              Input("dec-specialty", "value"), Input("dec-region", "value"))
def update_decision(specialty, region):
    s = decision.recommendation_summary(specialty, region)
    if s is None:
        return html.Div("No data available for this selection.", className="card")

    spec_short = specialty.replace(" Service", "")
    saved_txt = (f"choosing it over the {s['region']} average would save about "
                 f"{s['weeks_saved']:.0f} weeks" if s["weeks_saved"] >= 1
                 else "it is already close to the regional average")
    headline = (f"For {spec_short} in {s['region']}, the median wait is about "
                f"{s['scope_avg']:.0f} weeks across {s['n_providers']} providers. "
                f"The fastest is {s['fastest_name']} at {s['fastest_wait']:.0f} "
                f"weeks ({abs(s['fastest_vs_national'])}% below the national average) "
                f"— {saved_txt}.")

    df = decision.provider_recommendations(specialty, region)
    table = pd.DataFrame({
        "Provider": df["provider_name"].str.title(),
        "Region": df["region"],
        "Median wait": df["median_wait_wks"].round(1).astype(str) + " wks",
        "vs national": df["vs_national_pct"].map(
            lambda v: f"{v:+.0f}%" if pd.notna(v) else "—"),
        "6-month trend": [_arrow(d, t) for d, t in
                          zip(df["direction"], df["trend_6m"].fillna(0))],
        "Percentile": df["percentile"].map(
            lambda p: f"Top {100 - int(p)}%" if p >= 50 else f"{int(p)}th"),
        "Waiting list": df["total_waiting"].map("{:,.0f}".format),
    })

    return html.Div([
        html.Div(className="callout", children=[
            html.B("💡 Recommendation:  "), html.Span(headline)]),
        html.Div(className="kpi-row", children=[
            kpi_card("National avg wait", f"{s['national_avg']:.0f} wks",
                     "patient-weighted median", "🇬🇧"),
            kpi_card(f"{s['region']} avg", f"{s['scope_avg']:.0f} wks",
                     f"{s['n_providers']} providers", "📍"),
            kpi_card("Fastest provider", f"{s['fastest_wait']:.0f} wks",
                     s["fastest_name"][:26], "⚡", "good"),
            kpi_card("Weeks you could save", f"{s['weeks_saved']:.0f}",
                     "vs regional average", "⏱️",
                     "good" if s["weeks_saved"] >= 1 else ""),
        ]),
        graph(charts.fastest_providers_chart(specialty, region)),
        graph(charts.specialty_trend_chart(specialty)),
        html.Div(className="card", children=[
            html.H4(f"All providers · {spec_short} · {s['region']} "
                    f"(fastest first, {s['latest_month']})", className="card-title"),
            dash_table.DataTable(
                data=table.to_dict("records"),
                columns=[{"name": c, "id": c} for c in table.columns],
                page_size=15, sort_action="native", filter_action="native",
                style_cell={"fontFamily": "Inter, Arial", "fontSize": 12,
                            "padding": "8px", "textAlign": "left"},
                style_header={"backgroundColor": "#005EB8", "color": "white",
                              "fontWeight": "600"},
                style_data_conditional=[
                    {"if": {"filter_query": "{6-month trend} contains 'improving'",
                            "column_id": "6-month trend"},
                     "color": "#009639", "fontWeight": "600"},
                    {"if": {"filter_query": "{6-month trend} contains 'worsening'",
                            "column_id": "6-month trend"},
                     "color": "#DA291C", "fontWeight": "600"},
                    {"if": {"row_index": "odd"}, "backgroundColor": "#f4f8fb"}]),
        ]),
    ])


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


# ── tab: methodology & transparency ───────────────────────────────────────────
def _method_item(term, defn):
    return html.Div(className="method-item", children=[
        html.Span(term, className="method-term"), html.Span(defn)])


def tab_methodology():
    return html.Div([
        html.Div(className="kpi-row", children=[
            kpi_card("Data last refreshed", REFRESH["latest_month"],
                     "latest published RTT month", "🗓️"),
            kpi_card("History covered",
                     f"{REFRESH['months']} months",
                     f"from {REFRESH['earliest_month']}", "📚"),
            kpi_card("Update frequency", "Monthly",
                     "published ~6 wks in arrears", "🔄"),
            kpi_card("Sources", "England + Scotland",
                     "NHS England · Public Health Scotland", "🏛️"),
        ]),
        html.Div(className="callout", children=[
            html.B("Why might this differ from my own experience?  "),
            html.Span(
                "These are published, provider-level figures. Your personal wait "
                "depends on your specific condition, clinical urgency, the exact "
                "clinic, and when you were referred. A provider's median means half "
                "of patients waited less and half waited longer — individual waits "
                "vary widely around it. Treat these numbers as a guide for "
                "conversations with your GP, not a guarantee."),
        ]),
        html.Div(className="card method", children=[
            html.H4("What the numbers mean", className="card-title"),
            _method_item("RTT incomplete pathways",
                         "Patients still waiting to start treatment at month-end, "
                         "by provider and specialty (treatment function)."),
            _method_item("Median wait",
                         "The middle wait in weeks — half of patients on the list "
                         "have waited less, half longer. Used as the headline figure "
                         "because it is less skewed by very long waits than the mean."),
            _method_item("National / regional average",
                         "Patient-weighted average of provider medians (providers "
                         "with bigger lists count more). Labelled as an average, not "
                         "an exact national median, which needs the full distribution."),
            _method_item("% within 18 weeks",
                         "Share of the waiting list within the 18-week referral-to-"
                         "treatment standard. The NHS constitutional target is 92%."),
            _method_item("4-hour A&E performance",
                         "Share of A&E attendances admitted, transferred or "
                         "discharged within 4 hours. The operational standard is 95% "
                         "in both England and Scotland."),
            _method_item("6-month trend",
                         "Change in a provider's median wait versus six months "
                         "earlier. ▼ means the wait fell (improving)."),
            _method_item("Scotland health board",
                         "NHS Scotland A&E is reported by Public Health Scotland for "
                         "14 territorial health boards (e.g. NHS Lothian). Figures are "
                         "aggregated here from treatment-location level to board level "
                         "and cover Type 1 (major ED) and Type 3 (minor injury) units."),
            _method_item("England vs Scotland comparison",
                         "Both nations use the same 4-hour standard, so all-type "
                         "performance is broadly comparable — but coding, department "
                         "mix and reporting calendars differ slightly, so read the "
                         "comparison as indicative of direction, not an exact gap."),
        ]),
        html.Div(className="card method", children=[
            html.H4("Caveats & limitations", className="card-title"),
            html.Ul([
                html.Li("\"Region\" is the NHS England region of the provider, not "
                        "travel distance — a provider in your region may still be far away."),
                html.Li("Some providers don't report every month; gaps are excluded "
                        "rather than guessed."),
                html.Li("Revised figures are used where the source body has republished them."),
                html.Li("England RTT/A&E and Scotland A&E come from separate national "
                        "collections (NHS England and Public Health Scotland) with their "
                        "own definitions; cross-nation figures are indicative."),
                html.Li("This tool is for information only and is not medical advice "
                        "or affiliated with NHS England or Public Health Scotland."),
            ]),
        ]),
        html.Div(className="card method", children=[
            html.H4("Sources", className="card-title"),
            html.Ul([
                html.Li(dcc.Link("NHS England — A&E Attendances & Emergency Admissions",
                        href="https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/",
                        target="_blank")),
                html.Li(dcc.Link("NHS England — RTT (Referral to Treatment) Waiting Times",
                        href="https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/",
                        target="_blank")),
                html.Li(dcc.Link("Public Health Scotland — A&E Activity & Waiting Times",
                        href="https://publichealthscotland.scot/publications/accident-and-emergency-activity-and-waiting-times/",
                        target="_blank")),
            ]),
        ]),
    ])


# ── tab: Scotland ─────────────────────────────────────────────────────────────
def tab_scotland():
    yoy = SCOT["yoy"]
    yoy_txt = f"{yoy:+.1f} pts" if yoy is not None else "n/a"
    yoy_tone = "good" if (yoy or 0) >= 0 else "bad"
    yoy_icon = "📈" if (yoy or 0) >= 0 else "📉"
    return html.Div([
        html.P("NHS Scotland A&E performance from Public Health Scotland — the same "
               "4-hour standard as England, across 14 territorial health boards. "
               "The comparison below puts the two nations side by side.",
               className="lead"),
        html.Div(className="kpi-row", children=[
            kpi_card("Scotland 4-hour performance",
                     f"{SCOT['latest_pct']:.1f}%", SCOT["latest_period"], "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
            kpi_card("Change vs a year ago", yoy_txt, "all A&E types",
                     yoy_icon, yoy_tone),
            kpi_card("Best health board", f"{SCOT['best_board'][1]:.1f}%",
                     f"NHS {SCOT['best_board'][0]}", "🏆", "good"),
            kpi_card("Most pressured board", f"{SCOT['worst_board'][1]:.1f}%",
                     f"NHS {SCOT['worst_board'][0]}", "⚠️", "bad"),
            kpi_card("Health boards", f"{SCOT['n_boards']}",
                     "territorial NHS boards", "🏥"),
        ]),
        html.Div(className="callout", children=[
            html.B("🆚 Cross-border view:  "),
            html.Span("Scotland historically outperformed England on the 4-hour "
                      "standard, but both nations fell sharply after 2021. The chart "
                      "below tracks them on the same axis — useful context whether "
                      "you're benchmarking NHS Scotland or comparing systems.")]),
        graph(charts.nations_comparison_chart()),
        graph(charts.scotland_performance_chart()),
        graph(charts.scotland_ranking_chart()),
        html.Div(className="controls", children=[
            html.Label("Explore a health board:"),
            dcc.Dropdown(id="scot-board", options=SCOT_BOARDS,
                         value="Lothian" if "Lothian" in SCOT_BOARDS
                         else SCOT_BOARDS[0], clearable=False),
        ]),
        dcc.Loading(dcc.Graph(id="scot-board-graph",
                    config={"displayModeBar": False}, className="card"),
                    type="dot", color=BLUE),
        graph(charts.scotland_heatmap_chart()),
    ])


@app.callback(Output("scot-board-graph", "figure"), Input("scot-board", "value"))
def update_scotland(hb_name):
    return charts.scotland_board_chart(hb_name or SCOT_BOARDS[0])


# ── layout ────────────────────────────────────────────────────────────────────
app.layout = html.Div(className="app", children=[
    html.Header(className="header", children=[
        html.Div([
            html.H1("UK NHS Waiting Times"),
            html.P("A&E 4-hour performance & RTT 18-week waits · England + Scotland",
                   className="subtitle"),
        ]),
        html.Div(className="header-stats", children=[
            html.Div(className="header-stat", children=[
                html.Span(f"{KPI['latest_pct']:.1f}%"),
                html.Small(f"🏴󠁧󠁢󠁥󠁮󠁧󠁿 England · {KPI['latest_period']}"),
            ]),
            html.Div(className="header-stat", children=[
                html.Span(f"{SCOT['latest_pct']:.1f}%"),
                html.Small(f"🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland · {SCOT['latest_period']}"),
            ]),
        ]),
    ]),
    dcc.Tabs(id="tabs", value="decision", className="tabs", children=[
        dcc.Tab(label="⚡  Find shortest wait", value="decision"),
        dcc.Tab(label="🏥  National overview", value="overview"),
        dcc.Tab(label="📊  Trends & statistics", value="trends"),
        dcc.Tab(label="🏨  Trust explorer", value="trust"),
        dcc.Tab(label="🗺️  Regional", value="regional"),
        dcc.Tab(label="🩺  RTT specialties", value="rtt"),
        dcc.Tab(label="🏴󠁧󠁢󠁳󠁣󠁴󠁿  Scotland", value="scotland"),
        dcc.Tab(label="🔗  A&E ↔ RTT correlation", value="corr"),
        dcc.Tab(label="ℹ️  Methodology", value="method"),
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
        "decision": tab_decision,
        "overview": tab_overview,
        "trends": tab_trends,
        "trust": tab_trust,
        "regional": tab_regional,
        "rtt": tab_rtt,
        "scotland": tab_scotland,
        "corr": tab_correlation,
        "method": tab_methodology,
    }[tab]()


if __name__ == "__main__":
    app.run(debug=True, port=8050)
