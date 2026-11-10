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

PALETTE = {  # categorical slots 1-3, validated in each mode (light surface #fcfcfb, dark #1a1a19)
    "light": ["#2a78d6", "#eb6834", "#1baf7a"],
    "dark": ["#3987e5", "#d95926", "#199e70"],
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
) -> alt.TopLevelMixin:
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
    return (
        body.properties(
            title=alt.TitleParams(
                text=title,
                subtitle=[subtitle],
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
