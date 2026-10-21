"""The NAV pack: one HTML page for the valuation date and the period behind
it, plus CSV files of everything the run produced.

The page has no external resources, so it can be emailed or archived as is.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import math
import pathlib

import pandas as pd

from .engine import RunResult
from .models import AGE_BUCKETS

# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def _minus(text: str) -> str:
    return text.replace("-", "−")


def money(value: float, digits: int = 2) -> str:
    if abs(value) < 0.5 * 10 ** -digits:
        value = 0.0  # no "-0.00"
    return _minus(f"{value:,.{digits}f}")


def millions(value: float) -> str:
    return _minus(f"{value / 1e6:,.2f}m")


def pct(value: float, digits: int = 2, sign: bool = False) -> str:
    return _minus(f"{value:+.{digits}%}" if sign else f"{value:.{digits}%}")


def fmt_date(day: dt.date) -> str:
    return f"{day:%b} {day.day}, {day.year}"


def plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


# ---------------------------------------------------------------------------
# Small pieces
# ---------------------------------------------------------------------------


def icon(status: str, size: int = 14) -> str:
    if status == "ok":
        glyph = '<circle cx="8" cy="8" r="7.5" fill="currentColor"/><path d="M4.6 8.3l2.2 2.2 4.6-4.8" fill="none" style="stroke:var(--surface)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    elif status == "warning":
        glyph = '<path d="M8 .9l7.3 13.4H.7z" fill="currentColor"/><rect x="7.1" y="5.2" width="1.8" height="5" rx=".9" style="fill:var(--surface)"/><circle cx="8" cy="12.2" r="1" style="fill:var(--surface)"/>'
    else:
        glyph = '<path d="M5.1.6h5.8l4.5 4.5v5.8l-4.5 4.5H5.1L.6 10.9V5.1z" fill="currentColor"/><path d="M5.4 5.4l5.2 5.2M10.6 5.4l-5.2 5.2" style="stroke:var(--surface)" stroke-width="1.8" stroke-linecap="round"/>'
    return f'<svg class="icon icon-{status}" width="{size}" height="{size}" viewBox="0 0 16 16" aria-hidden="true">{glyph}</svg>'


def chip(status: str, label: str) -> str:
    return f'<span class="chip">{icon(status)}<span>{_esc(label)}</span></span>'


def table(headers: list[str], rows: list[list[str]], numeric: set[int] = frozenset(), empty: str = "Nothing to show.") -> str:
    if not rows:
        return f'<p class="empty">{_esc(empty)}</p>'
    head = "".join(f'<th class="num">{h}</th>' if i in numeric else f"<th>{h}</th>" for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f'<td class="num">{c}</td>' if i in numeric else f"<td>{c}</td>" for i, c in enumerate(r)) + "</tr>"
        for r in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _nice_step(span: float, target: int = 5) -> float:
    raw = span / max(target, 1)
    magnitude = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= mult * magnitude:
            return mult * magnitude
    return 10 * magnitude


def _ticks(lo: float, hi: float, target: int = 5) -> list[float]:
    step = _nice_step(hi - lo, target)
    v, out = math.ceil(lo / step - 1e-9) * step, []
    while v <= hi + 1e-9:
        out.append(round(v, 10))
        v += step
    return out


def _month_ticks(dates: list[dt.date], x) -> list[str]:
    """A tick and label where each month starts. The first month is labeled
    too, unless the next month starts too close to fit both."""
    starts = [i for i, day in enumerate(dates) if i == 0 or day.month != dates[i - 1].month]
    if len(starts) > 1 and starts[1] < 8:
        starts = starts[1:]
    parts = []
    for i in starts:
        day = dates[i]
        label = f"{day:%b}" if day.month != 1 else f"{day:%b} {day.year}"
        parts.append(f'<line class="tick" x1="{x(i):.1f}" x2="{x(i):.1f}" y1="0" y2="4"/>')
        parts.append(f'<text class="axis-text" x="{x(i):.1f}" y="18" text-anchor="middle">{label}</text>')
    return parts


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

SERIES = ["s1", "s2", "s3"]  # CSS classes, colors set in the stylesheet


def nav_chart(run: RunResult) -> str:
    """NAV per share for each class, indexed to 100 at the start of the period."""
    history = run.nav_history()
    codes = [sc.code for sc in run.data.config.share_classes]
    dates = [run.data.opening.date] + [d.date for d in run.days]
    series = {}
    for code in codes:
        start = run.opening_nav_per_share[code]
        values = [100.0] + [v / start * 100 for v in history.loc[history["share_class"] == code, "nav_per_share"]]
        series[code] = values
    width, height, left, right, top, bottom = 720, 260, 44, 104, 12, 28
    pw, ph = width - left - right, height - top - bottom
    lo = min(min(v) for v in series.values())
    hi = max(max(v) for v in series.values())
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    n = len(dates)

    def x(i):
        return left + i * pw / (n - 1)

    def y(v):
        return top + (hi - v) / (hi - lo) * ph

    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="NAV per share by class, indexed to 100">']
    for t in _ticks(lo, hi):
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>')
        parts.append(f'<text class="axis-text" x="{left - 8}" y="{y(t) + 4:.1f}" text-anchor="end">{t:g}</text>')
    parts.append(f'<line class="baseline" x1="{left}" x2="{width - right}" y1="{top + ph}" y2="{top + ph}"/>')
    parts.append(f'<g transform="translate(0,{top + ph})">' + "".join(_month_ticks(dates, x)) + "</g>")
    for k, code in enumerate(codes):
        path = "M" + "L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(series[code]))
        parts.append(f'<path class="line {SERIES[k]}" d="{path}"/>')
    # End labels, nudged apart when they would overlap.
    ends = sorted(((y(series[c][-1]), c, k) for k, c in enumerate(codes)), key=lambda t: t[0])
    placed = []
    for ypos, code, k in ends:
        dot_y = ypos
        if placed and ypos - placed[-1] < 14:
            ypos = placed[-1] + 14
        placed.append(ypos)
        parts.append(f'<circle class="dot {SERIES[k]}" cx="{x(n - 1):.1f}" cy="{dot_y:.1f}" r="4"/>')
        if abs(ypos - dot_y) > 2:  # pushed down to make room: a leader line keeps it tied to its line
            parts.append(f'<path class="leader" d="M{x(n - 1) + 6:.1f},{dot_y:.1f}L{x(n - 1) + 14:.1f},{ypos:.1f}"/>')
        parts.append(f'<text class="end-label" x="{x(n - 1) + 17:.1f}" y="{ypos + 4:.1f}">{_esc(code)} {series[code][-1]:.1f}</text>')
    parts.append(f'<line class="xhair" x1="0" x2="0" y1="{top}" y2="{top + ph}" visibility="hidden"/>')
    parts.append(f'<rect class="overlay" x="{left}" y="{top}" width="{pw}" height="{ph}" tabindex="0" aria-label="Use the arrow keys to step through the days"/>')
    parts.append("</svg>")
    data = {
        "kind": "line",
        "left": left,
        "step": pw / (n - 1),
        "dates": [fmt_date(d) for d in dates],
        "series": [{"label": c, "values": [round(v, 2) for v in series[c]]} for c in codes],
    }
    legend = '<div class="legend">' + "".join(
        f'<span><i class="key-line {SERIES[k]}"></i>{_esc(c)}</span>' for k, c in enumerate(codes)
    ) + "</div>"
    payload = json.dumps(data).replace("</", "<\\/")
    return (
        f'<div class="chart" data-interactive>{legend}<div class="chart-scroll">{"".join(parts)}</div>'
        f'<script type="application/json" class="chart-data">{payload}</script><div class="tip" hidden></div></div>'
    )


def breaks_chart(run: RunResult) -> str:
    """Open breaks at the end of each day, stacked by age."""
    dates = [d.date for d in run.days]
    counts = []
    for d in run.days:
        open_rows = d.register[d.register["status"] == "open"] if not d.register.empty else d.register
        counts.append([int((open_rows["bucket"] == b).sum()) if not open_rows.empty else 0 for b in AGE_BUCKETS])
    width, height, left, right, top, bottom = 720, 200, 44, 16, 12, 28
    pw, ph = width - left - right, height - top - bottom
    peak = max([sum(c) for c in counts] + [1])
    hi = max(_ticks(0, peak + 0.5, 4)[-1], 1)
    n = len(dates)
    step = pw / n
    bar = max(step - 2, 1)

    def x(i):
        return left + (i + 0.5) * step

    def y(v):
        return top + (hi - v) / hi * ph

    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Open breaks each day by age">']
    for t in _ticks(0, hi, 4):
        if t != int(t):
            continue
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>')
        parts.append(f'<text class="axis-text" x="{left - 8}" y="{y(t) + 4:.1f}" text-anchor="end">{int(t)}</text>')
    for i, c in enumerate(counts):
        base = 0
        for b, count in enumerate(c):
            if not count:
                continue
            y0, y1 = y(base), y(base + count)
            parts.append(f'<rect class="age{b}" x="{x(i) - bar / 2:.2f}" y="{y1 + 1:.2f}" width="{bar:.2f}" height="{max(y0 - y1 - 1, 0.5):.2f}"/>')
            base += count
    parts.append(f'<line class="baseline" x1="{left}" x2="{width - right}" y1="{top + ph}" y2="{top + ph}"/>')
    parts.append(f'<g transform="translate(0,{top + ph})">' + "".join(_month_ticks(dates, x)) + "</g>")
    parts.append(f'<line class="xhair" x1="0" x2="0" y1="{top}" y2="{top + ph}" visibility="hidden"/>')
    parts.append(f'<rect class="overlay" x="{left}" y="{top}" width="{pw}" height="{ph}" tabindex="0" aria-label="Use the arrow keys to step through the days"/>')
    parts.append("</svg>")
    data = {
        "kind": "bars",
        "left": left,
        "step": step,
        "dates": [fmt_date(d) for d in dates],
        "series": [{"label": f"{b} days", "values": [c[k] for c in counts]} for k, b in enumerate(AGE_BUCKETS)],
    }
    legend = '<div class="legend">' + "".join(
        f'<span><i class="key age{k}"></i>{b} days</span>' for k, b in enumerate(AGE_BUCKETS)
    ) + "</div>"
    payload = json.dumps(data).replace("</", "<\\/")
    return (
        f'<div class="chart" data-interactive>{legend}<div class="chart-scroll">{"".join(parts)}</div>'
        f'<script type="application/json" class="chart-data">{payload}</script><div class="tip" hidden></div></div>'
    )


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _class_table(run: RunResult) -> str:
    last = run.last
    prior = run.days[-2] if len(run.days) > 1 else None
    rows = []
    for sc in run.data.config.share_classes:
        v, s = last.valuations[sc.code], last.states[sc.code]
        start = run.opening_nav_per_share[sc.code]
        before = prior.valuations[sc.code].nav_per_share if prior else start
        rate = 1.0 if sc.currency == run.data.config.base_currency else last.rates[sc.currency]
        rows.append(
            [
                _esc(sc.code),
                f"{v.nav_per_share:,.4f}",
                pct(v.nav_per_share / before - 1, sign=True),
                pct(v.nav_per_share / start - 1, sign=True),
                f"{s.units:,.3f}",
                f"{sc.currency} {millions(s.nav * rate)}",
                pct(sc.management_fee),
                f"{pct(sc.performance_fee, 0)} over {s.high_water_mark:,.4f}" if sc.performance_fee else "None",
            ]
        )
    return table(
        ["Class", "NAV per share", "Day", "Period", "Units", "Class NAV", "Management fee", "Performance fee"],
        rows,
        numeric={1, 2, 3, 4, 5, 6},
    )


def _bridge(run: RunResult) -> str:
    """How each class's NAV got from the start of the period to the end, in base currency."""
    base = run.data.config.base_currency
    codes = [sc.code for sc in run.data.config.share_classes]
    lines = {
        "Opening NAV": {c: run.opening_states[c].nav for c in codes},
        "Share of fund result": {c: sum(d.allocation[c] for d in run.days) for c in codes},
        "Management fee": {c: -sum(d.valuations[c].management_fee for d in run.days) for c in codes},
        "Performance fee": {c: -sum(d.valuations[c].performance_fee_change for d in run.days) for c in codes},
        "Subscriptions": {c: sum(x["base_amount"] for d in run.days for x in d.deals if x["share_class"] == c and x["type"] == "subscription") for c in codes},
        "Redemptions": {c: -sum(x["base_amount"] for d in run.days for x in d.deals if x["share_class"] == c and x["type"] == "redemption") for c in codes},
        "Closing NAV": {c: run.last.states[c].nav for c in codes},
    }
    rows = []
    for label, values in lines.items():
        total = sum(values.values())
        cells = [money(values[c]) for c in codes] + [money(total)]
        name = f"<strong>{label}</strong>" if label in ("Opening NAV", "Closing NAV") else label
        rows.append([name, *cells])
    expenses = sum(sum(d.expenses.values()) for d in run.days)
    note = (
        f'<p class="section-intro">In {base}. The fund result covers market moves, FX and dividends, after '
        f"{money(expenses)} of shared expenses, and is split between the classes each day by their NAV at the previous valuation point.</p>"
    )
    return note + table(["", *codes, "Fund"], rows, numeric=set(range(1, len(codes) + 2)))


