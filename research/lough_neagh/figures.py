"""Static scientific figures; no model predictions are presented as lake maps."""
import csv
import json
import os
import tempfile

os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="lough-mpl-"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

from sentinel_catalogue import ROOT

OUT = ROOT / "docs/lough-neagh/figures"
PAPER, INK, TEAL, RUST = "#faf6ef", "#182e32", "#136b72", "#ad3930"


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    plt.rcParams.update({"figure.facecolor": PAPER, "axes.facecolor": PAPER, "text.color": INK,
        "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 10, "savefig.facecolor": PAPER})
    with (ROOT / "data/lough-neagh/derived/exploratory-predictions.csv").open() as f:
        rows = list(csv.DictReader(f))
    rows = [r for r in rows if r["scheme"] == "leave_one_date_out" and r["model"] == "red_nir_linear"]
    report = json.loads((ROOT / "data/lough-neagh/derived/exploratory-validation.json").read_text())
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.6), gridspec_kw={"wspace": .38})
    for station, label, color in [("L1278", "Rea's Wood", TEAL), ("L1279", "Washing Bay", RUST)]:
        selected = [r for r in rows if r["station"] == station]
        x = [float(r["observed"]) for r in selected]
        y = [float(r["prediction"]) for r in selected]
        axes[0].scatter(x, y, label=label, color=color, s=28, alpha=.8, edgecolor=PAPER, linewidth=.4)
        axes[1].scatter(x, np.array(y)-x, color=color, s=28, alpha=.8, edgecolor=PAPER, linewidth=.4)
    axes[0].plot([0, 35], [0, 35], color="#788885", linestyle="--", linewidth=1)
    axes[0].set(xlim=(-1, 35), ylim=(-1, 35), xlabel="Published DAERA value (NTU)", ylabel="Held-out model prediction (NTU)", title="A  Little predictive separation")
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    axes[1].axhline(0, color="#788885", linewidth=1)
    axes[1].set(xlabel="Published DAERA value (NTU)", ylabel="Prediction minus probe (NTU)", title="B  Higher values underestimated")
    schemes = ["leave_one_date_out", "forward_blocks", "station_and_date_holdout"]
    for model, label, offset, color in [("station_median", "Station median baseline", -.17, "#829794"), ("red_nir_linear", "Red + NIR regression", .17, RUST)]:
        values = [next(r["rmse"] for r in report["metrics"] if r["scheme"] == scheme and r["model"] == model) for scheme in schemes]
        axes[2].bar(np.arange(3)+offset, values, width=.32, color=color, label=label)
    axes[2].set(xticks=range(3), xticklabels=["Whole date", "Forward\ntime", "Station\n+ dates"], ylabel="RMSE (NTU)", title="C  Transfer tests also fail")
    axes[2].legend(frameon=False, fontsize=8, loc="upper left")
    axes[2].set_ylim(0, 11)
    fig.suptitle("Lough Neagh · exploratory validation, not a satellite turbidity product", x=.06, ha="left", fontsize=15, fontfamily="serif")
    fig.text(.06, .025, "82 screened matchups / 60 dates. Provisional, threshold-filtered probes; Sen2Cor BOA. No aquatic correction validation.\nNo dates cross training/test boundaries. Station baseline falls back to training median for an unseen station.", fontsize=9, color="#5b686a")
    fig.subplots_adjust(top=.80, bottom=.24, left=.06, right=.98)
    fig.savefig(OUT / "validation.png", dpi=180)
    plt.close(fig)

    feature = json.loads((ROOT / "data/lough-neagh/raw/geography/daera-lough-neagh.geojson").read_text())["features"][0]
    projection = Transformer.from_crs(4326, 32629, always_xy=True).transform
    lake = transform(projection, shape(feature["geometry"]))
    fig, ax = plt.subplots(figsize=(7, 7.2))
    for polygon in getattr(lake, "geoms", [lake]):
        x, y = polygon.exterior.xy
        ax.fill(np.array(x)/1000, np.array(y)/1000, color="#e2e9e5", ec="#728885", linewidth=.7)
        for ring in polygon.interiors:
            x, y = ring.xy
            ax.fill(np.array(x)/1000, np.array(y)/1000, color=PAPER)
    audit = json.loads((ROOT / "data/lough-neagh/derived/matchup-audit.json").read_text())
    for row in audit["station_geography"]:
        x, y = projection(row["lon"], row["lat"])
        included = row["inside_lake"]
        ax.scatter([x/1000], [y/1000], color=TEAL if included else RUST, marker="o" if included else "x", s=55, zorder=3)
        name = row["station_name"] + ("\nOutlet; excluded" if not included else f"\n~{round(row['shore_distance_m'])} m to shore")
        offset = (-14, -10) if row["station"] == "L1278" else (12, 8) if included else (18, -22)
        align = "right" if row["station"] == "L1278" else "left"
        ax.annotate(name, (x/1000, y/1000), xytext=offset, textcoords="offset points", fontsize=10, color=INK, ha=align)
    ax.set_aspect("equal")
    ax.set(xlabel="UTM zone 29N easting (km)", ylabel="Northing (km)")
    ax.set_xlim(646, 687)
    ax.set_title("Two lake stations cannot validate every shore", loc="left", fontfamily="serif", fontsize=16, pad=25)
    ax.text(.01, 1.01, "Study geography only · no turbidity estimates shown", transform=ax.transAxes, fontsize=10, color="#5b686a")
    ax.plot([650, 655], [6036, 6036], color=INK, lw=2)
    ax.text(652.5, 6035.3, "5 km", ha="center", va="top", fontsize=9)
    fig.text(.12, .035, "Boundary: DAERA Lake Water Bodies 2016. Points: current DAERA probe coordinates.\nHistorical location/deployment consistency remains unconfirmed.", fontsize=9, color="#5b686a")
    fig.subplots_adjust(left=.12, right=.94, top=.88, bottom=.15)
    fig.savefig(OUT / "station-geography.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
