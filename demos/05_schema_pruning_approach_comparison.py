"""
Generate a 2D design space plot comparing schema linking
approaches for text-to-SQL.

X-axis: Schema linking cost category (log scale)
Y-axis: Generalisation level (single-schema to cross-DB)

Usage:
    uv run python demos/05_schema_pruning_approach_comparison.py
"""

import matplotlib.pyplot as plt
import numpy as np


def _add_method(ax, m):
    """Plot one method: marker, leader line, name, details."""
    is_pruner = m["name"] == "This pruner"
    ha = m.get("ha", "left")
    nox, noy = m["name_offset"]
    dox, doy = m["detail_offset"]

    # Marker
    ax.scatter(
        m["x"], m["y"],
        s=m["size"],
        c=m["color"],
        marker=m["marker"],
        zorder=5,
        edgecolors="white",
        linewidth=2,
    )

    # Name label - with leader arrow if specified
    arrow_props = None
    if m.get("arrow"):
        arrow_props = dict(
            arrowstyle="-",
            color="#BEBEBE",
            linewidth=1.5,
            shrinkA=0,
            shrinkB=6,
        )

    ax.annotate(
        m["name"],
        xy=(m["x"], m["y"]),
        xytext=(nox, noy),
        textcoords="offset points",
        fontsize=10 if is_pruner else 9,
        fontweight="bold",
        color=m["color"],
        ha=ha,
        va="bottom",
        arrowprops=arrow_props,
    )

    # Detail lines (tech + spider)
    detail = m["tech"]
    if m.get("spider"):
        detail += f"\nSpider EX: {m['spider']}"

    ax.annotate(
        detail,
        xy=(m["x"], m["y"]),
        xytext=(dox, doy),
        textcoords="offset points",
        fontsize=8 if is_pruner else 7.5,
        fontweight="normal",
        color=m["color"],
        ha=ha,
        va="top",
        linespacing=1.3,
        alpha=0.85,
    )