def _balance_sheet(run: RunResult) -> str:
    last = run.last
    rows = []
    for line, value in last.balance_sheet.items():
        if line == "Net assets":
            continue
        if value == 0 and line not in ("Investments", "Cash"):
            continue
        rows.append([line, money(value)])
    class_total = sum(s.nav for s in last.states.values())
    rows.append(["<strong>Net assets</strong>", f"<strong>{money(last.net_assets)}</strong>"])
    rows.append(["Sum of share class NAVs", money(class_total)])
    rows.append(["Difference", money(last.proof)])
    return table(["", run.data.config.base_currency], rows, numeric={1})


def _holdings(run: RunResult) -> str:
    last = run.last
    names = run.data.securities["name"]
    total = last.net_assets
    p = last.positions.sort_values("base_value", ascending=False)
    rows = [
        [
            _esc(names.get(r.isin, r.isin)),
            _esc(r.isin),
            r.currency,
            f"{r.quantity:,.0f}",
            f"{r.price:,.4f}" if r.currency == "GBP" else f"{r.price:,.2f}",
            money(r.base_value),
            pct(r.base_value / total),
        ]
        for r in p.itertuples()
    ]
    return table(["Security", "ISIN", "Currency", "Quantity", "Price", f"Value ({run.data.config.base_currency})", "Weight"], rows, numeric={3, 4, 5, 6})


