"""
Plotly figure factories. Every function returns a go.Figure so the Dash app
(and the notebooks) stay thin. Shared styling lives in `_layout`.
"""

import plotly.graph_objects as go
import plotly.express as px

from . import analysis, stats, decision

# NHS-ish palette
BLUE = "#005EB8"      # NHS blue
DARK = "#003087"
BRIGHT = "#0072CE"
CYAN = "#00A9CE"
RED = "#DA291C"
GREEN = "#009639"
AMBER = "#FFB81C"
GREY = "#768692"
COVID_START, COVID_END = "2020-03-01", "2021-06-01"

FONT = "Inter, Arial, sans-serif"


def _layout(fig, title=None, height=420):
    fig.update_layout(
        title=dict(text=title, font=dict(size=18, color=DARK, family=FONT),
                   x=0.01, xanchor="left") if title else None,
        template="plotly_white",
        height=height,
        margin=dict(l=60, r=30, t=64 if title else 30, b=50),
        font=dict(family=FONT, size=13, color="#1d2935"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="white", font_size=13, font_family=FONT,
                        bordercolor=BLUE),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        transition=dict(duration=400, easing="cubic-in-out"),
    )
    fig.update_xaxes(showgrid=False, showline=True, linecolor="#dde3e8")
    fig.update_yaxes(gridcolor="#eef2f5", zeroline=False)
    return fig


def _covid_band(fig):
    fig.add_vrect(x0=COVID_START, x1=COVID_END, fillcolor=GREY, opacity=0.10,
                  line_width=0, annotation_text="COVID-19",
                  annotation_position="top left",
                  annotation_font_size=11, annotation_font_color=GREY)
    return fig


def _timeaxis(fig):
    """Add compact range-selector buttons to a date x-axis."""
    fig.update_xaxes(rangeselector=dict(
        buttons=[
            dict(count=1, label="1Y", step="year", stepmode="backward"),
            dict(count=3, label="3Y", step="year", stepmode="backward"),
            dict(count=5, label="5Y", step="year", stepmode="backward"),
            dict(step="all", label="All"),
        ],
        bgcolor="#eef3f7", activecolor=BLUE, font=dict(size=11),
        x=1, y=1.12, xanchor="right"))
    return fig


# ── National overview ─────────────────────────────────────────────────────────
def national_performance_chart():
    df = analysis.national_performance("2012-01-01")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["period"], y=df["pct_within_4hrs"], mode="lines",
        name="All A&E types", line=dict(color=BLUE, width=3, shape="spline",
                                        smoothing=0.4),
        fill="tozeroy", fillcolor="rgba(0,94,184,0.07)",
        hovertemplate="%{y:.1f}% within 4h<extra></extra>"))
    fig.add_hline(y=95, line=dict(color=RED, dash="dash", width=1.5),
                  annotation_text="95% target", annotation_position="top right",
                  annotation_font_color=RED)
    _covid_band(fig)
    _timeaxis(fig)
    fig.update_yaxes(title="% seen within 4 hours", range=[40, 100], ticksuffix="%")
    return _layout(fig, "National A&E 4-hour performance vs 95% target")


def attendance_chart():
    df = analysis.national_performance("2012-01-01")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["period"], y=df["att_total"], mode="lines", name="Total attendances",
        line=dict(color=BRIGHT, width=2.5, shape="spline", smoothing=0.4),
        fill="tozeroy", fillcolor="rgba(0,114,206,0.10)",
        hovertemplate="%{y:,.0f} attendances<extra></extra>"))
    _covid_band(fig)
    _timeaxis(fig)
    fig.update_yaxes(title="Monthly A&E attendances")
    return _layout(fig, "National A&E attendance volume")


