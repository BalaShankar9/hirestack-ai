"""
ChartRenderer — matplotlib-driven chart galaxy for PPT slides.

Renders a ChartSpec into a PNG byte buffer suitable for python-pptx
add_picture(). Uses the non-interactive 'Agg' backend so it works in
server / async / unit-test environments without a display.

Supported kinds (15+ — the "galaxy"):
    line, area, bar, column, stacked_bar, scatter, bubble, pie, donut,
    histogram, box, heatmap, waterfall, radar, funnel.

Design:
- Pure async wrapper around sync matplotlib calls (matplotlib is sync but
  fast; we offload to a thread to avoid blocking the event loop on big
  charts).
- Style is consistent across kinds: accent color drives primary series,
  secondary series cycle through a palette, axes are clean, grid is
  subtle, fonts match the slide composer's DEFAULT_FONT family.
- Failures return None so the composer's placeholder card kicks in
  instead of raising into the orchestrator.

ChartSelector — heuristic data-shape → optimal chart kind suggester.
Used by upstream callers (e.g. P4 orchestrator) to pick a chart type
when the LLM didn't specify one.
"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Any, Dict, List, Optional, Sequence

import matplotlib
matplotlib.use("Agg")  # non-interactive backend; safe in server contexts.
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

from ai_engine.agents.ppt.schemas import ChartKind, ChartSpec

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
#  Palette helpers
# ────────────────────────────────────────────────────────────────────────

def _hex_to_rgb01(value: str) -> tuple:
    h = value.strip().lstrip("#")
    if len(h) != 6:
        return (0.15, 0.39, 0.92)  # default blue
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


def _palette(accent_hex: str, n: int) -> List[tuple]:
    """Build an n-color palette, accent first then complementary cycle."""
    base = _hex_to_rgb01(accent_hex)
    extras = [
        (0.94, 0.34, 0.36),  # red
        (0.20, 0.71, 0.40),  # green
        (0.96, 0.62, 0.04),  # amber
        (0.55, 0.36, 0.96),  # purple
        (0.16, 0.71, 0.86),  # cyan
        (0.91, 0.45, 0.71),  # pink
        (0.50, 0.50, 0.50),  # gray
    ]
    out = [base]
    for c in extras:
        if len(out) >= n:
            break
        out.append(c)
    while len(out) < n:
        out.append(extras[len(out) % len(extras)])
    return out[:n]


# ────────────────────────────────────────────────────────────────────────
#  Series normalization
# ────────────────────────────────────────────────────────────────────────

def _series_to_y(series: Dict[str, Any]) -> List[float]:
    data = series.get("data") or []
    out: List[float] = []
    for d in data:
        if isinstance(d, (int, float)):
            out.append(float(d))
        elif isinstance(d, (list, tuple)) and len(d) >= 2:
            out.append(float(d[1]))  # treat as (x,y) → y
    return out


def _series_to_xy(series: Dict[str, Any]) -> tuple:
    data = series.get("data") or []
    xs: List[float] = []
    ys: List[float] = []
    for i, d in enumerate(data):
        if isinstance(d, (int, float)):
            xs.append(float(i))
            ys.append(float(d))
        elif isinstance(d, (list, tuple)) and len(d) >= 2:
            xs.append(float(d[0]))
            ys.append(float(d[1]))
    return xs, ys


def _series_to_xyz(series: Dict[str, Any]) -> tuple:
    data = series.get("data") or []
    xs: List[float] = []
    ys: List[float] = []
    zs: List[float] = []
    for i, d in enumerate(data):
        if isinstance(d, (list, tuple)) and len(d) >= 3:
            xs.append(float(d[0])); ys.append(float(d[1])); zs.append(float(d[2]))
        elif isinstance(d, (list, tuple)) and len(d) >= 2:
            xs.append(float(d[0])); ys.append(float(d[1])); zs.append(20.0)
        elif isinstance(d, (int, float)):
            xs.append(float(i)); ys.append(float(d)); zs.append(20.0)
    return xs, ys, zs


# ────────────────────────────────────────────────────────────────────────
#  ChartRenderer
# ────────────────────────────────────────────────────────────────────────

class ChartRenderer:
    """Render a ChartSpec to a PNG byte buffer."""

    def __init__(self, *, dpi: int = 150, figsize: tuple = (11.0, 5.5)) -> None:
        self.dpi = dpi
        self.figsize = figsize

    async def render(self, spec: ChartSpec, *, accent_hex: str = "#2563EB") -> Optional[bytes]:
        """Async entry — runs matplotlib in a thread to keep the loop snappy."""
        try:
            return await asyncio.to_thread(self._render_sync, spec, accent_hex)
        except Exception as exc:  # noqa: BLE001
            logger.warning("chart_render_failed: kind=%s err=%s", spec.kind, str(exc)[:200])
            return None

    # ─── sync core ────────────────────────────────────────────────────
    def _render_sync(self, spec: ChartSpec, accent_hex: str) -> Optional[bytes]:
        kind = (spec.kind or "").lower().strip()
        fig: Figure = plt.figure(figsize=self.figsize, dpi=self.dpi, facecolor="white")
        ax = fig.add_subplot(111)
        try:
            handler = self._dispatch.get(kind)
            if handler is None:
                logger.debug("chart_unknown_kind: %s", kind)
                return None
            handler(self, ax, spec, accent_hex)
            self._style_axes(ax, spec, kind)
            buf = io.BytesIO()
            fig.tight_layout(pad=1.6)
            fig.savefig(buf, format="png", dpi=self.dpi,
                        facecolor=fig.get_facecolor(), bbox_inches="tight")
            return buf.getvalue()
        finally:
            plt.close(fig)

    # ─── shared styling ───────────────────────────────────────────────
    def _style_axes(self, ax, spec: ChartSpec, kind: str) -> None:
        if spec.title and kind not in ("pie", "donut"):
            ax.set_title(spec.title, fontsize=14, fontweight="bold", pad=12, color="#0F172A")
        if spec.x_label:
            ax.set_xlabel(spec.x_label, fontsize=11, color="#334155")
        if spec.y_label:
            ax.set_ylabel(spec.y_label, fontsize=11, color="#334155")
        if kind not in ("pie", "donut", "radar"):
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color("#CBD5E1")
            ax.spines["bottom"].set_color("#CBD5E1")
            ax.tick_params(colors="#475569", labelsize=10)
            ax.grid(True, axis="y", linestyle="--", color="#E2E8F0", alpha=0.7)
            ax.set_axisbelow(True)

    # ─── individual renderers ─────────────────────────────────────────
    def _render_line(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        colors = _palette(accent_hex, max(1, len(spec.series)))
        cats = spec.categories or None
        for i, s in enumerate(spec.series):
            ys = _series_to_y(s)
            xs = list(range(len(ys)))
            ax.plot(xs, ys, marker="o", linewidth=2.5, color=colors[i],
                    label=s.get("name") or f"Series {i+1}")
        if cats:
            ax.set_xticks(range(len(cats)))
            ax.set_xticklabels(cats, rotation=0)
        if len(spec.series) > 1:
            ax.legend(loc="best", frameon=False, fontsize=10)

    def _render_area(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        colors = _palette(accent_hex, max(1, len(spec.series)))
        cats = spec.categories or None
        for i, s in enumerate(spec.series):
            ys = _series_to_y(s)
            xs = list(range(len(ys)))
            ax.fill_between(xs, ys, alpha=0.35, color=colors[i])
            ax.plot(xs, ys, linewidth=2.0, color=colors[i],
                    label=s.get("name") or f"Series {i+1}")
        if cats:
            ax.set_xticks(range(len(cats)))
            ax.set_xticklabels(cats)
        if len(spec.series) > 1:
            ax.legend(loc="best", frameon=False, fontsize=10)

    def _render_bar(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        # horizontal bar
        cats = spec.categories or [f"#{i+1}" for i in range(len(_series_to_y(spec.series[0]) if spec.series else []))]
        colors = _palette(accent_hex, max(1, len(spec.series)))
        if not spec.series:
            return
        n_groups = len(cats)
        n_series = len(spec.series)
        bar_h = 0.8 / max(1, n_series)
        ys_base = np.arange(n_groups)
        for i, s in enumerate(spec.series):
            ys = _series_to_y(s)[:n_groups]
            offset = (i - (n_series - 1) / 2.0) * bar_h
            ax.barh(ys_base + offset, ys, height=bar_h, color=colors[i],
                    label=s.get("name") or f"Series {i+1}")
        ax.set_yticks(ys_base)
        ax.set_yticklabels(cats)
        ax.invert_yaxis()
        if n_series > 1:
            ax.legend(loc="best", frameon=False, fontsize=10)

    def _render_column(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        cats = spec.categories or [f"#{i+1}" for i in range(len(_series_to_y(spec.series[0]) if spec.series else []))]
        colors = _palette(accent_hex, max(1, len(spec.series)))
        if not spec.series:
            return
        n_groups = len(cats)
        n_series = len(spec.series)
        bar_w = 0.8 / max(1, n_series)
        xs_base = np.arange(n_groups)
        for i, s in enumerate(spec.series):
            ys = _series_to_y(s)[:n_groups]
            offset = (i - (n_series - 1) / 2.0) * bar_w
            ax.bar(xs_base + offset, ys, width=bar_w, color=colors[i],
                   label=s.get("name") or f"Series {i+1}")
        ax.set_xticks(xs_base)
        ax.set_xticklabels(cats, rotation=0)
        if n_series > 1:
            ax.legend(loc="best", frameon=False, fontsize=10)

    def _render_stacked_bar(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        cats = spec.categories or [f"#{i+1}" for i in range(len(_series_to_y(spec.series[0]) if spec.series else []))]
        colors = _palette(accent_hex, max(1, len(spec.series)))
        n_groups = len(cats)
        xs = np.arange(n_groups)
        bottom = np.zeros(n_groups)
        for i, s in enumerate(spec.series):
            ys = np.array(_series_to_y(s)[:n_groups] + [0.0] * max(0, n_groups - len(_series_to_y(s))))[:n_groups]
            ax.bar(xs, ys, bottom=bottom, color=colors[i],
                   label=s.get("name") or f"Series {i+1}")
            bottom = bottom + ys
        ax.set_xticks(xs); ax.set_xticklabels(cats)
        ax.legend(loc="best", frameon=False, fontsize=10)

    def _render_scatter(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        colors = _palette(accent_hex, max(1, len(spec.series)))
        for i, s in enumerate(spec.series):
            xs, ys = _series_to_xy(s)
            ax.scatter(xs, ys, s=60, color=colors[i], alpha=0.75,
                       label=s.get("name") or f"Series {i+1}", edgecolors="white", linewidths=1.0)
        if len(spec.series) > 1:
            ax.legend(loc="best", frameon=False, fontsize=10)

    def _render_bubble(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        colors = _palette(accent_hex, max(1, len(spec.series)))
        for i, s in enumerate(spec.series):
            xs, ys, zs = _series_to_xyz(s)
            sizes = [max(20.0, z * 8.0) for z in zs]
            ax.scatter(xs, ys, s=sizes, color=colors[i], alpha=0.55,
                       label=s.get("name") or f"Series {i+1}", edgecolors="white", linewidths=1.0)
        if len(spec.series) > 1:
            ax.legend(loc="best", frameon=False, fontsize=10)

    def _render_pie(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        if not spec.series:
            return
        ys = _series_to_y(spec.series[0])
        labels = spec.categories or [f"Slice {i+1}" for i in range(len(ys))]
        colors = _palette(accent_hex, len(ys))
        ax.pie(ys, labels=labels, colors=colors, autopct="%1.0f%%",
               startangle=90, textprops={"fontsize": 11, "color": "#0F172A"})
        ax.set_aspect("equal")
        if spec.title:
            ax.set_title(spec.title, fontsize=14, fontweight="bold", pad=12, color="#0F172A")

    def _render_donut(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        if not spec.series:
            return
        ys = _series_to_y(spec.series[0])
        labels = spec.categories or [f"Slice {i+1}" for i in range(len(ys))]
        colors = _palette(accent_hex, len(ys))
        wedges, _, _ = ax.pie(ys, labels=labels, colors=colors, autopct="%1.0f%%",
                              startangle=90, pctdistance=0.78,
                              wedgeprops={"width": 0.45, "edgecolor": "white", "linewidth": 2})
        ax.set_aspect("equal")
        if spec.title:
            ax.set_title(spec.title, fontsize=14, fontweight="bold", pad=12, color="#0F172A")

    def _render_histogram(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        if not spec.series:
            return
        data = _series_to_y(spec.series[0])
        color = _palette(accent_hex, 1)[0]
        ax.hist(data, bins=min(20, max(5, len(data) // 2 or 5)),
                color=color, edgecolor="white", alpha=0.85)

    def _render_box(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        datasets = [_series_to_y(s) for s in spec.series if _series_to_y(s)]
        labels = [s.get("name") or f"S{i+1}" for i, s in enumerate(spec.series) if _series_to_y(s)]
        if not datasets:
            return
        color = _palette(accent_hex, 1)[0]
        bp = ax.boxplot(datasets, tick_labels=labels, patch_artist=True,
                        boxprops=dict(facecolor=color, alpha=0.55, edgecolor=color),
                        medianprops=dict(color="#0F172A", linewidth=2))
        # silence linter
        _ = bp

    def _render_heatmap(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        matrix = spec.matrix
        if not matrix:
            # Fall back: stack series rows.
            matrix = [_series_to_y(s) for s in spec.series if _series_to_y(s)]
        if not matrix:
            return
        arr = np.array(matrix, dtype=float)
        im = ax.imshow(arr, aspect="auto", cmap="Blues")
        ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        if spec.categories:
            ax.set_xticks(range(len(spec.categories)))
            ax.set_xticklabels(spec.categories, rotation=30, ha="right")
        row_labels = [s.get("name") for s in spec.series if s.get("name")]
        if row_labels and len(row_labels) == arr.shape[0]:
            ax.set_yticks(range(len(row_labels)))
            ax.set_yticklabels(row_labels)

    def _render_waterfall(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        if not spec.series:
            return
        ys = _series_to_y(spec.series[0])
        cats = spec.categories or [f"#{i+1}" for i in range(len(ys))]
        running = 0.0
        positives_color = _palette(accent_hex, 1)[0]
        neg_color = (0.94, 0.34, 0.36)
        bars = []
        for i, v in enumerate(ys):
            color = positives_color if v >= 0 else neg_color
            ax.bar(i, v, bottom=running, color=color)
            running += v
            bars.append(running)
        ax.set_xticks(range(len(cats)))
        ax.set_xticklabels(cats, rotation=0)
        ax.axhline(0, color="#475569", linewidth=0.8)

    def _render_radar(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        # Replace the cartesian axes with a polar one — matplotlib quirk:
        # we need the figure, not the existing ax.
        fig = ax.figure
        fig.delaxes(ax)
        ax_polar = fig.add_subplot(111, projection="polar")
        cats = spec.categories or []
        n = len(cats)
        if n == 0 and spec.series:
            n = len(_series_to_y(spec.series[0]))
            cats = [f"#{i+1}" for i in range(n)]
        if n < 3:
            return
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
        angles += angles[:1]
        colors = _palette(accent_hex, max(1, len(spec.series)))
        for i, s in enumerate(spec.series):
            vals = _series_to_y(s)[:n]
            if len(vals) < n:
                vals += [0.0] * (n - len(vals))
            vals += vals[:1]
            ax_polar.plot(angles, vals, color=colors[i], linewidth=2,
                          label=s.get("name") or f"Series {i+1}")
            ax_polar.fill(angles, vals, color=colors[i], alpha=0.2)
        ax_polar.set_xticks(angles[:-1])
        ax_polar.set_xticklabels(cats, fontsize=10)
        ax_polar.tick_params(colors="#475569")
        if spec.title:
            ax_polar.set_title(spec.title, fontsize=14, fontweight="bold", pad=18, color="#0F172A")
        if len(spec.series) > 1:
            ax_polar.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1), frameon=False, fontsize=10)

    def _render_funnel(self, ax, spec: ChartSpec, accent_hex: str) -> None:
        if not spec.series:
            return
        ys = _series_to_y(spec.series[0])
        cats = spec.categories or [f"Stage {i+1}" for i in range(len(ys))]
        if not ys:
            return
        max_y = max(ys) or 1.0
        color = _palette(accent_hex, 1)[0]
        # Draw centered horizontal bars with decreasing widths.
        for i, (label, v) in enumerate(zip(cats, ys)):
            width = (v / max_y)
            ax.barh(i, width, left=(1 - width) / 2, color=color, alpha=0.6 + 0.05 * i,
                    edgecolor="white", linewidth=2)
            ax.text(0.5, i, f"{label}: {int(v)}", ha="center", va="center",
                    fontsize=11, color="#0F172A", fontweight="bold")
        ax.set_yticks([])
        ax.set_xticks([])
        ax.invert_yaxis()
        ax.set_xlim(0, 1)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_visible(False)
        ax.spines["left"].set_visible(False)

    # ─── dispatch table ───────────────────────────────────────────────
    _dispatch = {
        ChartKind.line.value: _render_line,
        ChartKind.area.value: _render_area,
        ChartKind.bar.value: _render_bar,
        ChartKind.column.value: _render_column,
        ChartKind.stacked_bar.value: _render_stacked_bar,
        ChartKind.scatter.value: _render_scatter,
        ChartKind.bubble.value: _render_bubble,
        ChartKind.pie.value: _render_pie,
        ChartKind.donut.value: _render_donut,
        ChartKind.histogram.value: _render_histogram,
        ChartKind.box.value: _render_box,
        ChartKind.heatmap.value: _render_heatmap,
        ChartKind.waterfall.value: _render_waterfall,
        ChartKind.radar.value: _render_radar,
        ChartKind.funnel.value: _render_funnel,
    }


# ────────────────────────────────────────────────────────────────────────
#  ChartSelector — heuristic data-shape → chart-kind suggester
# ────────────────────────────────────────────────────────────────────────

class ChartSelector:
    """Pick a sensible ChartKind for a (categories, series) shape."""

    @staticmethod
    def suggest(*, series: Sequence[Dict[str, Any]],
                categories: Optional[Sequence[str]] = None,
                hint: Optional[str] = None) -> ChartKind:
        """
        Heuristics:
        - 1 series, ≤6 categories, sums approx 100 → pie.
        - 1 series, ≤8 categories          → column.
        - 1 series, time-like categories    → line.
        - multiple series, same length     → line if numeric x else stacked_bar.
        - series of [x,y] pairs            → scatter; with z → bubble.
        - matrix payload                   → heatmap.
        - hint == "trend"|"growth"         → line; "share" → donut.
        """
        if hint:
            h = hint.lower().strip()
            if h in ("trend", "growth", "time"): return ChartKind.line
            if h in ("share", "distribution", "split"): return ChartKind.donut
            if h in ("compare", "comparison", "rank"): return ChartKind.column
            if h in ("flow", "conversion", "funnel"): return ChartKind.funnel
            if h in ("correlation", "relationship"): return ChartKind.scatter

        if not series:
            return ChartKind.column

        n_series = len(series)
        first = series[0]
        first_data = first.get("data") or []

        # Detect pair / triple data → scatter / bubble.
        if first_data and isinstance(first_data[0], (list, tuple)):
            if len(first_data[0]) >= 3:
                return ChartKind.bubble
            return ChartKind.scatter

        n_points = len(first_data)
        if n_series == 1:
            ys = [float(d) for d in first_data if isinstance(d, (int, float))]
            total = sum(ys) if ys else 0.0
            if 0 <= n_points <= 6 and 95 <= total <= 105:
                return ChartKind.pie
            if categories and any(_looks_time_like(c) for c in categories):
                return ChartKind.line
            return ChartKind.column

        # Multi-series.
        if categories and any(_looks_time_like(c) for c in categories):
            return ChartKind.line
        return ChartKind.stacked_bar


_TIME_HINTS = ("q1", "q2", "q3", "q4", "20", "jan", "feb", "mar", "apr",
               "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
               "year", "month", "week", "day")


def _looks_time_like(label: str) -> bool:
    if not isinstance(label, str):
        return False
    s = label.lower().strip()
    return any(h in s for h in _TIME_HINTS)