def main() -> None:
    fig, ax = plt.subplots(figsize=(12, 7.5))
    ax.set_facecolor("#FAFAFA")
    fig.patch.set_facecolor("white")

    # --- Shaded regions ---
    ax.axhspan(
        -0.7, 1.5,
        xmin=0, xmax=0.42,
        color="#ebe6fb", alpha=0.5, zorder=0,
    )
    ax.text(
        0.20, -0.55,
        "Production deployment\n"
        "(known schema, zero latency)",
        fontsize=9, color="#6a3db5",
        fontweight="bold",
        ha="left", va="bottom",
        style="italic",
    )

    ax.axhspan(
        2.5, 4.1,
        xmin=0.58, xmax=1.0,
        color="#f3e8ff", alpha=0.5, zorder=0,
    )
    ax.text(
        35000, 3.95,
        "Research benchmarks\n"
        "(unseen schemas, LLM-dependent)",
        fontsize=9, color="#8100e6",
        fontweight="bold",
        ha="right", va="top",
        style="italic",
    )

    # --- Methods ---
    # Colours: pruner = purple accent (protagonist)
    #          others = muted greys
    methods = [
        {
            "name": "This pruner",
            "tech": "Keyword + entity map\n+ FK graph",
            "x": 0.5,
            "y": 0,
            "spider": None,
            "color": "#8100e6",
            "marker": "D",
            "size": 280,
            "name_offset": (16, 16),
            "detail_offset": (16, 10),
            "ha": "left",
            "arrow": False,
        },
        {
            "name": "DAIL-SQL",
            "tech": "n-gram matching (RAT-SQL)",
            "x": 8,
            "y": 2,
            "spider": "86.6%",
            "color": "#525658",
            "marker": "D",
            "size": 220,
            "name_offset": (16, 10),
            "detail_offset": (16, 4),
            "ha": "left",
            "arrow": False,
        },
        {
            "name": "RESDSQL",
            "tech": "RoBERTa-Large cross-encoder",
            "x": 150,
            "y": 1,
            "spider": "79.9%",
            "color": "#525658",
            "marker": "s",
            "size": 220,
            "name_offset": (16, 10),
            "detail_offset": (16, 4),
            "ha": "left",
            "arrow": False,
        },
        {
            "name": "DIN-SQL",
            "tech": "GPT-4 few-shot prompting",
            "x": 2000,
            "y": 3,
            "spider": "85.3%",
            "color": "#525658",
            "marker": "o",
            "size": 220,
            "name_offset": (-120, -50),
            "detail_offset": (-120, -56),
            "ha": "left",
            "arrow": True,
        },
        {
            "name": "C3SQL",
            "tech": "GPT-3.5 zero-shot + voting",
            "x": 6000,
            "y": 3,
            "spider": "82.3%",
            "color": "#525658",
            "marker": "o",
            "size": 220,
            "name_offset": (-30, -50),
            "detail_offset": (-30, -56),
            "ha": "left",
            "arrow": True,
        },
    ]

    for m in methods:
        _add_method(ax, m)

    # --- Axes ---
    ax.set_xscale("log")
    ax.set_xlim(0.15, 40000)
    ax.set_ylim(-0.7, 4.2)

    ax.set_xticks([1, 10, 100, 1000, 10000])
    ax.set_xticklabels(
        [
            "Sub-ms\n(local)",
            "~10ms\n(local)",
            "~100ms\n(GPU)",
            "~1s\n(1 LLM call)",
            "~10s\n(multi-LLM)",
        ],
        fontsize=9,
        color="#525658",
    )

    ax.set_yticks([0, 1, 2, 3])
    ax.set_yticklabels(
        [
            "Single-schema\n(domain config)",
            "Cross-DB\n(training data)",
            "Cross-DB\n(example pool)",
            "Cross-DB\n(zero / few-shot)",
        ],
        fontsize=10,
        color="#525658",
    )

    ax.set_xlabel(
        "Schema Linking Cost (order of magnitude)",
        fontsize=13,
        fontweight="bold",
        labelpad=14,
        color="#151616",
    )
    ax.set_ylabel(
        "Generalisation",
        fontsize=13,
        fontweight="bold",
        labelpad=12,
        color="#151616",
    )

    # --- Grid ---
    ax.grid(
        True, alpha=0.2, linewidth=0.8, color="#D7DADC",
    )
    ax.tick_params(axis="both", which="major", labelsize=10)
    for spine in ax.spines.values():
        spine.set_color("#D7DADC")

    # --- Legend ---
    legend_handles = [
        plt.Line2D(
            [0], [0],
            marker="D", color="w",
            markerfacecolor="#8100e6",
            markersize=10,
            label="Deterministic (this work)",
        ),
        plt.Line2D(
            [0], [0],
            marker="D", color="w",
            markerfacecolor="#525658",
            markersize=10,
            label="Deterministic",
        ),
        plt.Line2D(
            [0], [0],
            marker="s", color="w",
            markerfacecolor="#525658",
            markersize=10,
            label="Trained model",
        ),
        plt.Line2D(
            [0], [0],
            marker="o", color="w",
            markerfacecolor="#525658",
            markersize=10,
            label="LLM-prompted",
        ),
    ]
    ax.legend(
        handles=legend_handles,
        loc="lower right",
        fontsize=10,
        framealpha=0.9,
        edgecolor="#D7DADC",
        title="Approach type",
        title_fontsize=10,
    )

    # --- Title ---
    ax.set_title(
        "Schema Linking for Text-to-SQL:"
        " How Approaches Compare",
        fontsize=15,
        fontweight="bold",
        pad=18,
        color="#151616",
    )

    # --- Footnote ---
    fig.text(
        0.5,
        0.005,
        "X-axis shows order-of-magnitude cost"
        " categories, not precise measurements."
        "  Spider execution accuracy (EX) on test"
        " set except DIN-SQL (dev set, GPT-4).",
        ha="center",
        fontsize=8.5,
        color="#525658",
        style="italic",
    )

    plt.tight_layout(rect=[0, 0.035, 1, 1])

    out = "docs/text-to-sql-schema-pruning-approach-comparison-v1.png"
    plt.savefig(out, dpi=180, bbox_inches="tight")
    print(f"Saved to {out}")
    plt.close()


if __name__ == "__main__":
    main()
