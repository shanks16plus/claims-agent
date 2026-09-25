"""Charts for the insurer pages: Altair (Vega-Lite), drawn in the app's style.
Colours were checked with the dataviz palette validator on the card surface (#FBFAF8): mid navy (slot 1) and
green (slot 2) pass the lightness, chroma and colour-blindness checks. Green sits below 3:1 contrast, so every
chart carries visible value labels and a table view underneath."""
import altair as alt

SURFACE, INK, MUTED, GRID = "#FBFAF8", "#0F1D2E", "#545E6B", "#E4DFD6"
SLOT_1, SLOT_2 = "#2F5B9A", "#2FAE6B"
FONT = "IBM Plex Sans"

# Outcome colours follow the outcome, never its rank: a filter that drops one keeps the other's colour.
OUTCOMES = {"Settled automatically": SLOT_2, "Sent to a person": SLOT_1}


def _styled(chart):
    return (chart.configure(background="transparent", font=FONT)
            .configure_view(stroke=None)
            .configure_axis(labelFont=FONT, labelColor=MUTED, labelFontSize=12, titleFont=FONT, titleColor=MUTED,
                            titleFontWeight="normal", titleFontSize=12, gridColor=GRID, gridWidth=1, domain=False,
                            ticks=False, labelPadding=8)
            .configure_legend(labelFont=FONT, labelColor=INK, labelFontSize=12, title=None, orient="top",
                              symbolType="square", symbolSize=120, columnPadding=18, padding=0, offset=14)
            .configure_text(font=FONT))


def bars(df, category, value, value_title, number_format="d"):
    """One series, horizontal, largest first, value at the tip."""
    base = alt.Chart(df).encode(
        y=alt.Y(f"{category}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=280)),
        x=alt.X(f"{value}:Q", title=None, axis=alt.Axis(format=number_format, tickMinStep=1, grid=True),
                scale=alt.Scale(nice=True)))
    marks = base.mark_bar(size=18, cornerRadiusEnd=4, color=SLOT_1).encode(
        tooltip=[alt.Tooltip(f"{value}:Q", title=value_title, format=number_format),
                 alt.Tooltip(f"{category}:N", title=" ")])
    labels = base.mark_text(align="left", dx=8, color=INK, fontSize=12).encode(
        text=alt.Text(f"{value}:Q", format=number_format))
    return _styled((marks + labels).properties(height=max(44 * len(df), 90)))


def stacked_bars(df, category, series, value, value_title):
    """Part-to-whole per category, horizontal. A 2px surface gap separates the segments."""
    domain = [name for name in OUTCOMES if name in set(df[series])]
    chart = alt.Chart(df).mark_bar(size=20, stroke=SURFACE, strokeWidth=2).encode(
        y=alt.Y(f"{category}:N", title=None, sort="-x"),
        x=alt.X(f"sum({value}):Q", title=None, stack=True, axis=alt.Axis(format="d", tickMinStep=1)),
        color=alt.Color(f"{series}:N", scale=alt.Scale(domain=domain, range=[OUTCOMES[d] for d in domain])),
        order=alt.Order(f"{series}:N", sort="descending"),
        tooltip=[alt.Tooltip(f"sum({value}):Q", title=value_title), alt.Tooltip(f"{series}:N", title=" "),
                 alt.Tooltip(f"{category}:N", title=" ")])
    return _styled(chart.properties(height=max(52 * df[category].nunique(), 110)))


def daily_columns(df, start, end, series, value, value_title):
    """Claims per day on a continuous date axis: every day from start to end is a slot, empty days included."""
    days = (end - start).days + 1
    width = 22 if days <= 10 else 12 if days <= 35 else 5
    domain = [name for name in OUTCOMES if name in set(df[series])]
    chart = alt.Chart(df).mark_bar(size=width, stroke=SURFACE, strokeWidth=1).encode(
        x=alt.X("day:T", title=None, scale=alt.Scale(domain=[start.isoformat(), end.isoformat()], padding=18),
                axis=alt.Axis(format="%d %b", labelAngle=0, grid=False, tickCount=min(days, 10))),
        y=alt.Y(f"sum({value}):Q", title=None, stack=True, axis=alt.Axis(format="d", tickMinStep=1)),
        color=alt.Color(f"{series}:N", scale=alt.Scale(domain=domain, range=[OUTCOMES[d] for d in domain])),
        order=alt.Order(f"{series}:N", sort="descending"),
        tooltip=[alt.Tooltip(f"sum({value}):Q", title=value_title), alt.Tooltip(f"{series}:N", title=" "),
                 alt.Tooltip("day:T", title=" ", format="%d %B %Y")])
    return _styled(chart.properties(height=220))
