"""Interactive charts (Altair) of the metrics figures, readable in the light and the dark theme.

Design (the dataviz method of the project's tooling): a validated categorical palette, one set of
steps per theme (the first three slots of the reference palette, which pass the colour-blindness
and contrast checks in both modes); colour follows the series, never its position (the AI's
answer key is always slot 1, the AC's always slot 2); text uses ink tokens, never the series
colour, so labels stay legible on a dark surface; thin bars with a rounded end; hairline grid;
one panel per scenario when a figure has many bars, so every panel is full width and its values
fit horizontally. The values come from ``metrics.figures.figure_data``; the subtitle carries the
filters and the source, so a picture saved from the chart's ⋯ menu says where it came from.
"""

import altair as alt
import pandas as pd

PALETTE = {  # categorical slots in their fixed, validated order (light surface #fcfcfb, dark #1a1a19)
    # Slots 1-3 pass every pair (pies, scatter); all 8 pass the adjacent pairs (stacks, bars).
    "light": [
        "#2a78d6",
        "#eb6834",
        "#1baf7a",
        "#eda100",
        "#e87ba4",
        "#008300",
        "#6250d6",
        "#e34948",
    ],
    "dark": [
        "#3987e5",
        "#d95926",
        "#199e70",
        "#c98500",
        "#d55181",
        "#008300",
        "#9085e9",
        "#e66767",
    ],
}
INK = {
    "light": {
        "surface": "#fcfcfb",
        "primary": "#0b0b0b",
        "secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
    },
    "dark": {
        "surface": "#1a1a19",
        "primary": "#f0efec",
        "secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
    },
}
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
WIDTH = 960
PANEL_HEIGHT = 260
SINGLE_HEIGHT = 420
BAR = 22  # px: thin bars, never filling the slot
LABEL_GAP = 14  # px between grouped bars, so the value labels above neighbouring bars never touch


def _tight_x(x_order: list[str], n_series: int, gap: int = 2) -> alt.X:
    """An x band just wide enough for ``n_series`` thin bars side by side, centred in each step."""
    step = WIDTH / max(1, len(x_order))
    inner = max(0.1, min(0.9, 1 - n_series * (BAR + gap) / step))
    return alt.X(
        "x:N",
        sort=x_order,
        title=None,
        axis=alt.Axis(labelAngle=0, labelLimit=200),
        scale=alt.Scale(paddingInner=inner, paddingOuter=inner / 2),
    )


def _panel(
    data: pd.DataFrame, kind: str, fmt: str, y_title: str, colors: list[str], ink: dict, height: int
) -> alt.LayerChart:
    x_order = list(dict.fromkeys(data["x"]))
    series_order = list(dict.fromkeys(data["series"]))
    base = alt.Chart(data)
    x = alt.X("x:N", sort=x_order, title=None, axis=alt.Axis(labelAngle=0, labelLimit=200))
    color = alt.Color(
        "series:N",
        sort=series_order,
        scale=alt.Scale(domain=series_order, range=colors[: len(series_order)]),
        legend=alt.Legend(orient="top", title=None, labelLimit=400),
    )
    tooltip = [
        alt.Tooltip("x:N", title="conjunto"),
        alt.Tooltip("series:N", title="série"),
        alt.Tooltip("value:Q", title=y_title, format=fmt),
    ]
    label_style = {"fontSize": 11, "color": ink["primary"], "font": FONT}
    if kind == "box":
        gap = LABEL_GAP if len(series_order) > 1 else 2
        offset = alt.XOffset(
            "series:N", sort=series_order, scale=alt.Scale(paddingInner=gap / (BAR + gap))
        )
        x = _tight_x(x_order, len(series_order), gap)
        boxes = base.mark_boxplot(
            extent=1.5,
            outliers=False,  # the extreme problems stay in the table; they would flatten the boxes
            size=BAR,
            median={"color": ink["primary"]},
            rule={"color": ink["secondary"]},
            ticks={"color": ink["secondary"]},
        ).encode(x=x, xOffset=offset, y=alt.Y("value:Q", title=y_title), color=color)
        medians = (
            base.transform_aggregate(
                median="median(value)", top="q3(value)", groupby=["x", "series"]
            )
            .mark_text(baseline="bottom", dy=-4, fontWeight="bold", **label_style)
            .encode(x=x, xOffset=offset, y="top:Q", text=alt.Text("median:Q", format=fmt))
        )
        layers = [boxes, medians]
    elif kind == "stacked":
        y = alt.Y("value:Q", title=y_title, stack="zero")
        bars = base.mark_bar(size=BAR * 2, cornerRadiusEnd=4).encode(
            x=x, y=y, color=color, order=alt.Order("series:N"), tooltip=tooltip
        )
        totals = (
            base.transform_aggregate(total="sum(value)", groupby=["x"])
            .mark_text(baseline="bottom", dy=-4, fontWeight="bold", **label_style)
            .encode(x=x, y="total:Q", text=alt.Text("total:Q", format=fmt))
        )
        layers = [bars, totals]  # the split is in the tooltip and the legend
    else:
        gap = LABEL_GAP if len(series_order) > 1 else 2
        offset = alt.XOffset(
            "series:N", sort=series_order, scale=alt.Scale(paddingInner=gap / (BAR + gap))
        )
        y = alt.Y("value:Q", title=y_title)
        x = _tight_x(x_order, len(series_order), gap)
        bars = base.mark_bar(cornerRadiusEnd=4).encode(
            x=x, xOffset=offset, y=y, color=color, tooltip=tooltip
        )
        labels = base.mark_text(baseline="bottom", dy=-4, **label_style).encode(
            x=x, xOffset=offset, y=y, text=alt.Text("value:Q", format=fmt)
        )
        layers = [bars, labels]
    return alt.layer(*layers).properties(width=WIDTH, height=height)


