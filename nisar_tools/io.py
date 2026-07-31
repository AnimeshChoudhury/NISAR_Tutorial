"""
Generic HDF5 readers for NISAR RSLC / GCOV / GUNW products.

Design constraints, driven by inspecting the real sample products
(see docs/data_inventory.md):

- The top-level science group is either 'science/LSAR' (L-band) or 'science/SSAR'
  (S-band) — never hardcode one; detect_band_group() inspects the file.
- RSLC image cubes can be tens of GB. Every reader here returns lazy h5py.Dataset
  handles for large arrays (swaths, covariance grids, interferogram layers) — callers
  slice what they need. Only small metadata (identification scalars, coordinate axes,
  geolocation cubes) is read eagerly into numpy arrays.
- GCOV covariance-term sets vary by product (diagonal-only vs. diagonal+off-diagonal);
  readers introspect what's actually present rather than assuming a fixed schema.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import h5py
import numpy as np

_BAND_GROUPS = ("LSAR", "SSAR")
# Matches a polarimetric covariance/coherency term name, e.g. HHHH, HVHV, HHHV, VVVV.
_COVARIANCE_TERM_RE = re.compile(r"^[HV]{2}[HV]{2}$")


def _decode(value):
    """Decode HDF5 fixed-length byte strings (scalar or array) to native Python/str."""
    if isinstance(value, (bytes, np.bytes_)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray) and value.dtype.kind == "S":
        return np.char.decode(value, "utf-8", errors="replace").tolist()
    return value


def detect_band_group(h5file: h5py.File) -> str:
    """Return 'LSAR' or 'SSAR', whichever top-level science group the file actually has."""
    science = h5file.get("science")
    if science is None:
        raise ValueError("Not a NISAR product: no top-level 'science' group.")
    for band in _BAND_GROUPS:
        if band in science:
            return band
    raise ValueError(f"Unrecognized NISAR band group under 'science/': {list(science.keys())}")


def parse_bounding_polygon(wkt: str) -> dict[str, float]:
    """
    Parse a NISAR identification/boundingPolygon WKT POLYGON string (vertices are
    'lon lat height' triplets, WGS84) into a lon/lat/height bounding box. This is how
    each notebook confirms its geographic region from metadata rather than assuming it.
    """
    coords_str = wkt.split("((", 1)[1].rsplit("))", 1)[0]
    lons, lats, heights = [], [], []
    for triplet in coords_str.split(","):
        lon_str, lat_str, height_str = triplet.strip().split()
        lons.append(float(lon_str))
        lats.append(float(lat_str))
        heights.append(float(height_str))
    return {
        "lon_min": min(lons),
        "lon_max": max(lons),
        "lat_min": min(lats),
        "lat_max": max(lats),
        "height_min": min(heights),
        "height_max": max(heights),
    }


def read_identification(h5file: h5py.File, band_group: str | None = None) -> dict[str, Any]:
    """Read the full identification group (all scalar/small metadata) into a plain dict."""
    band_group = band_group or detect_band_group(h5file)
    grp = h5file[f"science/{band_group}/identification"]
    out: dict[str, Any] = {}
    for key in grp.keys():
        item = grp[key]
        if isinstance(item, h5py.Dataset):
            out[key] = _decode(item[()])
    return out


class _BaseProduct:
    """Common metadata surface shared by RSLC/GCOV/GUNW readers."""

    def __init__(self, filepath: Path, h5file: h5py.File, band_group: str, identification: dict[str, Any]):
        self.filepath = Path(filepath)
        self._h5 = h5file
        self.band_group = band_group
        self.identification = identification

    def close(self):
        self._h5.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self):
        return (
            f"{type(self).__name__}(file={self.filepath.name!r}, band_group={self.band_group!r}, "
            f"track={self.track_number}, frame={self.frame_number})"
        )

    @property
    def product_type(self) -> str | None:
        return self.identification.get("productType")

    @property
    def track_number(self):
        return self.identification.get("trackNumber")

    @property
    def frame_number(self):
        return self.identification.get("frameNumber")

    @property
    def radar_band(self):
        return self.identification.get("radarBand")

    @property
    def orbit_pass_direction(self):
        return self.identification.get("orbitPassDirection")

    @property
    def bounding_polygon(self):
        return self.identification.get("boundingPolygon")

    @property
    def bbox(self) -> dict[str, float] | None:
        """Lon/lat/height bounding box parsed from boundingPolygon, or None if absent."""
        wkt = self.bounding_polygon
        return parse_bounding_polygon(wkt) if wkt else None

    @property
    def zero_doppler_start_time(self):
        return self.identification.get("zeroDopplerStartTime")

    @property
    def zero_doppler_end_time(self):
        return self.identification.get("zeroDopplerEndTime")

    @property
    def list_of_frequencies(self):
        return self.identification.get("listOfFrequencies")


class RSLCProduct(_BaseProduct):
    """Reader for RSLC (L1, radar-coordinate complex SLC) products."""

    def _swaths_group(self) -> h5py.Group:
        return self._h5[f"science/{self.band_group}/RSLC/swaths"]

    def list_polarizations(self, frequency: str = "A") -> list[str]:
        dset = self._swaths_group()[f"frequency{frequency}/listOfPolarizations"]
        return list(_decode(dset[()]))

    def get_slc_dataset(self, frequency: str = "A", polarization: str = "HH") -> h5py.Dataset:
        """Lazy handle to the complex SLC image cube — slice this, do not load it whole."""
        return self._swaths_group()[f"frequency{frequency}/{polarization}"]

    def read_slc_block(
        self,
        frequency: str = "A",
        polarization: str = "HH",
        row_slice: slice = slice(None),
        col_slice: slice = slice(None),
    ) -> np.ndarray:
        """Read a bounded window of the SLC cube into memory."""
        return self.get_slc_dataset(frequency, polarization)[row_slice, col_slice]

    def slant_range(self, frequency: str = "A") -> np.ndarray:
        return self._swaths_group()[f"frequency{frequency}/slantRange"][()]

    def range_spacing(self, frequency: str = "A") -> float:
        return float(self._swaths_group()[f"frequency{frequency}/slantRangeSpacing"][()])

    def center_frequency(self, frequency: str = "A") -> float:
        """Acquired center frequency in Hz -- use with the speed of light to get wavelength."""
        return float(self._swaths_group()[f"frequency{frequency}/acquiredCenterFrequency"][()])

    def zero_doppler_time(self) -> np.ndarray:
        return self._swaths_group()["zeroDopplerTime"][()]

    def azimuth_spacing(self) -> float:
        return float(self._swaths_group()["zeroDopplerTimeSpacing"][()])

    def geolocation_grid(self) -> dict[str, np.ndarray | int]:
        """
        RSLC products are not geocoded, so there is no direct x/y axis. Instead NISAR
        provides a coarse geolocationGrid cube (coordinateX/Y in the CRS given by 'epsg',
        plus incidence angle, height, etc.) used to locate radar-coordinate pixels on the
        ground. These cubes are small (tens of MB) so we read them fully.
        """
        grp = self._h5[f"science/{self.band_group}/RSLC/metadata/geolocationGrid"]
        out: dict[str, np.ndarray | int] = {}
        for key in grp.keys():
            item = grp[key]
            if isinstance(item, h5py.Dataset):
                out[key] = item[()]
        return out


class GCOVProduct(_BaseProduct):
    """Reader for GCOV (L2, geocoded polarimetric covariance) products."""

    def _grids_group(self) -> h5py.Group:
        return self._h5[f"science/{self.band_group}/GCOV/grids"]

    def list_covariance_terms(self, frequency: str = "A") -> list[str]:
        """
        Return the covariance terms actually present for this frequency. Prefers the
        product's own listOfCovarianceTerms dataset; falls back to introspecting dataset
        names in the frequency group in case that dataset is absent. Term sets vary by
        product — e.g. the L-band sample here has only diagonal terms (HHHH, HVHV) while
        the S-band sample also has the off-diagonal HHHV term.
        """
        freq_grp = self._grids_group()[f"frequency{frequency}"]
        if "listOfCovarianceTerms" in freq_grp:
            return list(_decode(freq_grp["listOfCovarianceTerms"][()]))
        return sorted(k for k in freq_grp.keys() if _COVARIANCE_TERM_RE.match(k))

    def get_covariance_dataset(self, term: str, frequency: str = "A") -> h5py.Dataset:
        """Lazy handle to a covariance-term grid — slice this, do not load it whole."""
        return self._grids_group()[f"frequency{frequency}/{term}"]

    def list_polarizations(self, frequency: str = "A") -> list[str]:
        dset = self._grids_group()[f"frequency{frequency}/listOfPolarizations"]
        return list(_decode(dset[()]))

    def coordinates(self, frequency: str = "A") -> dict[str, Any]:
        """Geocoded x/y axes (meters, in the CRS given by 'epsg') and grid spacing."""
        freq_grp = self._grids_group()[f"frequency{frequency}"]
        return {
            "x": freq_grp["xCoordinates"][()],
            "y": freq_grp["yCoordinates"][()],
            "x_spacing": freq_grp["xCoordinateSpacing"][()],
            "y_spacing": freq_grp["yCoordinateSpacing"][()],
            "epsg": int(freq_grp["projection"][()]),
        }

    def center_frequency(self, frequency: str = "A") -> float:
        """Center frequency in Hz (from metadata/sourceData) -- use with the speed of light to get wavelength."""
        path = f"science/{self.band_group}/GCOV/metadata/sourceData/swaths/frequency{frequency}/centerFrequency"
        return float(self._h5[path][()])


_GUNW_LAYER_NAMES = (
    "unwrappedPhase",
    "coherenceMagnitude",
    "connectedComponents",
    "ionospherePhaseScreen",
)


class GUNWProduct(_BaseProduct):
    """Reader for GUNW (L2, geocoded unwrapped interferogram) products."""

    def _grids_group(self) -> h5py.Group:
        return self._h5[f"science/{self.band_group}/GUNW/grids"]

    # --- Reference/secondary pairing, read from metadata (not filename parsing) ---

    @property
    def reference_zero_doppler_start_time(self):
        return self.identification.get("referenceZeroDopplerStartTime")

    @property
    def reference_zero_doppler_end_time(self):
        return self.identification.get("referenceZeroDopplerEndTime")

    @property
    def secondary_zero_doppler_start_time(self):
        return self.identification.get("secondaryZeroDopplerStartTime")

    @property
    def secondary_zero_doppler_end_time(self):
        return self.identification.get("secondaryZeroDopplerEndTime")

    # --- Layers ---

    def list_unwrapped_layers(self, frequency: str = "A", polarization: str = "HH") -> list[str]:
        grp = self._grids_group()[f"frequency{frequency}/unwrappedInterferogram/{polarization}"]
        return sorted(k for k in grp.keys() if k in _GUNW_LAYER_NAMES and isinstance(grp[k], h5py.Dataset))

    def get_unwrapped_layer(self, layer: str, frequency: str = "A", polarization: str = "HH") -> h5py.Dataset:
        return self._grids_group()[f"frequency{frequency}/unwrappedInterferogram/{polarization}/{layer}"]

    def get_wrapped_interferogram(self, frequency: str = "A", polarization: str = "HH") -> h5py.Dataset:
        return self._grids_group()[f"frequency{frequency}/wrappedInterferogram/{polarization}/wrappedInterferogram"]

    def list_polarizations(self, frequency: str = "A") -> list[str]:
        dset = self._grids_group()[f"frequency{frequency}/listOfPolarizations"]
        return list(_decode(dset[()]))

    def coordinates(self, frequency: str = "A", polarization: str = "HH") -> dict[str, Any]:
        grp = self._grids_group()[f"frequency{frequency}/unwrappedInterferogram/{polarization}"]
        return {
            "x": grp["xCoordinates"][()],
            "y": grp["yCoordinates"][()],
            "epsg": int(grp["projection"][()]),
        }


_PRODUCT_CLASSES: dict[str, type[_BaseProduct]] = {
    "RSLC": RSLCProduct,
    "GCOV": GCOVProduct,
    "GUNW": GUNWProduct,
}


def open_product(filepath: str | Path) -> _BaseProduct:
    """
    Open a NISAR HDF5 product and return the appropriate reader (RSLCProduct /
    GCOVProduct / GUNWProduct), auto-detected from the file's own identification/
    productType attribute and LSAR-vs-SSAR band group. Use as a context manager:

        with open_product(path) as prod:
            ...
    """
    filepath = Path(filepath)
    h5file = h5py.File(filepath, "r")
    try:
        band_group = detect_band_group(h5file)
        identification = read_identification(h5file, band_group)
        product_type = identification.get("productType")
        cls = _PRODUCT_CLASSES.get(product_type)
        if cls is None:
            raise ValueError(
                f"Unsupported or unrecognized productType {product_type!r} in {filepath.name}"
            )
        return cls(filepath, h5file, band_group, identification)
    except Exception:
        h5file.close()
        raise