# ── Trends & statistics ───────────────────────────────────────────────────────
def decomposition_chart():
    df = analysis.national_performance("2012-01-01")
    dec = stats.decompose(df, "pct_within_4hrs").reset_index()
    fig = go.Figure()
    for col, color, name in [("observed", BLUE, "Observed"),
                             ("trend", RED, "Trend"),
                             ("seasonal", GREEN, "Seasonal"),
                             ("residual", GREY, "Residual")]:
        fig.add_trace(go.Scatter(x=dec["period"], y=dec[col], mode="lines",
                                 name=name, line=dict(color=color, width=1.8)))
    fig.update_yaxes(title="% within 4 hours (decomposed)")
    return _layout(fig, "Seasonal decomposition of national 4-hour performance",
                   height=460)


def seasonal_index_chart():
    df = analysis.seasonal_index()
    colors = [RED if v > 100 else BLUE for v in df["index"]]
    fig = go.Figure(go.Bar(
        x=df["month_name"], y=df["index"], marker_color=colors,
        marker_line_width=0, text=df["index"].round(0), textposition="outside",
        hovertemplate="%{x}: index %{y:.0f}<extra></extra>"))
    fig.add_hline(y=100, line=dict(color=GREY, dash="dot"))
    fig.update_yaxes(title="Seasonal index (100 = average month)", range=[90, 110])
    return _layout(fig, "A&E attendance seasonality (pre-COVID 2015-2019)")


# ── Trust explorer ────────────────────────────────────────────────────────────
def trust_chart(org_name):
    df = analysis.trust_timeseries(org_name)
    nat = analysis.national_type1_monthly()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=nat["period"], y=nat["pct"], mode="lines",
                             name="National (Type 1)",
                             line=dict(color=GREY, width=1.8, dash="dot"),
                             hovertemplate="National: %{y:.1f}%<extra></extra>"))
    fig.add_trace(go.Scatter(x=df["period"], y=df["pct_within_4hrs_t1"],
                             mode="lines", name=org_name,
                             line=dict(color=BLUE, width=3, shape="spline",
                                       smoothing=0.4),
                             fill="tonexty", fillcolor="rgba(0,94,184,0.06)",
                             hovertemplate="This trust: %{y:.1f}%<extra></extra>"))
    fig.add_hline(y=95, line=dict(color=RED, dash="dash", width=1))
    _covid_band(fig)
    _timeaxis(fig)
    fig.update_yaxes(title="% Type-1 within 4 hours", range=[0, 100], ticksuffix="%")
    return _layout(fig, f"{org_name} — Type-1 4-hour performance vs national")


def trust_attendance_chart(org_name):
    df = analysis.trust_timeseries(org_name)
    fig = go.Figure(go.Bar(
        x=df["period"], y=df["att_type1"],
        marker=dict(color=df["att_type1"], colorscale=[[0, CYAN], [1, DARK]],
                    line_width=0),
        name="Type-1 attendances",
        hovertemplate="%{x|%b %Y}: %{y:,.0f}<extra></extra>"))
    fig.update_yaxes(title="Type-1 attendances / month")
    return _layout(fig, "Monthly Type-1 attendance volume", height=320)


def worst_trusts_chart():
    df = analysis.worst_trusts(limit=15)
    df = df.sort_values("avg_performance")
    fig = go.Figure(go.Bar(
        x=df["avg_performance"], y=df["org_name"], orientation="h",
        marker=dict(color=df["avg_performance"], colorscale="RdYlGn",
                    cmin=0, cmax=60, line_width=0),
        text=df["avg_performance"].round(1).astype(str) + "%",
        textposition="outside",
        hovertemplate="%{y}<br>%{x:.1f}% within 4h<extra></extra>"))
    fig.update_xaxes(title="Avg Type-1 4-hour performance (last 12 months)",
                     range=[0, 100], ticksuffix="%")
    fig.update_layout(yaxis=dict(autorange="reversed"))
    return _layout(fig, "15 lowest-performing trusts (12-month average)", height=520)