def chart(
    data: pd.DataFrame,
    title: str,
    y_title: str,
    subtitle: str,
    kind: str,
    fmt: str = ".1f",
    mode: str = "light",
    in_card: bool = False,
) -> alt.TopLevelMixin:
    """The figures of feature 010 (grouped, stacked, box). ``in_card``: no title, transparent, at
    its fixed width (the dashboard writes the title as page text)."""
    mode = mode if mode in INK else "light"
    ink, colors = INK[mode], PALETTE[mode]
    panels = [p for p in dict.fromkeys(data["panel"])] if "panel" in data else [""]
    if panels == [""]:
        body = _panel(data, kind, fmt, y_title, colors, ink, SINGLE_HEIGHT)
    else:
        body = alt.vconcat(
            *[
                _panel(
                    data[data["panel"] == p], kind, fmt, y_title, colors, ink, PANEL_HEIGHT
                ).properties(
                    title=alt.TitleParams(p, anchor="start", fontSize=13, color=ink["secondary"])
                )
                for p in panels
            ],
            spacing=28,
        ).resolve_scale(y="shared")
    if in_card:
        return _card(body, ink, stretch=False)
    return _finish(body, title, subtitle, ink)


def _finish(body, title: str, subtitle: str | list[str], ink: dict) -> alt.TopLevelMixin:
    """Title, subtitle, surface, fonts, axes and legend of every chart, in the ink of the theme."""
    return (
        body.properties(
            title=alt.TitleParams(
                text=title,
                subtitle=[subtitle] if isinstance(subtitle, str) else list(subtitle),
                anchor="start",
                fontSize=16,
                subtitleFontSize=11,
                color=ink["primary"],
                subtitleColor=ink["secondary"],
                font=FONT,
                subtitleFont=FONT,
                offset=12,
            )
        )
        .configure(background=ink["surface"], font=FONT, padding=16)
        .configure_view(stroke=None)
        .configure_axis(
            labelColor=ink["secondary"],
            titleColor=ink["secondary"],
            labelFontSize=12,
            titleFontSize=12,
            gridColor=ink["grid"],
            gridWidth=1,
            domainColor=ink["axis"],
            tickColor=ink["axis"],
        )
        .configure_axisX(grid=False)
        .configure_legend(labelColor=ink["primary"], labelFontSize=12, symbolType="square")
    )


# ------------------------------------------------------------- page 1 of the dashboard (012, US1)
# Card charts: the conclusion title and the subtitle are page text (same font as the page), so the
# chart has no title of its own, a transparent background and the width of its card. One chart per
# job (dataviz skill): parts of a whole with at most 4 parts → donut with direct labels; magnitudes
# of one series → bars without a legend; a split per set → 100% stacked bars with a 2px gap in the
# page colour; a mean per set and scenario → a dot plot on a zoomed axis. Text always in ink.

PAGE_BG = {"light": "#ffffff", "dark": "#0e1117"}  # Streamlit's own page background, for the gaps
CARD_HEIGHT = 240