def _breaks(run: RunResult) -> str:
    register = run.last.register
    names = run.data.securities["name"]

    def label(row):
        ref = row["reference"]
        return _esc(f"{names[ref]} ({ref})" if ref in names.index else ref)

    def diff(row):
        v = row["difference"]
        return "" if pd.isna(v) else money(float(v), 2 if row["category"] != "position" else 0)

    open_rows = register[register["status"] == "open"] if not register.empty else register
    resolved = register[register["status"] == "resolved"] if not register.empty else register
    open_table = table(
        ["Age", "Type", "Reference", "What differs", "Difference", "First seen"],
        [
            [
                chip("warning" if r["age"] > 5 else "ok", f'{r["age"]} days'),
                r["category"].capitalize(),
                label(r),
                _esc(r["detail"]),
                diff(r),
                fmt_date(r["first_seen"]),
            ]
            for _, r in open_rows.iterrows()
        ],
        numeric={4},
        empty="No open breaks.",
    )
    resolved_table = table(
        ["Type", "Reference", "What differed", "First seen", "Cleared", "Days open"],
        [
            [r["category"].capitalize(), label(r), _esc(r["detail"]), fmt_date(r["first_seen"]), fmt_date(r["resolved_on"]), str(r["age"] + 1)]
            for _, r in resolved.iterrows()
        ],
        numeric={5},
        empty="Nothing cleared in the period.",
    )
    return (
        f"<h3>Open on {fmt_date(run.last.date)}</h3>{open_table}"
        f"{breaks_chart(run)}"
        f"<details><summary>{plural(len(resolved), 'break', 'breaks')} cleared during the period</summary>{resolved_table}</details>"
    )