# ── Regional ──────────────────────────────────────────────────────────────────
def regional_heatmap_chart():
    df = analysis.regional_heatmap()
    pivot = df.pivot(index="region", columns="period", values="pct")
    pivot = pivot.reindex(pivot.mean(axis=1).sort_values().index)  # worst on top
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[p.strftime("%b %y") for p in pivot.columns],
        y=pivot.index,
        colorscale="RdYlGn", zmin=40, zmax=95,
        xgap=2, ygap=2,
        colorbar=dict(title="% &lt;4h", ticksuffix="%"),
        hovertemplate="%{y}<br>%{x}: %{z:.1f}%<extra></extra>"))
    return _layout(fig, "Type-1 4-hour performance by NHS region (last 24 months)",
                   height=460)


def regional_latest_bar():
    df = analysis.regional_heatmap()
    latest = df[df["period"] == df["period"].max()].sort_values("pct")
    fig = go.Figure(go.Bar(
        x=latest["pct"], y=latest["region"], orientation="h",
        marker=dict(color=latest["pct"], colorscale="RdYlGn", cmin=40, cmax=95,
                    line_width=0),
        text=latest["pct"].round(1).astype(str) + "%", textposition="outside",
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
    fig.add_vline(x=95, line=dict(color=RED, dash="dash"))
    fig.update_xaxes(title="% Type-1 within 4 hours", range=[0, 100], ticksuffix="%")
    title = f"Latest month by region ({latest['period'].max():%B %Y})"
    return _layout(fig, title, height=420)


# ── RTT ───────────────────────────────────────────────────────────────────────
def rtt_specialty_bar():
    df = analysis.rtt_specialty_latest(12)
    df = df.sort_values("pct_over_18wk")
    label = df["latest_period"].iloc[0] if len(df) else ""
    fig = go.Figure(go.Bar(
        x=df["pct_over_18wk"], y=df["treatment_function"], orientation="h",
        marker=dict(color=df["pct_over_18wk"], colorscale=[[0, AMBER], [1, RED]],
                    line_width=0),
        text=df["pct_over_18wk"].round(1).astype(str) + "%", textposition="outside",
        hovertemplate="%{y}<br>%{x:.1f}% over 18 wks<extra></extra>"))
    fig.update_xaxes(title="% waiting more than 18 weeks", ticksuffix="%")
    fig.update_layout(yaxis=dict(autorange="reversed"))
    return _layout(fig, f"Worst specialties by 18-week breach ({label})", height=460)


def rtt_trend_chart(specialties=None):
    df = analysis.rtt_specialty_trend(specialties)
    fig = go.Figure()
    palette = px.colors.qualitative.Bold
    for i, (name, g) in enumerate(df.groupby("treatment_function")):
        fig.add_trace(go.Scatter(
            x=g["period"], y=g["pct_over_18wk"], mode="lines+markers",
            name=name, line=dict(width=2.5, color=palette[i % len(palette)],
                                 shape="spline", smoothing=0.4),
            marker=dict(size=5),
            hovertemplate=name + ": %{y:.1f}%<extra></extra>"))
    fig.update_yaxes(title="% waiting over 18 weeks", ticksuffix="%")
    return _layout(fig, "RTT 18-week breaches over time by specialty")


def rtt_national_chart():
    df = analysis.rtt_national_trend()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["period"], y=df["total_waiting"], name="Total waiting list",
        marker=dict(color="rgba(0,114,206,0.35)", line_width=0), yaxis="y",
        hovertemplate="%{x|%b %Y}: %{y:,.0f} waiting<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=df["period"], y=df["pct_within_18wk"], name="% within 18 wks",
        line=dict(color=RED, width=3, shape="spline", smoothing=0.4), yaxis="y2",
        hovertemplate="%{y:.1f}% within 18 wks<extra></extra>"))
    fig.update_layout(
        yaxis=dict(title="Total incomplete pathways"),
        yaxis2=dict(title="% within 18 weeks", overlaying="y", side="right",
                    range=[0, 100], ticksuffix="%", showgrid=False))
    return _layout(fig, "National RTT waiting list size vs 18-week compliance")