def _theme(mode: str) -> tuple[str, dict, list[str]]:
    mode = mode if mode in INK else "light"
    return mode, INK[mode], PALETTE[mode]


def _card(body, ink: dict, stretch: bool = True) -> alt.TopLevelMixin:
    """No title, transparent, the width of the card; axes and legend in the ink of the theme."""
    return (
        (body.properties(width="container") if stretch else body)
        .configure(
            background="transparent",
            font=FONT,
            padding={"left": 4, "right": 12, "top": 8, "bottom": 4},
        )
        .configure_view(stroke=None)
        .configure_axis(
            labelColor=ink["secondary"],
            titleColor=ink["secondary"],
            labelFontSize=12,
            titleFontSize=12,
            titleFontWeight="normal",
            gridColor=ink["grid"],
            gridWidth=1,
            domainColor=ink["axis"],
            tickColor=ink["axis"],
        )
        .configure_axisX(grid=False)
        .configure_legend(
            labelColor=ink["secondary"], labelFontSize=12, symbolType="square", symbolSize=90
        )
    )


def donut(data: pd.DataFrame, mode: str = "light", fmt: str = ",") -> alt.TopLevelMixin:
    """``data``: ``label``, ``value`` (at most 4 rows); the legend beside it reads "name · share"."""
    if len(data) > 4:
        raise ValueError("a donut takes at most 4 parts; use bars")
    mode, ink, colors = _theme(mode)
    frame = data.assign(share=data["value"] / data["value"].sum(), order=range(len(data)))
    frame["text"] = [
        f"{label} · {round(100 * share)}%"
        for label, share in zip(frame["label"], frame["share"], strict=True)
    ]
    texts = list(frame["text"])
    base = alt.Chart(frame).encode(
        theta=alt.Theta("value:Q", stack=True), order=alt.Order("order:Q")
    )
    arcs = base.mark_arc(
        innerRadius=62, outerRadius=100, stroke=PAGE_BG[mode], strokeWidth=2
    ).encode(
        color=alt.Color(
            "text:N",
            sort=texts,
            scale=alt.Scale(domain=texts, range=colors[: len(texts)]),
            legend=alt.Legend(
                orient="right",
                title=None,
                labelFontSize=13,
                labelColor=ink["primary"],
                symbolSize=140,
                rowPadding=8,
                labelLimit=260,
            ),
        ),
        tooltip=[
            alt.Tooltip("label:N", title="parte"),
            alt.Tooltip("value:Q", title="valor", format=fmt),
            alt.Tooltip("share:Q", title="participação", format=".0%"),
        ],
    )
    return _card(arcs.properties(height=CARD_HEIGHT), ink)


def bars(
    data: pd.DataFrame, y_title: str, mode: str = "light", fmt: str = ","
) -> alt.TopLevelMixin:
    """``data``: ``x`` (in order), ``value``; one series, so no legend: the card title names it."""
    mode, ink, colors = _theme(mode)
    order = list(dict.fromkeys(data["x"]))
    base = alt.Chart(data).encode(
        x=alt.X(
            "x:N",
            sort=order,
            title=None,
            axis=alt.Axis(labelAngle=0, ticks=False, domain=False),
            scale=alt.Scale(paddingInner=0.35),
        ),
        y=alt.Y("value:Q", title=None, axis=alt.Axis(tickCount=4, domain=False, ticks=False)),
    )
    marks = base.mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color=colors[0]).encode(
        tooltip=[alt.Tooltip("x:N", title=""), alt.Tooltip("value:Q", title=y_title, format=fmt)]
    )
    labels = base.mark_text(
        baseline="bottom", dy=-4, fontSize=12, color=ink["primary"], font=FONT
    ).encode(text=alt.Text("value:Q", format=fmt))
    return _card(alt.layer(marks, labels).properties(height=CARD_HEIGHT), ink)