def _checks(run: RunResult) -> str:
    checks = run.checks()
    names = run.data.securities["name"]
    rows = [
        [fmt_date(c.date), _esc(c.check.capitalize()), _esc(names.get(c.reference, c.reference)), _esc(c.detail)]
        for c in checks.itertuples()
    ]
    return table(["Date", "Check", "On", "Detail"], rows, empty="No findings in the period.")


def _deals(run: RunResult) -> str:
    deals = run.deals()
    rows = [
        [
            fmt_date(d.date),
            _esc(d.deal_id),
            _esc(d.share_class),
            d.type.capitalize(),
            f"{d.nav_per_share:,.4f}",
            f"{d.units:,.3f}",
            f"{d.currency} {money(d.amount)}",
            fmt_date(d.settles),
        ]
        for d in deals.itertuples()
    ]
    return table(["Dealt", "Deal", "Class", "Type", "NAV per share", "Units", "Amount", "Settles"], rows, numeric={4, 5, 6})


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

CSS = """
:root{color-scheme:light;--page:#f5f3ed;--surface:#fcfbf8;--ink:#0b1f33;--ink-2:#4a5563;--muted:#6b7280;
--grid:#e6e3da;--axis:#c9c5b9;--rule:#c5a363;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;
--a0:#86b6ef;--a1:#3987e5;--a2:#1c5cab;--a3:#0d366b;--ok:#1c6350;--warning:#8a6414;--breach:#a1352a;--border:rgba(11,31,51,.10)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#111417;--surface:#1b1e22;
--ink:#eef0f2;--ink-2:#b9c0c8;--muted:#8a929b;--grid:#2b3036;--axis:#3a4048;--s1:#3987e5;--s2:#d95926;--s3:#199e70;
--a0:#184f95;--a1:#256abf;--a2:#5598e7;--a3:#9ec5f4;--ok:#3fae8a;--warning:#e0b04a;--breach:#e06a5c;--border:rgba(255,255,255,.10)}}
:root[data-theme="dark"]{color-scheme:dark;--page:#111417;--surface:#1b1e22;--ink:#eef0f2;--ink-2:#b9c0c8;--muted:#8a929b;
--grid:#2b3036;--axis:#3a4048;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--a0:#184f95;--a1:#256abf;--a2:#5598e7;--a3:#9ec5f4;
--ok:#3fae8a;--warning:#e0b04a;--breach:#e06a5c;--border:rgba(255,255,255,.10)}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:1000px;margin:0 auto;padding:32px 16px 48px}
.kicker{margin:0;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2)}
h1{margin:4px 0 6px;font-size:28px;line-height:1.2}
h2{margin:0 0 4px;font-size:19px}
h3{margin:14px 0 6px;font-size:15px}
.meta{margin:0;color:var(--ink-2);font-size:14px}
header{padding-bottom:18px;border-bottom:2px solid var(--rule);margin-bottom:20px}
.banner{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--rule);padding:10px 14px;border-radius:6px;margin:0 0 20px;font-size:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-bottom:24px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.tile-label{margin:0 0 6px;font-size:13px;color:var(--ink-2)}
.tile-value{margin:0 0 6px;font-size:26px;font-weight:600;line-height:1.15}
.tile-sub{margin:4px 0 0;font-size:13px;color:var(--ink-2)}
section.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px 18px 14px;margin-bottom:16px}
.section-intro{margin:0 0 12px;color:var(--ink-2);font-size:14px}
.chip{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;font-size:13px;font-weight:600}
.icon{flex:none}.icon-ok{color:var(--ok)}.icon-warning{color:var(--warning)}.icon-breach{color:var(--breach)}
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--grid);vertical-align:top}
thead th{font-size:12px;font-weight:600;color:var(--ink-2);border-bottom:1px solid var(--axis)}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
details{margin-top:12px}summary{cursor:pointer;color:var(--ink-2);font-size:14px}
.empty{color:var(--ink-2);font-size:14px}
.chart{position:relative;margin:10px 0 8px}
.chart-scroll{overflow-x:auto}
.chart-svg{display:block;width:100%;min-width:620px;height:auto;overflow:visible}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:var(--ink-2);margin:0 0 6px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.key{display:inline-block;width:12px;height:12px;border-radius:3px}
.key-line{display:inline-block;width:16px;height:0;border-top:2px solid}
.key-line.s1{border-color:var(--s1)}.key-line.s2{border-color:var(--s2)}.key-line.s3{border-color:var(--s3)}
.grid{stroke:var(--grid);stroke-width:1}
.baseline,.tick{stroke:var(--axis);stroke-width:1}
.axis-text{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.end-label{fill:var(--ink);font-size:12px;font-variant-numeric:tabular-nums}
.leader{fill:none;stroke:var(--muted);stroke-width:1}
.line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.line.s1{stroke:var(--s1)}.line.s2{stroke:var(--s2)}.line.s3{stroke:var(--s3)}
.dot{stroke:var(--surface);stroke-width:2}.dot.s1{fill:var(--s1)}.dot.s2{fill:var(--s2)}.dot.s3{fill:var(--s3)}
.age0{fill:var(--a0);background:var(--a0)}.age1{fill:var(--a1);background:var(--a1)}.age2{fill:var(--a2);background:var(--a2)}.age3{fill:var(--a3);background:var(--a3)}
.xhair{stroke:var(--ink-2);stroke-width:1}
.overlay{fill:transparent;outline:none}.overlay:focus{stroke:var(--axis);stroke-width:1}
.tip{position:absolute;z-index:2;pointer-events:none;background:var(--surface);border:1px solid var(--border);border-radius:8px;
padding:8px 10px;box-shadow:0 4px 14px rgba(0,0,0,.12);font-size:13px;min-width:150px}
.tip-row{display:flex;gap:8px;align-items:baseline}.tip-row strong{font-variant-numeric:tabular-nums}.tip-row span{color:var(--ink-2)}
.tip-date{color:var(--ink-2);margin-bottom:2px}
footer{color:var(--ink-2);font-size:13px;margin-top:22px}footer p{margin:0 0 8px}
@media print{body{background:#fff}.tip{display:none}section.card,.tile{break-inside:avoid}}
@media (max-width:560px){h1{font-size:23px}.tile-value{font-size:22px}th,td{padding:6px 7px}}
"""

