"""Plotting helpers for the SASMaker workshop."""

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


def plot_goose_timeline(
    packet_data: pd.DataFrame,
    *,
    stream_column: str = "goID",
):
    """Plot each captured GOOSE transmission on a timeline."""
    required_columns = {"RelativeTime", stream_column}
    missing_columns = required_columns.difference(packet_data.columns)

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required columns: {missing}")

    plot_data = packet_data.dropna(
        subset=["RelativeTime", stream_column]
    ).copy()

    if plot_data.empty:
        raise ValueError("No GOOSE packets are available to plot")

    streams = list(plot_data[stream_column].drop_duplicates())
    stream_positions = {
        stream: position
        for position, stream in enumerate(streams)
    }

    plot_data["stream_position"] = plot_data[stream_column].map(
        stream_positions
    )

    figure_height = max(3.0, 0.6 * len(streams) + 1.5)
    figure, axes = plt.subplots(
        figsize=(10, figure_height),
        constrained_layout=True,
    )

    axes.scatter(
        plot_data["RelativeTime"],
        plot_data["stream_position"],
        marker="|",
        s=180,
        linewidths=1.5,
        color="#0065BD",
    )

    axes.set_yticks(range(len(streams)))
    axes.set_yticklabels(streams)
    axes.set_xlabel("Time since first GOOSE packet (s)")
    axes.set_ylabel("GOOSE stream")
    axes.set_title("Captured GOOSE transmissions")
    axes.grid(axis="x", linestyle=":", alpha=0.5)

    return figure, axes

def plot_goose_packet_rate(
    packet_data: pd.DataFrame,
    *,
    bin_width: float = 0.1,
):
    """Plot the aggregate captured GOOSE packet rate."""
    if "RelativeTime" not in packet_data.columns:
        raise ValueError("Missing required column: RelativeTime")

    if bin_width <= 0:
        raise ValueError("bin_width must be greater than zero")

    times = (
        pd.to_numeric(packet_data["RelativeTime"], errors="coerce")
        .dropna()
        .sort_values()
    )

    if times.empty:
        raise ValueError("No GOOSE packets are available to plot")

    maximum_time = times.max()
    bins = np.arange(
        0,
        maximum_time + 2 * bin_width,
        bin_width,
    )

    packet_counts, bin_edges = np.histogram(times, bins=bins)
    packet_rate = packet_counts / bin_width
    bin_centres = bin_edges[:-1] + bin_width / 2

    figure, axes = plt.subplots(
        figsize=(9, 4),
        constrained_layout=True,
    )

    axes.plot(
        bin_centres,
        packet_rate,
        color="#0072B2",
        linewidth=1.8,
    )

    axes.fill_between(
        bin_centres,
        packet_rate,
        color="#56B4E9",
        alpha=0.18,
    )

    axes.set_xlim(left=0)
    axes.set_ylim(bottom=0)
    axes.set_xlabel("Time since first GOOSE packet (s)")
    axes.set_ylabel("Total GOOSE packet rate (pps)")
    axes.set_title("Captured GOOSE packet-rate profile")
    axes.grid(
        axis="y",
        linestyle=":",
        linewidth=0.8,
        alpha=0.45,
    )

    return figure, axes

def plot_goose_overview(
    packet_data: pd.DataFrame,
    *,
    bin_width: float = 0.1,
    stream_column: str = "goID",
):
    """Plot aggregate packet rate and per-stream transmissions together."""
    required_columns = {"RelativeTime", stream_column}
    missing_columns = required_columns.difference(packet_data.columns)

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required columns: {missing}")

    if bin_width <= 0:
        raise ValueError("bin_width must be greater than zero")

    plot_data = packet_data.copy()
    plot_data["RelativeTime"] = pd.to_numeric(
        plot_data["RelativeTime"],
        errors="coerce",
    )
    plot_data = plot_data.dropna(
        subset=["RelativeTime", stream_column]
    ).sort_values("RelativeTime")

    if plot_data.empty:
        raise ValueError("No GOOSE packets are available to plot")

    maximum_time = plot_data["RelativeTime"].max()

    # Extend the shared axis to a whole bin boundary.
    x_maximum = max(
        bin_width,
        np.ceil(maximum_time / bin_width) * bin_width,
    )

    bins = np.arange(
        0,
        x_maximum + bin_width,
        bin_width,
    )

    packet_counts, bin_edges = np.histogram(
        plot_data["RelativeTime"],
        bins=bins,
    )
    packet_rate = packet_counts / bin_width
    bin_centres = bin_edges[:-1] + bin_width / 2

    streams = list(plot_data[stream_column].drop_duplicates())
    stream_positions = {
        stream: position
        for position, stream in enumerate(streams)
    }

    y_positions = plot_data[stream_column].map(stream_positions)

    figure_height = max(6.0, 0.55 * len(streams) + 3.0)
    figure, (rate_axes, timeline_axes) = plt.subplots(
        2,
        1,
        figsize=(11, figure_height),
        sharex=True,
        gridspec_kw={
            "height_ratios": [1, 2],
            "hspace": 0.08,
        },
        constrained_layout=True,
    )

    # Upper panel: total packet rate
    rate_axes.plot(
        bin_centres,
        packet_rate,
        color="#0072B2",
        linewidth=1.8,
    )
    rate_axes.fill_between(
        bin_centres,
        packet_rate,
        color="#56B4E9",
        alpha=0.18,
    )
    rate_axes.set_ylim(bottom=0)
    rate_axes.set_ylabel("Packet rate\n(pps)")
    rate_axes.set_title("Captured GOOSE traffic")
    rate_axes.tick_params(axis="x", labelbottom=False)

    # Lower panel: individual stream transmissions
    timeline_axes.scatter(
        plot_data["RelativeTime"],
        y_positions,
        marker="|",
        s=180,
        linewidths=1.5,
        color="#0065BD",
    )
    timeline_axes.set_yticks(range(len(streams)))
    timeline_axes.set_yticklabels(streams)
    timeline_axes.set_xlabel("Time since first GOOSE packet (s)")
    timeline_axes.set_ylabel("GOOSE stream")

    # Exact shared limits and aligned gridlines
    timeline_axes.set_xlim(0, x_maximum)

    for axes in (rate_axes, timeline_axes):
        axes.grid(
            axis="x",
            linestyle=":",
            linewidth=0.8,
            alpha=0.5,
        )

    rate_axes.grid(
        axis="y",
        linestyle=":",
        linewidth=0.8,
        alpha=0.4,
    )

    return figure, (rate_axes, timeline_axes)