def stacked100(
    data: pd.DataFrame, parts: list[str], mode: str = "light", neutral: str | None = None
) -> alt.TopLevelMixin:
    """``data``: ``y`` (one bar each, in order), ``part``, ``count``, ``share`` (0–100).

    ``neutral`` is a part that means absence (e.g. "sem suíte"): it is drawn in the muted ink, not
    in a categorical hue, so it never reads as one more category.
    """
    if len(parts) > 8:
        raise ValueError("more than 8 parts: fold the smallest into 'outros'")
    mode, ink, palette = _theme(mode)
    hues = iter(palette)
    colors = [ink["muted"] if p == neutral else next(hues) for p in parts]
    order = list(dict.fromkeys(data["y"]))
    rank = {p: i for i, p in enumerate(parts)}
    frame = data.assign(part_order=data["part"].map(rank))
    body = (
        alt.Chart(frame)
        .mark_bar(stroke=PAGE_BG[mode], strokeWidth=2)
        .encode(
            y=alt.Y(
                "y:N",
                sort=order,
                title=None,
                axis=alt.Axis(ticks=False, domain=False, labelPadding=8),
                scale=alt.Scale(paddingInner=0.25),
            ),
            x=alt.X(
                "share:Q",
                stack="zero",
                title=None,
                scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(values=[0, 25, 50, 75, 100], labelExpr="datum.label + '%'"),
            ),
            color=alt.Color(
                "part:N",
                sort=parts,
                scale=alt.Scale(domain=parts, range=colors),
                legend=alt.Legend(
                    orient="bottom", title=None, labelLimit=260, columns=3, direction="horizontal"
                ),
            ),
            order=alt.Order("part_order:Q"),
            tooltip=[
                alt.Tooltip("y:N", title="IA"),
                alt.Tooltip("part:N", title="status"),
                alt.Tooltip("count:Q", title="combinações"),
                alt.Tooltip("share:Q", title="%", format=".1f"),
            ],
        )
        .properties(height=48 * max(1, len(order)))
    )
    return _card(body, ink)