# ── Decision support ──────────────────────────────────────────────────────────
def fastest_providers_chart(specialty, region="ALL", top_n=12):
    """Horizontal bar of the fastest providers, green=improving, red=worsening."""
    df = decision.provider_recommendations(specialty, region)
    if df.empty:
        return _layout(go.Figure().add_annotation(
            text="No data for this selection", showarrow=False), height=300)
    national = float(df["national_avg"].iloc[0])
    df = df.head(top_n).iloc[::-1]                  # fastest at top
    colors = df["direction"].map({"improving": GREEN, "worsening": RED,
                                  "stable": GREY}).fillna(GREY)
    fig = go.Figure(go.Bar(
        x=df["median_wait_wks"], y=df["provider_name"].str.title(),
        orientation="h", marker=dict(color=colors, line_width=0),
        text=df["median_wait_wks"].round(1).astype(str) + " wks",
        textposition="outside",
        customdata=df[["direction", "percentile"]].values,
        hovertemplate="%{y}<br>%{x:.1f} weeks · %{customdata[0]}"
                      "<br>faster than %{customdata[1]:.0f}% of providers<extra></extra>"))
    fig.add_vline(x=national, line=dict(color=DARK, dash="dash"),
                  annotation_text=f"National avg {national:.0f} wks",
                  annotation_position="top")
    region_lbl = decision.region_name(region)
    fig.update_xaxes(title="Median wait (weeks) — shorter is better")
    return _layout(fig, f"Fastest providers · {specialty.replace(' Service','')} · "
                        f"{region_lbl}", height=460)


def specialty_trend_chart(specialty):
    """National median wait + 18-week compliance trend for a specialty."""
    df = decision.specialty_national_trend(specialty)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["period"], y=df["median_wait"], mode="lines+markers",
        name="Median wait (weeks)", line=dict(color=BLUE, width=3, shape="spline",
                                              smoothing=0.4),
        fill="tozeroy", fillcolor="rgba(0,94,184,0.07)", marker=dict(size=5),
        hovertemplate="%{x|%b %Y}: %{y:.1f} weeks<extra></extra>"))
    fig.add_hline(y=18, line=dict(color=RED, dash="dash", width=1),
                  annotation_text="18-week standard", annotation_position="top right",
                  annotation_font_color=RED)
    fig.update_yaxes(title="Median wait (weeks)")
    return _layout(fig, f"National median wait over time · "
                        f"{specialty.replace(' Service','')}", height=340)


def correlation_chart():
    df = analysis.admission_vs_rtt()
    res = stats.pearson(df["ae_perf"], df["rtt_perf"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["ae_perf"], y=df["rtt_perf"], mode="markers",
        marker=dict(size=11, color=df["waiting"], colorscale="Viridis",
                    opacity=0.78, line=dict(width=1, color="white"),
                    colorbar=dict(title="RTT<br>waiting")),
        text=df["org_name"], hovertemplate="%{text}<br>A&E: %{x:.1f}%<br>"
        "RTT: %{y:.1f}%<extra></extra>", name="Trust"))
    if res.get("r") is not None:
        xs = [df["ae_perf"].min(), df["ae_perf"].max()]
        ys = [res["slope"] * x + res["intercept"] for x in xs]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name="Best fit",
                                 line=dict(color=RED, dash="dash", width=2)))
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(title="A&E Type-1 4-hour performance (%)", ticksuffix="%")
    fig.update_yaxes(title="RTT 18-week performance (%)", ticksuffix="%")
    sub = (f"r = {res['r']:.2f}, p = {res['p_value']:.3g}, n = {res['n']}"
           if res.get("r") is not None else "")
    return _layout(fig, f"A&E vs RTT performance by trust ({sub})"), res
