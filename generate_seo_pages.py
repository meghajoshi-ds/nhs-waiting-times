"""
Generate SEO-friendly static HTML pages from the waiting-times data.

The Dash app is a JavaScript single-page app, which search engines index poorly.
This script pre-renders one crawlable static page per specialty (national) and per
specialty x region — e.g. "ENT waiting times in London" — each with a unique
<title>, meta description, Open Graph tags, JSON-LD structured data, a key-stats
table, and a link through to the live interactive tool.

    python generate_seo_pages.py
    python generate_seo_pages.py --base-url https://your-app.onrender.com

Output goes to seo_pages/ (index.html, one page each, sitemap.xml, robots.txt,
seo.css). Host that folder, or wire it to the Dash app as static routes.
"""

import argparse
import html
import json
import re
from datetime import date
from pathlib import Path

from src import decision

OUT = Path("seo_pages")
DEFAULT_BASE = "https://nhs-waiting-times.onrender.com"


def slug(text):
    text = re.sub(r"\bService\b", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-+", "-", text)


def esc(text):
    return html.escape(str(text))


# ── page template ─────────────────────────────────────────────────────────────
def render_page(title, meta_desc, h1, intro, table_rows, faqs, canonical,
                tool_url, refreshed):
    rows_html = "\n".join(
        f"<tr><td>{esc(r['provider'])}</td><td>{esc(r['region'])}</td>"
        f"<td class='num'>{esc(r['wait'])}</td><td class='num'>{esc(r['vs'])}</td>"
        f"<td>{esc(r['trend'])}</td></tr>" for r in table_rows)

    faq_html = "\n".join(
        f"<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>"
        for q, a in faqs)

    faq_ld = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a}}
                       for q, a in faqs]}

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(meta_desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(meta_desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta name="robots" content="index,follow">
<link rel="stylesheet" href="seo.css">
<script type="application/ld+json">{json.dumps(faq_ld)}</script>
</head>
<body>
<header><a class="brand" href="index.html">NHS Waiting Times</a>
<a class="cta" href="{esc(tool_url)}">Open the interactive tool →</a></header>
<main>
<h1>{esc(h1)}</h1>
<p class="updated">Data: NHS England RTT · last updated {esc(refreshed)}</p>
<p class="intro">{intro}</p>
<table>
<thead><tr><th>Provider</th><th>Region</th><th>Median wait</th>
<th>vs national</th><th>6-month trend</th></tr></thead>
<tbody>
{rows_html}
</tbody>
</table>
<p><a class="cta big" href="{esc(tool_url)}">Compare all providers in the live tool →</a></p>
<h2>Frequently asked questions</h2>
{faq_html}
</main>
<footer>Source: <a href="https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/">NHS England RTT statistics</a>.
Figures are published provider medians and are for information only — not medical advice.</footer>
</body>
</html>
"""


def build_one(specialty, region_code, refreshed, base_url):
    s = decision.recommendation_summary(specialty, region_code)
    if s is None:
        return None
    df = decision.provider_recommendations(specialty, region_code)
    if df.empty:
        return None

    spec_short = specialty.replace(" Service", "")
    region = s["region"]
    is_national = region_code in (None, "ALL")
    where = "England" if is_national else region

    title = f"{spec_short} waiting times in {where} ({refreshed}) | NHS RTT data"
    meta = (f"Median {spec_short} waiting time in {where} is about "
            f"{s['scope_avg']:.0f} weeks ({refreshed}). Fastest provider: "
            f"{s['fastest_name']} at {s['fastest_wait']:.0f} weeks. "
            f"Compare {s['n_providers']} NHS providers and find the shortest wait.")
    h1 = f"{spec_short} waiting times in {where}"

    intro = (f"As of <strong>{esc(refreshed)}</strong>, the median wait to start "
             f"{esc(spec_short.lower())} treatment in {esc(where)} is about "
             f"<strong>{s['scope_avg']:.0f} weeks</strong> across "
             f"{s['n_providers']} NHS providers. The fastest is "
             f"<strong>{esc(s['fastest_name'])}</strong> at about "
             f"<strong>{s['fastest_wait']:.0f} weeks</strong> — roughly "
             f"{abs(s['fastest_vs_national'])}% below the national average. "
             f"Choosing the fastest provider over the {esc(where)} average could "
             f"save around <strong>{s['weeks_saved']:.0f} weeks</strong>. "
             f"You have a legal right to choose your provider for most planned care.")

    rows = [{
        "provider": r["provider_name"].title(),
        "region": r["region"],
        "wait": f"{r['median_wait_wks']:.0f} wks",
        "vs": f"{r['vs_national_pct']:+.0f}%" if r["vs_national_pct"] == r["vs_national_pct"] else "—",
        "trend": ("▼ improving" if r["direction"] == "improving"
                  else "▲ worsening" if r["direction"] == "worsening" else "– stable"),
    } for _, r in df.head(10).iterrows()]

    faqs = [
        (f"What is the average {spec_short.lower()} waiting time in {where}?",
         f"The median wait is about {s['scope_avg']:.0f} weeks as of {refreshed}, "
         f"meaning half of patients waited less and half waited longer. This is the "
         f"patient-weighted average of provider medians from NHS England RTT data."),
        (f"Which {where} provider has the shortest {spec_short.lower()} wait?",
         f"{s['fastest_name']} has the shortest median wait at about "
         f"{s['fastest_wait']:.0f} weeks — around {abs(s['fastest_vs_national'])}% "
         f"below the national average."),
        ("Can I choose which hospital treats me?",
         "For most planned (non-urgent) treatment in England you have a legal right "
         "to choose your provider, including one with a shorter wait. Ask your GP to "
         "refer you to the provider you prefer."),
        ("Why might my actual wait be different?",
         "Median figures describe the whole waiting list. Your wait depends on your "
         "specific condition, clinical urgency and referral date, so individual "
         "waits vary widely around the median."),
    ]

    canonical = f"{base_url.rstrip('/')}/seo/{slug(specialty)}-waiting-times" + \
                ("" if is_national else f"-{slug(region)}") + ".html"
    fname = (f"{slug(specialty)}-waiting-times"
             + ("" if is_national else f"-{slug(region)}") + ".html")

    page_kwargs = dict(title=title, meta_desc=meta, h1=h1, intro=intro,
                       table_rows=rows, faqs=faqs, canonical=canonical,
                       tool_url=base_url, refreshed=refreshed)
    return fname, render_page(**page_kwargs), {
        "fname": fname, "title": h1, "where": where, "spec": spec_short,
        "wait": s["scope_avg"], "national": is_national}


# ── index + sitemap + assets ──────────────────────────────────────────────────
def write_index(pages, refreshed):
    by_spec = {}
    for p in pages:
        by_spec.setdefault(p["spec"], []).append(p)
    blocks = []
    for spec in sorted(by_spec):
        items = sorted(by_spec[spec], key=lambda x: (not x["national"], x["where"]))
        links = "\n".join(
            f"<li><a href='{esc(p['fname'])}'>{esc(p['where'])}</a> "
            f"<span class='w'>~{p['wait']:.0f} wks</span></li>" for p in items)
        blocks.append(f"<section><h2>{esc(spec)}</h2><ul class='grid'>{links}</ul></section>")
    body = "\n".join(blocks)
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>NHS Waiting Times by Specialty & Region | RTT data {esc(refreshed)}</title>
<meta name="description" content="Browse NHS England waiting times by specialty and region. Median waits, fastest providers and weeks you could save — updated monthly from RTT data.">
<link rel="stylesheet" href="seo.css"></head><body>
<header><a class="brand" href="index.html">NHS Waiting Times</a></header>
<main><h1>NHS waiting times by specialty &amp; region</h1>
<p class="intro">Median referral-to-treatment waits across NHS England, by specialty
and region, from official RTT data (last updated {esc(refreshed)}). Pick a page to
see the fastest providers and how many weeks you could save.</p>
{body}</main>
<footer>Source: NHS England RTT statistics. For information only — not medical advice.</footer>
</body></html>"""


def write_sitemap(pages, base_url):
    today = date.today().isoformat()
    urls = [f"{base_url.rstrip('/')}/seo/index.html"]
    urls += [f"{base_url.rstrip('/')}/seo/{p['fname']}" for p in pages]
    items = "\n".join(
        f"  <url><loc>{esc(u)}</loc><lastmod>{today}</lastmod>"
        f"<changefreq>monthly</changefreq></url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{items}\n</urlset>\n")


SEO_CSS = """*{box-sizing:border-box}body{margin:0;font-family:Inter,Arial,sans-serif;
color:#1d2935;background:#eef3f7;line-height:1.55}
header{display:flex;justify-content:space-between;align-items:center;
background:linear-gradient(120deg,#003087,#0072CE);color:#fff;padding:16px 24px}
.brand{color:#fff;font-weight:800;font-size:18px;text-decoration:none}
.cta{background:#fff;color:#005EB8;padding:8px 14px;border-radius:8px;
text-decoration:none;font-weight:600}.cta.big{display:inline-block;background:#005EB8;
color:#fff;margin:18px 0;padding:12px 20px}
main{max-width:880px;margin:24px auto;padding:0 18px}
h1{color:#003087;font-size:28px}h2{color:#003087;margin-top:28px}
.intro{font-size:17px}.updated{color:#768692;font-size:13px;margin-top:-6px}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;
overflow:hidden;box-shadow:0 4px 20px rgba(0,48,135,.08);margin:14px 0}
th{background:#005EB8;color:#fff;text-align:left;padding:10px;font-size:14px}
td{padding:9px 10px;border-top:1px solid #eef2f5;font-size:14px}
td.num{text-align:right;font-variant-numeric:tabular-nums}
tr:nth-child(even) td{background:#f4f8fb}
details{background:#fff;border-radius:8px;padding:12px 16px;margin:8px 0;
box-shadow:0 2px 10px rgba(0,48,135,.06)}summary{font-weight:600;cursor:pointer;color:#003087}
.grid{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}
.grid a{color:#005EB8;text-decoration:none;font-weight:600}.grid .w{color:#768692;font-weight:400;font-size:13px}
section{background:#fff;border-radius:10px;padding:14px 20px;margin:14px 0;box-shadow:0 4px 20px rgba(0,48,135,.06)}
footer{max-width:880px;margin:30px auto;padding:18px;color:#768692;font-size:13px;
border-top:1px solid #d8dde0}footer a{color:#005EB8}
"""


def main():
    ap = argparse.ArgumentParser(description="Generate SEO static pages")
    ap.add_argument("--base-url", default=DEFAULT_BASE,
                    help="public URL of the live tool (for canonical links / CTA)")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    refreshed = decision.last_refresh()["latest_month"]
    specs = decision.specialties()
    region_codes = ["ALL"] + list(decision.REGION_NAMES)

    pages, written = [], 0
    for spec in specs:
        for rc in region_codes:
            built = build_one(spec, rc, refreshed, args.base_url)
            if not built:
                continue
            fname, html_text, meta = built
            (OUT / fname).write_text(html_text, encoding="utf-8")
            pages.append(meta)
            written += 1

    (OUT / "index.html").write_text(write_index(pages, refreshed), encoding="utf-8")
    (OUT / "sitemap.xml").write_text(write_sitemap(pages, args.base_url), encoding="utf-8")
    (OUT / "seo.css").write_text(SEO_CSS, encoding="utf-8")
    (OUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {args.base_url.rstrip('/')}/seo/sitemap.xml\n",
        encoding="utf-8")

    print(f"Generated {written} pages + index + sitemap in {OUT}/")
    print(f"Specialties: {len(specs)} · scopes per specialty: {len(region_codes)}")


if __name__ == "__main__":
    main()