def dots(
    data: pd.DataFrame, x_title: str, mode: str = "light", fmt: str = ".1f"
) -> alt.TopLevelMixin:
    """Dot plot: ``y`` (set, one row each), ``series`` (scenario), ``value``; a grey rule joins the
    lowest and highest value of each row, and the axis is zoomed to the data."""
    mode, ink, colors = _theme(mode)
    y_order = list(dict.fromkeys(data["y"]))
    series = list(dict.fromkeys(data["series"]))
    low, high = float(data["value"].min()), float(data["value"].max())
    pad = max(0.5, (high - low) * 0.15)
    scale = alt.Scale(domain=[low - pad, high + pad], zero=False, nice=False)
    y = alt.Y(
        "y:N", sort=y_order, title=None, axis=alt.Axis(ticks=False, domain=False, labelPadding=8)
    )
    span = (
        alt.Chart(data)
        .mark_rule(color=ink["axis"], strokeWidth=2)
        .encode(y=y, x=alt.X("min(value):Q", scale=scale, title=x_title), x2="max(value):Q")
    )
    points = (
        alt.Chart(data)
        .mark_point(filled=True, size=130, opacity=1, stroke=PAGE_BG[mode], strokeWidth=2)
        .encode(
            y=y,
            x=alt.X("value:Q", scale=scale, title=x_title, axis=alt.Axis(tickCount=6, grid=True)),
            color=alt.Color(
                "series:N",
                sort=series,
                scale=alt.Scale(domain=series, range=colors[: len(series)]),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=[
                alt.Tooltip("y:N", title="IA"),
                alt.Tooltip("series:N", title="cenário"),
                alt.Tooltip("value:Q", title=x_title, format=fmt),
            ],
        )
    )
    return _card(alt.layer(span, points).properties(height=44 * max(1, len(y_order))), ink)


# ------------------------------------------------------------- page 3 of the dashboard (012, US2)
# One highlight colour (slot 1) for the leader, the others in the muted ink (contracts/narrative.md:
# "o líder numa cor de destaque única; os demais em cinza"); a second accent (slot 2) only where a
# chart contrasts two things (the biggest and the smallest change of scenario). The IIC uses the
# diverging pair blue (slot 1, above zero) and red (slot 8, below), never green × red. Every chart
# is a body without title: the dashboard puts it in a card (``card``) and the figure command adds
# the title and the subtitle (``framed``).

FILE_WIDTH = 760
POSITIVE, NEGATIVE = 0, 7  # palette slots of the diverging pair


def card(body, mode: str = "light", stretch: bool = True) -> alt.TopLevelMixin:
    """A page-3 chart as the dashboard shows it: transparent, the width of its card (or its own
    fixed width, for side-by-side panels)."""
    _, ink, _ = _theme(mode)
    return _card(body, ink, stretch)


def framed(body, title: str, subtitle: list[str], mode: str = "light") -> alt.TopLevelMixin:
    """A page-3 chart as a figure file: fixed width, title, subtitle and the surface."""
    _, ink, _ = _theme(mode)
    if not isinstance(body, (alt.HConcatChart, alt.VConcatChart)):
        body = body.properties(width=FILE_WIDTH)
    return _finish(body, title, subtitle, ink)


def _grid_axes(ink: dict, rows: list[str], columns: list[str]) -> tuple[alt.X, alt.Y]:
    x = alt.X(
        "col:N",
        sort=columns,
        title=None,
        axis=alt.Axis(
            orient="top", labelAngle=0, ticks=False, domain=False, labelLimit=180, labelPadding=8
        ),
        scale=alt.Scale(paddingInner=0.06),
    )
    y = alt.Y(
        "row:N",
        sort=rows,
        title=None,
        axis=alt.Axis(ticks=False, domain=False, labelLimit=260, labelPadding=10),
        scale=alt.Scale(paddingInner=0.08),
    )
    return x, y


def _cell_text(base: alt.Chart, flag: str, ink: dict) -> list[alt.Chart]:
    """The text of the grid cells: bold where the boolean column ``flag`` is true."""
    style = {"lineBreak": "\n", "fontSize": 12, "color": ink["primary"], "font": FONT}
    return [
        base.transform_filter(f"{'' if bold else '!'}datum.{flag}")
        .mark_text(fontWeight="bold" if bold else "normal", **style)
        .encode(text="text:N")
        for bold in (True, False)
    ]


def scoreboard_grid(data: pd.DataFrame, mode: str = "light") -> alt.LayerChart:
    """``data``: ``row`` (set), ``col`` (criterion), ``text`` ("1º\\n90,1%"), ``first`` (bool).

    One cell per set × criterion; the 1st place of each criterion in the highlight colour."""
    mode, ink, colors = _theme(mode)
    rows = list(dict.fromkeys(data["row"]))
    columns = list(dict.fromkeys(data["col"]))
    x, y = _grid_axes(ink, rows, columns)
    base = alt.Chart(data).encode(x=x, y=y)
    cells = base.mark_rect(cornerRadius=4).encode(
        color=alt.condition(
            "datum.first", alt.value(colors[0]), alt.value(ink["grid"]), legend=None
        ),
        opacity=alt.condition("datum.first", alt.value(0.28), alt.value(0.45)),
        tooltip=[
            alt.Tooltip("row:N", title="IA"),
            alt.Tooltip("col:N", title="critério"),
            alt.Tooltip("tip:N", title="posição e valor"),
        ],
    )
    return alt.layer(cells, *_cell_text(base, "first", ink)).properties(
        height=50 * max(1, len(rows))
    )


def ranked_bars(
    data: pd.DataFrame, x_title: str, mode: str = "light", percent: bool = True
) -> alt.LayerChart:
    """Horizontal bars sorted best first: ``y`` (set), ``value``, ``label`` (text at the end),
    ``first`` (bool); optional ``before`` draws a tick at the value of the AI's answer key (the
    before/after of the oracle on the same scale)."""
    mode, ink, colors = _theme(mode)
    order = list(data["y"])
    has_before = "before" in data and data["before"].notna().any()
    top = float(max(data["value"].max(), data["before"].max() if has_before else 0))
    frame = data.assign(end=data[["value", "before"]].max(axis=1) if has_before else data["value"])
    scale = alt.Scale(domain=[0, top * 1.3], nice=False)
    if percent:
        axis = alt.Axis(
            values=[v for v in (0, 25, 50, 75, 100) if v <= top],
            labelExpr="datum.label + '%'",
            grid=True,
        )
    else:
        axis = alt.Axis(grid=True, tickCount=4, labelExpr="replace(datum.label, '.', ',')")
    y = alt.Y(
        "y:N",
        sort=order,
        title=None,
        axis=alt.Axis(ticks=False, domain=False, labelPadding=8, labelLimit=200),
        scale=alt.Scale(paddingInner=0.3),
    )
    base = alt.Chart(frame).encode(y=y)
    tooltip = [alt.Tooltip("y:N", title="IA"), alt.Tooltip("label:N", title=x_title)]
    layers = [
        base.mark_bar(cornerRadiusEnd=4, height=BAR).encode(
            x=alt.X("value:Q", scale=scale, title=x_title, axis=axis),
            color=alt.condition(
                "datum.first", alt.value(colors[0]), alt.value(ink["muted"]), legend=None
            ),
            tooltip=tooltip,
        )
    ]
    if has_before:
        layers.append(
            base.mark_tick(thickness=3, size=BAR + 10, color=ink["primary"]).encode(
                x=alt.X("before:Q", scale=scale), tooltip=tooltip
            )
        )
    layers.append(
        base.mark_text(align="left", dx=8, fontSize=12, color=ink["primary"], font=FONT).encode(
            x=alt.X("end:Q", scale=scale), text="label:N"
        )
    )
    return alt.layer(*layers).properties(height=44 * max(1, len(order)))


def tradeoff_scatter(
    data: pd.DataFrame, x_cut: float, y_cut: float, mode: str = "light"
) -> alt.LayerChart:
    """TFP (x, lower is better) × TDF* (y): ``label``, ``x``, ``y``, ``accent`` (-1 grey, 0 or 1
    for the two highlighted sets); the ideal region (low x, high y) shaded at 12%."""
    mode, ink, colors = _theme(mode)
    x_max = float(data["x"].max()) * 1.15 + 1
    y_low = float(data["y"].min()) - 4
    y_high = min(100.0, float(data["y"].max()) + 3)
    x_scale = alt.Scale(domain=[0, x_max], nice=False)
    y_scale = alt.Scale(domain=[y_low, y_high], nice=False, zero=False)
    region = pd.DataFrame(
        {"x0": [0.0], "x1": [x_cut], "y0": [y_cut], "y1": [y_high], "text": ["região ideal"]}
    )
    shade = (
        alt.Chart(region)
        .mark_rect(color=colors[0], opacity=0.12)
        .encode(
            x=alt.X("x0:Q", scale=x_scale), x2="x1:Q", y=alt.Y("y0:Q", scale=y_scale), y2="y1:Q"
        )
    )
    shade_label = (
        alt.Chart(region)
        .mark_text(align="left", baseline="top", dx=6, dy=6, fontSize=11, color=ink["secondary"])
        .encode(x=alt.X("x0:Q", scale=x_scale), y=alt.Y("y1:Q", scale=y_scale), text="text:N")
    )
    accent = alt.Color(
        "accent:N",
        scale=alt.Scale(domain=["-1", "0", "1"], range=[ink["muted"], colors[0], colors[1]]),
        legend=None,
    )
    frame = data.assign(accent=data["accent"].astype(str))
    base = alt.Chart(frame).encode(
        x=alt.X(
            "x:Q",
            scale=x_scale,
            title="TFP: % dos problemas em que reprova o código correto (menor é melhor)",
            axis=alt.Axis(labelExpr="datum.label + '%'", tickCount=6),
        ),
        y=alt.Y(
            "y:Q",
            scale=y_scale,
            title="TDF* (%)",
            axis=alt.Axis(labelExpr="datum.label + '%'", tickCount=5),
        ),
    )
    points = base.mark_point(
        filled=True, size=170, opacity=1, stroke=PAGE_BG[mode], strokeWidth=2
    ).encode(
        color=accent,
        tooltip=[
            alt.Tooltip("label:N", title="IA"),
            alt.Tooltip("x:Q", title="TFP (%)", format=".1f"),
            alt.Tooltip("y:Q", title="TDF* (%)", format=".1f"),
        ],
    )
    labels = base.mark_text(
        align="left", dx=11, fontSize=12, color=ink["primary"], font=FONT
    ).encode(text="label:N")
    return alt.layer(shade, shade_label, points, labels).properties(height=320)


def scenario_lines(data: pd.DataFrame, scenarios: list[str], mode: str = "light") -> alt.LayerChart:
    """TDF* across the scenarios: ``set``, ``scenario``, ``value``, ``accent`` (-1 grey, 0, 1); the
    name of each set written at its last point."""
    mode, ink, colors = _theme(mode)
    frame = data.assign(accent=data["accent"].astype(str))
    low, high = float(frame["value"].min()), float(frame["value"].max())
    pad = max(1.0, (high - low) * 0.08)
    x = alt.X(
        "scenario:N",
        sort=scenarios,
        title=None,
        axis=alt.Axis(labelAngle=0, ticks=False, domain=False, labelPadding=8),
        scale=alt.Scale(padding=0.35),
    )
    y = alt.Y(
        "value:Q",
        title="TDF* (%)",
        scale=alt.Scale(domain=[low - pad, high + pad], zero=False, nice=False),
        axis=alt.Axis(labelExpr="datum.label + '%'", tickCount=5),
    )
    accent = alt.Color(
        "accent:N",
        scale=alt.Scale(domain=["-1", "0", "1"], range=[ink["muted"], colors[0], colors[1]]),
        legend=None,
    )
    base = alt.Chart(frame).encode(x=x, y=y, color=accent, detail="set:N")
    lines = base.mark_line(strokeWidth=2.5)
    points = base.mark_point(filled=True, size=70, opacity=1).encode(
        tooltip=[
            alt.Tooltip("set:N", title="IA"),
            alt.Tooltip("scenario:N", title="cenário"),
            alt.Tooltip("value:Q", title="TDF* (%)", format=".2f"),
        ]
    )
    last = frame[frame["scenario"] == scenarios[-1]]
    labels = (
        alt.Chart(last)
        .mark_text(align="left", dx=10, fontSize=12, color=ink["primary"], font=FONT)
        .encode(x=x, y=y, text="set:N")
    )
    return alt.layer(lines, points, labels).properties(height=300)


def diverging_bars(data: pd.DataFrame, limit: float, mode: str = "light") -> alt.LayerChart:
    """IIC from zero: ``y`` (set), ``value``, ``label``; blue above zero, red below, a grey zero
    rule; ``limit`` is the half width of the shared x scale."""
    mode, ink, colors = _theme(mode)
    order = list(dict.fromkeys(data["y"]))
    scale = alt.Scale(domain=[-limit, limit], nice=False)
    y = alt.Y(
        "y:N",
        sort=order,
        title=None,
        axis=alt.Axis(ticks=False, domain=False, labelPadding=8, labelLimit=200),
        scale=alt.Scale(paddingInner=0.3),
    )
    frame = data.assign(positive=data["value"] >= 0)
    base = alt.Chart(frame).encode(y=y)
    bars = base.mark_bar(cornerRadiusEnd=3, height=BAR).encode(
        x=alt.X(
            "value:Q",
            scale=scale,
            title="IIC (%)",
            axis=alt.Axis(labelExpr="datum.label + '%'", tickCount=5),
        ),
        color=alt.condition(
            "datum.value >= 0",
            alt.value(colors[POSITIVE]),
            alt.value(colors[NEGATIVE]),
            legend=None,
        ),
        tooltip=[alt.Tooltip("y:N", title="IA"), alt.Tooltip("label:N", title="IIC")],
    )
    zero = (
        alt.Chart(pd.DataFrame({"x": [0.0]}))
        .mark_rule(color=ink["muted"], strokeWidth=1.5)
        .encode(x=alt.X("x:Q", scale=scale))
    )
    text = {"fontSize": 12, "color": ink["primary"], "font": FONT}
    right = base.transform_filter("datum.value >= 0").mark_text(align="left", dx=6, **text)
    left = base.transform_filter("datum.value < 0").mark_text(align="right", dx=-6, **text)
    labels = [m.encode(x=alt.X("value:Q", scale=scale), text="label:N") for m in (right, left)]
    return alt.layer(bars, zero, *labels).properties(height=44 * max(1, len(order)))


def guide_grid(
    data: pd.DataFrame, rows: list[str], columns: list[str], highlight: str | None, mode: str
) -> alt.LayerChart:
    """The choice guide: ``row`` (criterion in plain words), ``col`` (scenario), ``text`` (winner and
    value, then the second and the state); the row ``highlight`` in the highlight colour."""
    mode, ink, colors = _theme(mode)
    x, y = _grid_axes(ink, rows, columns)
    frame = data.assign(on=data["row"] == highlight)
    base = alt.Chart(frame).encode(x=x, y=y)
    cells = base.mark_rect(cornerRadius=4).encode(
        color=alt.condition("datum.on", alt.value(colors[0]), alt.value(ink["grid"]), legend=None),
        opacity=alt.condition("datum.on", alt.value(0.28), alt.value(0.45)),
        tooltip=[
            alt.Tooltip("row:N", title="critério"),
            alt.Tooltip("col:N", title="cenário"),
            alt.Tooltip("tip:N", title="resultado"),
        ],
    )
    return alt.layer(cells, *_cell_text(base, "on", ink)).properties(height=60 * max(1, len(rows)))
