"""
Inspect NISAR HDF5 sample products and log their structure/metadata.

This script is read-only and metadata-focused: HDF5 group/dataset *structure*
(names, shapes, dtypes) is cheap to enumerate even on multi-GB files because
h5py does not read pixel data until a dataset is sliced. We only ever read
the *values* of small datasets (identification scalars, listOfPolarizations,
bounding polygons, etc.) - never full SAR image cubes, which is important
here since two of the sample RSLC files are 14-27 GB each.

Usage:
    python scripts/inspect_nisar_h5.py

Writes a full structural/metadata dump to stdout (redirect to a log file if
desired) and is the source data for docs/data_inventory.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATA_DIR = REPO_ROOT / "SampleData"

# Never materialize a dataset larger than this many elements.
MAX_READ_ELEMENTS = 20_000

TREE_DEPTH_LIMIT = None  # None = full tree; set an int to cap depth for display


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}PB"


def decode(value):
    """Decode bytes/np.bytes_ to str, leave everything else alone."""
    if isinstance(value, (bytes, np.bytes_)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray) and value.dtype.kind == "S":
        return np.char.decode(value, "utf-8", errors="replace").tolist()
    return value


def print_tree(h5file: h5py.File, depth_limit=None):
    print("\n--- HDF5 group/dataset tree ---")

    def visitor(name, obj):
        depth = name.count("/") + 1
        if depth_limit is not None and depth > depth_limit:
            return
        indent = "  " * depth
        if isinstance(obj, h5py.Group):
            print(f"{indent}[GROUP] {name}/")
        elif isinstance(obj, h5py.Dataset):
            print(
                f"{indent}[DSET]  {name}  shape={obj.shape} "
                f"dtype={obj.dtype} size={human_size(obj.size * obj.dtype.itemsize)}"
            )

    h5file.visititems(visitor)


def safe_read(dset: h5py.Dataset):
    """Read a dataset's value only if it's small; else return a placeholder."""
    if dset.size <= MAX_READ_ELEMENTS:
        try:
            val = dset[()]
            return decode(val)
        except Exception as exc:  # pragma: no cover - diagnostic only
            return f"<error reading: {exc}>"
    return f"<skipped: {dset.size} elements, shape={dset.shape}, too large to read>"


def find_paths(h5file: h5py.File, predicate) -> list[str]:
    matches = []

    def visitor(name, obj):
        if predicate(name, obj):
            matches.append(name)

    h5file.visititems(visitor)
    return matches


def dump_identification(h5file: h5py.File):
    print("\n--- Identification / product metadata ---")
    id_paths = find_paths(h5file, lambda n, o: n.split("/")[-1] == "identification" and isinstance(o, h5py.Group))
    if not id_paths:
        print("  No 'identification' group found.")
        return
    for path in id_paths:
        grp = h5file[path]
        print(f"  Group: {path}")
        for key in sorted(grp.keys()):
            item = grp[key]
            if isinstance(item, h5py.Dataset):
                val = safe_read(item)
                print(f"    {key}: {val}")


def dump_polarizations(h5file: h5py.File):
    print("\n--- Polarization layers (listOfPolarizations) ---")
    pol_paths = find_paths(
        h5file,
        lambda n, o: n.split("/")[-1] == "listOfPolarizations" and isinstance(o, h5py.Dataset),
    )
    if not pol_paths:
        print("  No 'listOfPolarizations' datasets found.")
    for path in pol_paths:
        val = safe_read(h5file[path])
        print(f"  {path}: {val}")


def dump_covariance_terms(h5file: h5py.File):
    print("\n--- GCOV covariance terms (listOfCovarianceTerms) ---")
    cov_paths = find_paths(
        h5file,
        lambda n, o: n.split("/")[-1] == "listOfCovarianceTerms" and isinstance(o, h5py.Dataset),
    )
    if not cov_paths:
        print("  No 'listOfCovarianceTerms' datasets found (not a GCOV product, or different layout).")
    for path in cov_paths:
        val = safe_read(h5file[path])
        print(f"  {path}: {val}")
    # Also directly list dataset names under frequency groups that look like
    # polarimetric covariance terms (e.g. HHHH, HVHV, HHHV) in case the
    # listOfCovarianceTerms dataset is absent or the layout differs.
    cov_term_names = {"HHHH", "HVHV", "VVVV", "VHVH", "HHHV", "HHVV", "HVVV", "HHVH", "VVVH", "HVVH"}
    grid_paths = find_paths(
        h5file,
        lambda n, o: isinstance(o, h5py.Dataset) and n.split("/")[-1] in cov_term_names,
    )
    if grid_paths:
        print("  Covariance-term datasets found directly in tree:")
        for path in grid_paths:
            dset = h5file[path]
            print(f"    {path}  shape={dset.shape} dtype={dset.dtype}")


def dump_gunw_layers(h5file: h5py.File):
    print("\n--- GUNW interferogram layers ---")
    keywords = (
        "unwrappedPhase",
        "wrappedInterferogram",
        "coherenceMagnitude",
        "connectedComponents",
        "ionospherePhaseScreen",
        "unwrappedInterferogram",
    )
    layer_paths = find_paths(
        h5file,
        lambda n, o: isinstance(o, h5py.Dataset) and n.split("/")[-1] in keywords,
    )
    if not layer_paths:
        print("  No recognized GUNW layer datasets found (not a GUNW product, or different layout).")
    for path in layer_paths:
        dset = h5file[path]
        print(f"  {path}  shape={dset.shape} dtype={dset.dtype}")


def dump_geolocation(h5file: h5py.File):
    print("\n--- Geolocation metadata ---")
    # boundingPolygon is the standard NISAR way to express the scene footprint (WKT string).
    poly_paths = find_paths(
        h5file,
        lambda n, o: n.split("/")[-1] == "boundingPolygon" and isinstance(o, h5py.Dataset),
    )
    if poly_paths:
        for path in poly_paths:
            val = safe_read(h5file[path])
            print(f"  {path}:\n    {val}")
    else:
        print("  No 'boundingPolygon' dataset found.")

    # Corner/extent-like scalar datasets sometimes present too.
    extent_keywords = {
        "zeroDopplerStartTime",
        "zeroDopplerEndTime",
        "sceneCenterAlongTrackSpacing",
        "sceneCenterGroundRangeSpacing",
    }
    extent_paths = find_paths(
        h5file,
        lambda n, o: isinstance(o, h5py.Dataset) and n.split("/")[-1] in extent_keywords,
    )
    for path in extent_paths:
        val = safe_read(h5file[path])
        print(f"  {path}: {val}")

    # Radar/geolocation grid lat/lon cubes (small - coarse cubes, safe to read fully if small).
    latlon_paths = find_paths(
        h5file,
        lambda n, o: isinstance(o, h5py.Dataset) and n.split("/")[-1] in ("latitude", "longitude", "height"),
    )
    for path in latlon_paths:
        dset = h5file[path]
        if dset.size <= MAX_READ_ELEMENTS:
            val = dset[()]
            arr = np.asarray(val)
            print(
                f"  {path}  shape={dset.shape} "
                f"min={np.nanmin(arr):.6f} max={np.nanmax(arr):.6f}"
            )
        else:
            print(f"  {path}  shape={dset.shape} (too large to read fully; skipped)")


def inspect_file(filepath: Path):
    print("=" * 100)
    print(f"FILE: {filepath.name}")
    print(f"  Full path: {filepath}")
    print(f"  Size on disk: {human_size(filepath.stat().st_size)}")
    print("=" * 100)

    with h5py.File(filepath, "r") as f:
        print_tree(f, depth_limit=TREE_DEPTH_LIMIT)
        dump_identification(f)
        dump_geolocation(f)
        dump_polarizations(f)
        dump_covariance_terms(f)
        dump_gunw_layers(f)

    print()


def main():
    if not SAMPLE_DATA_DIR.is_dir():
        print(f"SampleData directory not found at {SAMPLE_DATA_DIR}", file=sys.stderr)
        sys.exit(1)

    h5_files = sorted(SAMPLE_DATA_DIR.glob("*.h5"))
    if not h5_files:
        print(f"No .h5 files found in {SAMPLE_DATA_DIR}", file=sys.stderr)
        sys.exit(1)

    for filepath in h5_files:
        inspect_file(filepath)


if __name__ == "__main__":
    main()
