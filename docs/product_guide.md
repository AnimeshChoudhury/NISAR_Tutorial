# NISAR Product Guide

A factual reference for the product levels, bands, and polarimetric terms used across
this repo. For the conceptual/theory explanation of *why* these things matter, see
[Module 00](../modules/00_sar_theory_primer/notebook.ipynb); for what's actually present
in this repo's specific sample files, see [`data_inventory.md`](data_inventory.md). This
page is for looking something up, not for reading start to finish.

## Product levels

| Product | Level | Coordinates | Contents | Typical size (this repo's samples) |
|---|---|---|---|---|
| **RSLC** (Range Doppler Single Look Complex) | L1 | Radar (range/azimuth) — **not geocoded** | Complex-valued SLC image per polarization/frequency; calibration, orbit, and geolocation-grid metadata | ~14-25 GB |
| **GCOV** (Geocoded Covariance) | L2 | Geocoded (map projection, e.g. a UTM zone) | Polarimetric covariance-matrix terms (backscatter power per polarization, plus cross-terms where present) resampled onto a regular x/y grid | ~7-12 GB |
| **GUNW** (Geocoded Unwrapped interferogram) | L2 | Geocoded (map projection) | Interferometric products (wrapped/unwrapped phase, coherence, connected components, pixel offsets) derived from an RSLC *pair* | ~2 GB |

Key distinction: RSLC is **not** geocoded — a pixel's ground location has to be looked
up via the product's `geolocationGrid` metadata cube (coarse lat/lon/height/incidence-angle
grid), not read directly off an x/y axis. GCOV and GUNW *are* geocoded and carry direct
`xCoordinates`/`yCoordinates` axes plus an EPSG code (`projection` dataset).

`nisar_tools.io.open_product()` auto-detects which of these three a given file is from
its own `identification/productType` attribute, and returns the matching reader
(`RSLCProduct`, `GCOVProduct`, or `GUNWProduct`).

## HDF5 path convention

All three product types share the same top-level structure:

```
science/<LSAR|SSAR>/<PRODUCT>/...
science/<LSAR|SSAR>/identification/...
```

`LSAR` (L-band) vs `SSAR` (S-band) is the first fork in the tree — `nisar_tools.io`
detects this automatically rather than assuming one. The `identification` group (present
in every product) carries track/frame number, orbit pass direction, acquisition start/end
time, the scene's `boundingPolygon` (WGS84 lon/lat/height vertices), processing baseline
(`compositeReleaseId`), and product-specific fields (e.g. GUNW additionally records
`referenceZeroDopplerStartTime`/`secondaryZeroDopplerStartTime` for its source RSLC pair).

## L-band vs S-band

| | L-band | S-band |
|---|---|---|
| Center frequency (this repo's samples) | 1.239 GHz | 3.200 GHz |
| Wavelength (computed via `center_frequency()`, not looked up) | ~24.2 cm | ~9.4 cm |
| Typical vegetation penetration | Deeper — more sensitive to larger woody structure, or the ground under sparse canopy | Shallower — more sensitive to near-surface structure (leaves, small branches) and surface roughness/moisture |
| Instrument on NISAR | LSAR (NASA/JPL) | SSAR (ISRO) |

These are general SAR-physics tendencies (a wave interacts most strongly with objects
comparable to its own wavelength), not a scene-specific claim — see Module 05/06 for how
this repo demonstrates (without over-claiming) the practical consequence on real data.

## Polarizations and covariance terms

NISAR transmits and receives combinations of horizontal (H) and vertical (V)
polarization. This repo's sample products are all **dual-pol** (single transmit
polarization, H; both H and V received), giving up to two backscatter channels: HH and
HV.

For a dual-pol pixel, the 2x2 covariance matrix is:

```
[ HHHH   HHHV ]
[ HVHH   HVHV ]
```

- **Diagonal terms** (`HHHH`, `HVHV`): real-valued backscatter *power* in each channel.
  Always present in a GCOV product's `listOfCovarianceTerms`.
- **Off-diagonal term** (`HHHV`): a complex number — the *correlation* between the HH and
  HV channels (magnitude + relative phase). Not guaranteed to be present; this repo's
  L-band GCOV sample lacks it, its S-band GCOV sample has it (see `data_inventory.md`).
  `GCOVProduct.list_covariance_terms()` reports what's actually there per-file rather
  than assuming a fixed schema.

**What polarimetric decomposition needs:** a full decomposition (Cloude-Pottier
entropy/alpha/anisotropy, Freeman-Durden three-component, etc.) requires a **quad-pol**
covariance or coherency matrix — HH, HV, VH, and VV all present. None of this repo's
sample products are quad-pol. The most that's derivable from a dual-pol product with an
off-diagonal term is the HH-HV complex correlation coefficient
(`rho = HHHV / sqrt(HHHH * HVHV)`, used in Module 06) — a real polarimetric quantity, but
not a substitute for full decomposition.

## GUNW interferogram layers

| Layer | Meaning |
|---|---|
| `wrappedInterferogram` | Complex-valued interferogram, phase wrapped to (-pi, pi] |
| `unwrappedPhase` | Phase after 2*pi-ambiguity resolution (unwrapping); still contains flat-earth removal + topographic-phase removal (via reference DEM) but *not* atmospheric/ionospheric correction |
| `coherenceMagnitude` | Interferometric coherence, [0, 1] — how reliable the phase estimate is at each pixel |
| `connectedComponents` | Integer label per pixel identifying which contiguously-unwrapped region it belongs to; `0` conventionally marks pixels not part of any reliably-unwrapped region |
| `ionospherePhaseScreen` | Estimated ionospheric phase contribution (available as a layer for correction; not applied by default) |
| `pixelOffsets` | Offset-tracking layers (amplitude cross-correlation based displacement), independent of the phase-unwrapping products above |

See [Module 04](../modules/04_insar_deformation_basics/notebook.ipynb) for how these are
read, masked, and interpreted together — and [Module 00, Section 9](../modules/00_sar_theory_primer/notebook.ipynb)
for the phase-decomposition theory behind them.
