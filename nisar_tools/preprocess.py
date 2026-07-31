"""
Multilooking, calibration/scaling, masking, and geometric-alignment helpers shared
across the tutorial notebooks. Operates on already-windowed in-memory numpy arrays
(callers are responsible for slicing bounded windows out of the lazy h5py.Dataset
handles returned by nisar_tools.io — these functions do not touch the HDF5 files).
"""

from __future__ import annotations

import numpy as np


def amplitude(complex_arr: np.ndarray) -> np.ndarray:
    """|SLC| amplitude from a complex single-look-complex array."""
    return np.abs(complex_arr)


def power(complex_arr: np.ndarray) -> np.ndarray:
    """|SLC|^2 power (intensity) from a complex single-look-complex array."""
    return np.abs(complex_arr) ** 2


def power_db(power_arr: np.ndarray, floor_db: float = -40.0) -> np.ndarray:
    """
    Convert linear power/backscatter to dB, flooring non-positive or non-finite
    values instead of producing -inf/NaN (these arise at no-data / masked pixels).
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        db = 10.0 * np.log10(power_arr)
    db = np.where(np.isfinite(db), db, floor_db)
    return np.maximum(db, floor_db)


def multilook(arr: np.ndarray, looks_row: int, looks_col: int) -> np.ndarray:
    """
    Boxcar-average a 2D real array by (looks_row, looks_col). Trims any remainder
    rows/columns that don't evenly divide into the look window. This is the standard
    incoherent multilooking used to reduce speckle in power/intensity imagery -- it
    should be applied to power (not to the complex field, which would coherently
    average phase and is a different operation).
    """
    if arr.ndim != 2:
        raise ValueError(f"multilook expects a 2D array, got shape {arr.shape}")
    n_rows = (arr.shape[0] // looks_row) * looks_row
    n_cols = (arr.shape[1] // looks_col) * looks_col
    trimmed = arr[:n_rows, :n_cols]
    reshaped = trimmed.reshape(n_rows // looks_row, looks_row, n_cols // looks_col, looks_col)
    return np.nanmean(reshaped, axis=(1, 3))


def ratio_db(power_a: np.ndarray, power_b: np.ndarray, floor_db: float = -40.0) -> np.ndarray:
    """10*log10(power_a) - 10*log10(power_b), e.g. an HH/HV backscatter ratio in dB."""
    return power_db(power_a, floor_db) - power_db(power_b, floor_db)


def coordinate_window(
    x_coords: np.ndarray, y_coords: np.ndarray, x_min: float, x_max: float, y_min: float, y_max: float
) -> tuple[slice, slice]:
    """
    Return (row_slice, col_slice) selecting the sub-grid of a geocoded product (GCOV/
    GUNW) whose x/y axis coordinates fall within [x_min, x_max] x [y_min, y_max].
    Works regardless of whether y_coords is ascending or descending (NISAR geocoded
    grids are typically north-up, i.e. descending y).
    """
    col_idx = np.where((x_coords >= x_min) & (x_coords <= x_max))[0]
    row_idx = np.where((y_coords >= y_min) & (y_coords <= y_max))[0]
    if col_idx.size == 0 or row_idx.size == 0:
        raise ValueError("Requested x/y window does not intersect this product's coordinate grid.")
    return slice(row_idx.min(), row_idx.max() + 1), slice(col_idx.min(), col_idx.max() + 1)


def coefficient_of_variation(arr: np.ndarray) -> float:
    """std/mean over a homogeneous patch -- the standard speckle metric; a fully
    developed speckle intensity image has CV ~= 1.0, decreasing with more looks."""
    return float(np.nanstd(arr) / np.nanmean(arr))


def center_window(n_rows: int, n_cols: int, win_rows: int, win_cols: int) -> tuple[slice, slice]:
    """Return (row_slice, col_slice) for a centered win_rows x win_cols window."""
    win_rows = min(win_rows, n_rows)
    win_cols = min(win_cols, n_cols)
    row0 = (n_rows - win_rows) // 2
    col0 = (n_cols - win_cols) // 2
    return slice(row0, row0 + win_rows), slice(col0, col0 + win_cols)


def coregister_offsets(
    ref_range_start: float,
    ref_range_spacing: float,
    ref_azimuth_start: float,
    ref_azimuth_spacing: float,
    sec_range_start: float,
    sec_range_spacing: float,
    sec_azimuth_start: float,
    sec_azimuth_spacing: float,
) -> dict[str, int]:
    """
    Compute a coarse, metadata-driven geometric alignment between two RSLC
    acquisitions of the same track/frame: the integer range-multilook factor needed
    to bring the (possibly finer-sampled) secondary product's range spacing to match
    the reference's, plus the integer pixel offsets between their starting range
    samples / azimuth lines.

    This is deliberately simple -- it uses only the slantRange and zeroDopplerTime
    axes already in each product's metadata, not cross-correlation. It is adequate
    for a multilooked backscatter-differencing demo where sub-pixel accuracy isn't
    the point, but real InSAR/change-detection coregistration requires sub-pixel,
    cross-correlation-refined offsets -- see each notebook's Scope & Caveats cell.

    Returns a dict with keys: range_ml_factor, row_offset_lines, col_offset_samples.
    row/col offsets are in *reference-grid* units (i.e. after the secondary has been
    range-multilooked by range_ml_factor).
    """
    range_ml_factor = round(ref_range_spacing / sec_range_spacing)
    if range_ml_factor < 1:
        raise ValueError(
            "Reference range spacing is finer than secondary's; this helper only "
            "handles multilooking the secondary down to match a coarser reference."
        )
    col_offset_samples = round((sec_range_start - ref_range_start) / ref_range_spacing)
    row_offset_lines = round((sec_azimuth_start - ref_azimuth_start) / ref_azimuth_spacing)
    return {
        "range_ml_factor": range_ml_factor,
        "row_offset_lines": row_offset_lines,
        "col_offset_samples": col_offset_samples,
    }


def coherence_mask(coherence: np.ndarray, threshold: float = 0.3) -> np.ndarray:
    """Boolean mask of pixels considered coherent enough to trust (coherence >= threshold)."""
    return np.nan_to_num(coherence, nan=0.0) >= threshold


def apply_mask(arr: np.ndarray, valid_mask: np.ndarray) -> np.ma.MaskedArray:
    """Return a numpy masked array with invalid (valid_mask == False) pixels masked out."""
    return np.ma.masked_where(~valid_mask, arr)


def hh_hv_correlation(hhhh: np.ndarray, hvhv: np.ndarray, hhhv: np.ndarray) -> np.ndarray:
    """
    Complex correlation coefficient between the HH and HV channels:
        rho = HHHV / sqrt(HHHH * HVHV)
    This is the simplest quantity that *requires* the off-diagonal covariance term
    (HHHV) in addition to the diagonal power terms -- |rho| in [0, 1] indicates how
    correlated the co- and cross-pol returns are (low |rho| suggests more
    depolarizing/volume-like scattering; high |rho| suggests more surface-like
    scattering), and arg(rho) is their relative phase.

    Note: this is a dual-pol product, not a full quad-pol (HH/HV/VH/VV) covariance
    matrix, so it is NOT a substitute for a full polarimetric decomposition
    (e.g. Cloude-Pottier, Freeman-Durden) -- those require quad-pol data that these
    sample products don't contain. See Module 06's caveats cell.
    """
    denom = np.sqrt(hhhh.astype(np.float64) * hvhv.astype(np.float64))
    with np.errstate(divide="ignore", invalid="ignore"):
        rho = hhhv / denom
    return rho
