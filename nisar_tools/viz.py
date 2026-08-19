"""
Quicklook plotting helpers shared across the tutorial notebooks. Each function plots
into a caller-supplied Axes (so notebooks control figure layout/side-by-side panels)
and returns the AxesImage, so callers can add a shared colorbar if desired.

All functions accept an optional `valid_mask` (True = keep). Masked-out pixels are
rendered in `bad_color` rather than being colored as if they were valid data -- this
matters most for GUNW unwrapped phase, where plotting incoherent pixels with the same
colormap as coherent ones can visually imply displacement structure that isn't real.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np


def _as_masked(arr: np.ndarray, valid_mask: np.ndarray | None) -> np.ndarray:
    if valid_mask is None:
        return arr
    return np.ma.masked_where(~valid_mask, arr)


def _percentile_clip(arr, low: float, high: float) -> tuple[float, float]:
    """
    Percentile bounds over the finite, unmasked values only. `.compressed()` alone is
    not enough: a masked array's unmasked region can still contain its own NaNs (e.g.
    a layer whose own no-data footprint doesn't exactly match the valid_mask it was
    plotted with -- ionospherePhaseScreen vs. unwrappedPhase in Module 04 is a real
    example) and np.percentile silently propagates those to NaN, which would otherwise
    collapse vmin/vmax to a degenerate (or NaN) range without any visible error.
    """
    values = arr.compressed() if np.ma.isMaskedArray(arr) else arr
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0, 1.0
    return float(np.percentile(finite, low)), float(np.percentile(finite, high))


def _imshow_core(ax, arr, cmap, vmin, vmax, extent, bad_color):
    cmap_obj = plt.get_cmap(cmap).copy()
    cmap_obj.set_bad(bad_color)
    return ax.imshow(arr, cmap=cmap_obj, vmin=vmin, vmax=vmax, extent=extent, aspect="auto")


def add_colorbar(im, ax, label: str | None = None):
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    if label:
        cbar.set_label(label)
    return cbar


def _finish(ax, im, title, xlabel, ylabel, colorbar_label):
    if title:
        ax.set_title(title)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    add_colorbar(im, ax, colorbar_label)


def imshow_amplitude(
    ax,
    amp: np.ndarray,
    title: str | None = None,
    cmap: str = "gray",
    clip_percentile: tuple[float, float] = (2, 98),
    vmin: float | None = None,
    vmax: float | None = None,
    valid_mask: np.ndarray | None = None,
    extent=None,
    xlabel: str | None = "Range sample",
    ylabel: str | None = "Azimuth line",
    colorbar_label: str = "Amplitude",
    bad_color: str = "black",
):
    """Generic percentile-clipped grayscale (or any sequential cmap) image -- used for
    SLC amplitude, but equally for any single sequential quantity (e.g. dB backscatter)
    by overriding cmap/colorbar_label."""
    masked = _as_masked(amp, valid_mask)
    auto_vmin, auto_vmax = _percentile_clip(masked, *clip_percentile)
    vmin = auto_vmin if vmin is None else vmin
    vmax = auto_vmax if vmax is None else vmax
    im = _imshow_core(ax, masked, cmap, vmin, vmax, extent, bad_color)
    _finish(ax, im, title, xlabel, ylabel, colorbar_label)
    return im


def imshow_phase(
    ax,
    phase: np.ndarray,
    title: str | None = None,
    cmap: str = "twilight",
    vmin: float = -np.pi,
    vmax: float = np.pi,
    valid_mask: np.ndarray | None = None,
    extent=None,
    xlabel: str | None = "Range sample",
    ylabel: str | None = "Azimuth line",
    colorbar_label: str = "Phase (rad)",
    bad_color: str = "black",
):
    """Wrapped phase in [-pi, pi] with a cyclic colormap by default."""
    masked = _as_masked(phase, valid_mask)
    im = _imshow_core(ax, masked, cmap, vmin, vmax, extent, bad_color)
    _finish(ax, im, title, xlabel, ylabel, colorbar_label)
    return im


def imshow_diverging(
    ax,
    arr: np.ndarray,
    title: str | None = None,
    cmap: str = "RdBu_r",
    clip_percentile: tuple[float, float] = (2, 98),
    center: float = 0.0,
    vmin: float | None = None,
    vmax: float | None = None,
    valid_mask: np.ndarray | None = None,
    extent=None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    colorbar_label: str | None = None,
    bad_color: str = "black",
):
    """Symmetric diverging colormap about `center` (span from percentile-clipped max
    absolute deviation unless vmin/vmax given explicitly) -- for difference maps, dB
    ratio maps, or side-by-side comparisons needing a shared, explicit scale."""
    masked = _as_masked(arr, valid_mask)
    if vmin is None or vmax is None:
        lo, hi = _percentile_clip(masked, *clip_percentile)
        half_range = max(abs(lo - center), abs(hi - center))
        vmin = center - half_range if vmin is None else vmin
        vmax = center + half_range if vmax is None else vmax
    im = _imshow_core(ax, masked, cmap, vmin, vmax, extent, bad_color)
    _finish(ax, im, title, xlabel, ylabel, colorbar_label)
    return im


def imshow_masked(
    ax,
    arr: np.ndarray,
    valid_mask: np.ndarray | None = None,
    title: str | None = None,
    cmap: str = "viridis",
    vmin: float | None = None,
    vmax: float | None = None,
    clip_percentile: tuple[float, float] = (2, 98),
    extent=None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    colorbar_label: str | None = None,
    bad_color: str = "black",
):
    """Sequential-colormap plot with explicit/auto vmin-vmax, for quantities with a
    natural fixed range (e.g. coherence in [0, 1]) rather than a diverging one."""
    masked = _as_masked(arr, valid_mask)
    auto_vmin, auto_vmax = _percentile_clip(masked, *clip_percentile)
    vmin = auto_vmin if vmin is None else vmin
    vmax = auto_vmax if vmax is None else vmax
    im = _imshow_core(ax, masked, cmap, vmin, vmax, extent, bad_color)
    _finish(ax, im, title, xlabel, ylabel, colorbar_label)
    return im


def new_figure(ncols: int = 1, nrows: int = 1, figsize=None, **kwargs):
    if figsize is None:
        figsize = (6.5 * ncols, 5.5 * nrows)
    return plt.subplots(nrows=nrows, ncols=ncols, figsize=figsize, **kwargs)