JS = """
(function(){
  document.querySelectorAll('.chart[data-interactive]').forEach(function(chart){
    var data = JSON.parse(chart.querySelector('.chart-data').textContent);
    var svg = chart.querySelector('svg'), overlay = chart.querySelector('.overlay'), xhair = chart.querySelector('.xhair');
    var tip = chart.querySelector('.tip'), n = data.dates.length, current = n - 1;
    function hide(){ xhair.setAttribute('visibility', 'hidden'); tip.hidden = true; }
    function place(i){
      current = Math.max(0, Math.min(n - 1, i));
      var x = data.kind === 'bars' ? data.left + (current + 0.5) * data.step : data.left + current * data.step;
      xhair.setAttribute('x1', x); xhair.setAttribute('x2', x); xhair.setAttribute('visibility', 'visible');
      tip.replaceChildren();
      var head = document.createElement('div'); head.className = 'tip-date'; head.textContent = data.dates[current]; tip.append(head);
      data.series.forEach(function(s){
        var row = document.createElement('div'); row.className = 'tip-row';
        var v = document.createElement('strong'); v.textContent = String(s.values[current]);
        var l = document.createElement('span'); l.textContent = s.label;
        row.append(v, l); tip.append(row);
      });
      tip.hidden = false;
      var pt = svg.createSVGPoint(); pt.x = x; pt.y = 0;
      var s = pt.matrixTransform(svg.getScreenCTM()), b = chart.getBoundingClientRect();
      var left = s.x - b.left + 14;
      if (left + tip.offsetWidth > b.width) left = s.x - b.left - tip.offsetWidth - 14;
      tip.style.left = Math.max(left, 0) + 'px'; tip.style.top = '28px';
    }
    overlay.addEventListener('pointermove', function(e){
      var pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
      var p = pt.matrixTransform(svg.getScreenCTM().inverse());
      var i = data.kind === 'bars' ? Math.floor((p.x - data.left) / data.step) : Math.round((p.x - data.left) / data.step);
      place(i);
    });
    overlay.addEventListener('pointerleave', hide);
    overlay.addEventListener('focus', function(){ place(current); });
    overlay.addEventListener('blur', hide);
    overlay.addEventListener('keydown', function(e){
      if (e.key === 'ArrowLeft') { place(current - 1); e.preventDefault(); }
      if (e.key === 'ArrowRight') { place(current + 1); e.preventDefault(); }
    });
  });
})();
"""


