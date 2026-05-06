"""
Timeline visualization module using Panel + HoloViews.
"""

from __future__ import annotations

from typing import Literal

import holoviews as hv
import pandas as pd
import panel as pn

hv.extension("bokeh")
pn.extension()

AggLevel = Literal["none", "day", "month", "year"]

_PALETTE = [
    "#3266ad", "#c45c2e", "#2a9d6e", "#8f5bbf",
    "#c4923c", "#3b8fbf", "#b84a6b", "#5e7a2e",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _get_chunk(row: pd.Series, var: str, dim: int) -> int | None:
    meta = (
        (row.get("variables") or {}).get(var)
        or (row.get("coords") or {}).get(var)
    )
    if not meta:
        return None
    chunks = meta.get("chunks")
    if not chunks or dim >= len(chunks):
        return None
    return int(chunks[dim])


def _all_variables(df: pd.DataFrame) -> list[str]:
    names: set[str] = set()
    for col in ("variables", "coords"):
        if col in df.columns:
            df[col].dropna().apply(
                lambda d: names.update(d.keys()) if isinstance(d, dict) else None
            )
    return sorted(names)


def _max_dims(df: pd.DataFrame, var: str) -> int:
    best = 1
    for col in ("variables", "coords"):
        if col not in df.columns:
            continue
        for d in df[col].dropna():
            if not isinstance(d, dict):
                continue
            meta = d.get(var)
            if meta and meta.get("chunks"):
                best = max(best, len(meta["chunks"]))
    return best


def _agg_period(dates: pd.Series, level: AggLevel) -> pd.Series:
    if level == "day":
        return dates.dt.floor("D")
    if level == "month":
        return dates.dt.to_period("M").dt.to_timestamp()
    if level == "year":
        return dates.dt.to_period("Y").dt.to_timestamp()
    return dates


# ---------------------------------------------------------------------------
# ChunkTimeline class
# ---------------------------------------------------------------------------

class ChunkTimeline:
    """
    Parameters
    ----------
    df : pd.DataFrame
        Must contain:
          - ``date``      : datetime column
          - ``variables`` : dict per row  {varname: {chunks, shape, dtype, ...}}
          - ``coords``    : dict per row  {canonical: {chunks, ...}
                             or {canonical: [{path, chunks, ...}, ...]}}
        Rows with a non-empty ``error`` column are silently dropped.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = self._prepare(df)
        self._vars = _all_variables(self._df)
        if not self._vars:
            raise ValueError("No variables or coords found in the dataframe.")

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    @property
    def variables(self) -> list[str]:
        return self._vars

    def widget(self) -> pn.viewable.Viewable:
        all_dims = sorted({
            d
            for v in self._vars
            for d in range(_max_dims(self._df, v))
        })

        var_sel = pn.widgets.Select(
            name="Variable", options=self._vars, value=self._vars[0], width=180,
        )
        dim_sel = pn.widgets.Select(
            name="Chunk dimension", options=all_dims, value=0, width=120,
        )
        agg_sel = pn.widgets.Select(
            name="Aggregate by",
            options=["none", "day", "month", "year"],
            value="none",
            width=120,
        )

        n_card = pn.indicators.Number(name="Granules", value=0, format="{value:,}", font_size="24pt")
        distinct_card = pn.indicators.Number(name="Chunk shapes", value=0, format="{value}", font_size="24pt")
        trans_card = pn.indicators.Number(name="Transitions", value=0, format="{value}", font_size="24pt")
        values_md = pn.pane.Markdown("", styles={"font-size": "12px", "color": "#555"})

        @pn.depends(var_sel, dim_sel, agg_sel)
        def _plot(var: str, dim: int, agg: str) -> pn.pane.Markdown | pn.pane.HoloViews:
            pts = self._build_series(var, int(dim), agg)
            if pts.empty:
                n_card.value = distinct_card.value = trans_card.value = 0
                values_md.object = "_no data_"
                return pn.pane.Markdown(f"**No data** for variable=`{var}`, dim={dim}.")

            distinct = sorted(pts["chunk_mean"].unique())
            n_trans = int((pts["chunk_mean"] != pts["chunk_mean"].shift()).iloc[1:].sum())

            n_card.value = int(pts["n"].sum())
            distinct_card.value = len(distinct)
            trans_card.value = n_trans
            values_md.object = "**values**  \n" + "  \n".join(f"`{v}`" for v in distinct)

            return pn.pane.HoloViews(
                self._make_hvplot(pts, var, int(dim), agg),
                sizing_mode="stretch_width",
            )

        sidebar = pn.Column(
            pn.pane.Markdown("### controls"),
            var_sel, dim_sel, agg_sel,
            pn.layout.Divider(),
            pn.pane.Markdown("### summary"),
            pn.Row(n_card, distinct_card, trans_card),
            pn.layout.Divider(),
            values_md,
            width=220,
            margin=(0, 16, 0, 0),
        )

        layout = pn.Row(
            sidebar,
            pn.Column(_plot, sizing_mode="stretch_width"),
            sizing_mode="stretch_width",
        )
        layout.servable()
        return layout

    def show(self, **kwargs: object) -> None:
        self.widget().show(**kwargs)

    def save(self, path: str = "chunk_timeline.html") -> None:
        self.widget().save(path, embed=True)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "error" in df.columns:
            df = df[df["error"].isna() | (df["error"] == "")]

        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

        if "coords" in df.columns:
            def _flatten(d: object) -> dict:
                if not isinstance(d, dict):
                    return {}
                return {
                    k: (v[0] if isinstance(v, list) and v else v)
                    for k, v in d.items()
                }
            df["coords"] = df["coords"].apply(_flatten)

        return df

    def _build_series(self, var: str, dim: int, agg: AggLevel) -> pd.DataFrame:
        rows = []
        for _, r in self._df.iterrows():
            v = _get_chunk(r, var, dim)
            if v is None:
                continue
            rows.append({"date": r["date"], "chunk": v})

        if not rows:
            return pd.DataFrame()

        pts = pd.DataFrame(rows)

        if agg != "none":
            pts["period"] = _agg_period(pts["date"], agg)
            out = (
                pts.groupby("period")["chunk"]
                .agg(chunk_mean="mean", chunk_min="min", chunk_max="max", n="count")
                .reset_index()
                .rename(columns={"period": "date"})
            )
            out["chunk_mean"] = out["chunk_mean"].round().astype(int)
        else:
            pts["chunk_mean"] = pts["chunk"]
            pts["chunk_min"] = pts["chunk"]
            pts["chunk_max"] = pts["chunk"]
            pts["n"] = 1
            out = pts.drop(columns=["chunk"]).reset_index(drop=True)

        return out

    def _make_hvplot(
        self,
        pts: pd.DataFrame,
        var: str,
        dim: int,
        agg: AggLevel,
    ) -> hv.core.overlay.Overlay:
        distinct = sorted(pts["chunk_mean"].unique())
        color_map = {v: _PALETTE[i % len(_PALETTE)] for i, v in enumerate(distinct)}

        pts = pts.copy()
        pts["color"] = pts["chunk_mean"].map(color_map)
        pts["transition"] = (pts["chunk_mean"] != pts["chunk_mean"].shift()).fillna(False)
        pts["label"] = pts["chunk_mean"].astype(str)

        n_trans = int(pts["transition"].iloc[1:].sum())
        title = (
            f"{var}  \u00b7  dim {dim}"
            + (f"  \u00b7  aggregated by {agg}" if agg != "none" else "")
            + f"  \u00b7  {n_trans} transition{'s' if n_trans != 1 else ''}"
        )

        curves = []
        seg_x = [pts.iloc[0]["date"]]
        seg_y = [pts.iloc[0]["chunk_mean"]]
        cur = pts.iloc[0]["chunk_mean"]

        for i in range(1, len(pts)):
            v = pts.iloc[i]["chunk_mean"]
            if v != cur:
                seg_x.append(pts.iloc[i]["date"])
                seg_y.append(v)
                curves.append(
                    hv.Curve(
                        pd.DataFrame({"date": seg_x, "chunk": seg_y}),
                        kdims="date", vdims="chunk",
                    ).opts(color=color_map[cur], line_width=2, show_legend=False)
                )
                seg_x, seg_y, cur = [pts.iloc[i]["date"]], [v], v
            else:
                seg_x.append(pts.iloc[i]["date"])
                seg_y.append(v)

        curves.append(
            hv.Curve(
                pd.DataFrame({"date": seg_x, "chunk": seg_y}),
                kdims="date", vdims="chunk",
            ).opts(color=color_map[cur], line_width=2, show_legend=False)
        )

        all_pts = hv.Points(
            pts, kdims=["date", "chunk_mean"], vdims=["color", "label", "n"],
        ).opts(
            color="color",
            size=5,
            tools=["hover"],
            hover_tooltips=[
                ("date", "@date{%F}"),
                ("chunk", "@chunk_mean"),
                ("n", "@n"),
            ],
            hover_formatters={"@date": "datetime"},
            show_legend=False,
        )

        t_pts = pts[pts["transition"] & (pts.index > 0)]
        if not t_pts.empty:
            trans_pts = hv.Points(
                t_pts, kdims=["date", "chunk_mean"], vdims=["color", "label"],
            ).opts(
                color="color",
                size=14,
                marker="circle_dot",
                line_width=2,
                fill_alpha=0,
                tools=["hover"],
                hover_tooltips=[
                    ("transition to", "@chunk_mean"),
                    ("date", "@date{%F}"),
                ],
                hover_formatters={"@date": "datetime"},
                legend_label="transition",
            )
        else:
            trans_pts = hv.Points([]).opts(show_legend=False)

        if agg != "none" and (pts["chunk_max"] != pts["chunk_min"]).any():
            band = hv.Area(
                pts, kdims="date", vdims=["chunk_min", "chunk_max"],
            ).opts(
                alpha=0.12, color="#3266ad", line_alpha=0,
                legend_label="min/max range",
            )
        else:
            band = hv.Area([]).opts(show_legend=False)

        legend_scatters = [
            hv.Scatter({"date": [], "chunk": []}).opts(
                color=color_map[v], size=8, legend_label=f"chunk {v}", show_legend=True,
            )
            for v in distinct
        ]

        overlay = (
            band
            * hv.Overlay(curves)
            * all_pts
            * trans_pts
            * hv.Overlay(legend_scatters)
        ).opts(
            hv.opts.Overlay(
                width=720, height=380,
                title=title,
                xlabel="date",
                ylabel=f"chunk size  (dim {dim})",
                legend_position="top_left",
                toolbar="above",
                show_grid=True,
                gridstyle={"grid_line_alpha": 0.2},
            )
        )
        return overlay