def render_html(run: RunResult, *, sample: bool = False, run_at: dt.datetime | None = None) -> str:
    config = run.data.config
    last = run.last
    run_at = run_at or dt.datetime.now()
    start = run.days[0].date
    proof_days = sum(1 for d in run.days if abs(d.proof) >= 0.005)
    register = last.register
    open_rows = register[register["status"] == "open"] if not register.empty else register
    oldest = int(open_rows["age"].max()) if not open_rows.empty else 0
    checks = run.checks()
    opening_total = run.opening_balance_sheet["Net assets"]

    tiles = [
        '<div class="tile"><p class="tile-label">Net assets</p>'
        f'<p class="tile-value">{config.base_currency} {millions(last.net_assets)}</p>'
        f'<p class="tile-sub">{pct(last.net_assets / opening_total - 1, 1, sign=True)} since {fmt_date(run.data.opening.date)}, flows included</p></div>',
        '<div class="tile"><p class="tile-label">NAV proof</p>'
        f'<p class="tile-value">{chip("ok" if proof_days == 0 else "breach", "Ties" if proof_days == 0 else "Out")}</p>'
        f'<p class="tile-sub">Balance sheet against class NAVs, {plural(len(run.days), "day", "days")} checked'
        + ("" if proof_days == 0 else f", {proof_days} out") + "</p></div>",
        '<div class="tile"><p class="tile-label">Open breaks</p>'
        f'<p class="tile-value">{len(open_rows)}</p>'
        f'<p class="tile-sub">{chip("warning" if oldest > 5 else "ok", f"Oldest {oldest} business days")}</p></div>',
        '<div class="tile"><p class="tile-label">Price and NAV checks</p>'
        f'<p class="tile-value">{len(checks)}</p>'
        f'<p class="tile-sub">{plural(len(checks), "finding", "findings")} to review in the period</p></div>',
    ]
    banner = (
        '<p class="banner"><strong>Synthetic sample data.</strong> The fund, its securities, prices, investors and '
        "counterparties are made up for testing.</p>"
        if sample
        else ""
    )
    meta = " · ".join(
        [
            f"Valuation date {fmt_date(last.date)}",
            f"Base currency {config.base_currency}",
            f"Period {fmt_date(start)} to {fmt_date(last.date)}",
            f"Run on {fmt_date(run_at.date())} at {run_at:%H:%M}",
        ]
    )
    body = (
        f'<main><header><p class="kicker">NAV pack</p><h1>{_esc(config.name)}</h1><p class="meta">{_esc(meta)}</p></header>{banner}'
        f'<div class="tiles">{"".join(tiles)}</div>'
        '<section class="card"><h2>Share classes</h2>'
        f'<p class="section-intro">NAV per share to {config.nav_decimals} decimals, in each class\'s own currency. '
        f"Day and period changes are after fees.</p>{_class_table(run)}{nav_chart(run)}</section>"
        '<section class="card"><h2>From opening to closing NAV</h2>'
        f"{_bridge(run)}</section>"
        '<section class="card"><h2>Balance sheet</h2>'
        f'<p class="section-intro">At {fmt_date(last.date)}. The NAV proof compares net assets from the balance sheet '
        f"with the sum of the class NAVs carried forward day by day.</p>{_balance_sheet(run)}</section>"
        '<section class="card"><h2>Reconciliation</h2>'
        '<p class="section-intro">Positions and cash against the custodian on a settled basis, trades against '
        f"broker confirmations. Cash differences of {config.tolerances.cash:,.2f} or less in a currency are within tolerance. "
        f"Ages are in business days.</p>{_breaks(run)}</section>"
        '<section class="card"><h2>Holdings</h2>'
        f"{_holdings(run)}</section>"
        '<section class="card"><h2>Dealing</h2>'
        f'<p class="section-intro">Forward priced at the day\'s NAV per share. Subscriptions and redemptions settle '
        f"T+{config.capital_settlement_days}.</p>{_deals(run)}</section>"
        '<section class="card"><h2>Checks</h2>'
        '<p class="section-intro">Prices unchanged for three days or more, one-day moves over 10%, FX moves over 2% '
        f"and NAV per share moves over 3%.</p>{_checks(run)}</section>"
        "<footer><p>Fees accrue daily on an actual/365 basis. Performance fees are charged on gains above the "
        "high-water mark and crystallize at year end and on redemption. "
        f"Units are issued to {config.unit_decimals} decimals, rounded down. Holdings and cash in other currencies "
        f"are converted at the day's rates, quoted in units of currency per {config.base_currency}.</p>"
        "<p>A portfolio project, not a production fund accounting system.</p></footer></main>"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(config.name)}: NAV pack, {fmt_date(last.date)}</title><style>{CSS}</style></head>"
        f"<body>{body}<script>{JS}</script></body></html>"
    )


def write_outputs(run: RunResult, out_dir: pathlib.Path | str, *, sample: bool = False) -> dict[str, pathlib.Path]:
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = run.last.date.isoformat()
    paths = {
        "report": out / f"nav_pack_{stamp}.html",
        "nav_history": out / "nav_history.csv",
        "balance_sheets": out / "balance_sheets.csv",
        "deals": out / "deals.csv",
        "break_register": out / "break_register.csv",
        "breaks_by_day": out / "breaks_by_day.csv",
        "checks": out / "checks.csv",
        "events": out / "ledger_events.csv",
    }
    paths["report"].write_text(render_html(run, sample=sample), encoding="utf-8")
    run.nav_history().to_csv(paths["nav_history"], index=False)
    run.balance_sheets().to_csv(paths["balance_sheets"], index=False)
    run.deals().to_csv(paths["deals"], index=False)
    run.last.register.to_csv(paths["break_register"], index=False)
    run.breaks_by_day().to_csv(paths["breaks_by_day"], index=False)
    run.checks().to_csv(paths["checks"], index=False)
    run.events.to_csv(paths["events"], index=False)
    return paths
