# Data Access

`SampleData/` is listed in `.gitignore` and is **not included in this repository**. The
five real NISAR sample products this tutorial is built on are too large to commit
(the two RSLC files alone are ~14 GB and ~25 GB), and NISAR sample/early-access data is
also subject to its own distribution terms — so this repo ships the code and the
metadata record (`docs/data_inventory.md`), not the data itself.

## What you need

Five HDF5 (`.h5`) products, matching the product types/tracks used throughout
Modules 00-06:

| # | Product | Band | Used in |
|---|---|---|---|
| 1 | RSLC (L1) | L-band | Modules 01, 02, 04 (reference acquisition) |
| 2 | RSLC (L1) | L-band | Modules 02, 04 (secondary acquisition — same track/frame as #1, later date) |
| 3 | GCOV (L2) | L-band | Modules 03, 05 |
| 4 | GUNW (L2) | L-band | Module 04 (formed from #1 + #2) |
| 5 | GCOV (L2) | S-band | Modules 05, 06 |

The exact filenames this repo's code and docs reference are recorded in
[`docs/data_inventory.md`](data_inventory.md), along with each file's full metadata
(track/frame, acquisition dates, geographic extent, polarizations, covariance terms
present, etc.) — obtained files don't need to be byte-identical to those, but should
match the same product types/bands/relationships (a repeat-pass RSLC pair from the same
track/frame, an L-band GCOV, an S-band GCOV, and a GUNW formed from the RSLC pair) for
the notebooks to run as written.

## Where to get NISAR data

- **ASF DAAC (Alaska Satellite Facility Distributed Active Archive Center)** —
  distributes NASA-side NISAR L-band products (RSLC, GCOV, GUNW, etc.):
  https://asf.alaska.edu/
- **ISRO Bhoonidhi** — distributes ISRO-side NISAR S-band products:
  https://bhoonidhi.nrsc.gov.in/

Both require free registration. Search by product type, track/frame, and date range to
find a repeat-pass pair (for Modules 02/04) and a matching S-band/L-band pair over the
same or overlapping footprint (for Module 05/06's band comparison to be meaningful the
way it is here).

## Using your own data with this repo

Once you have `.h5` files, place them in `SampleData/` at the repo root (create the
folder if needed) and update the filename constants near the top of each notebook
(e.g. `RSLC1_PATH`, `GCOV_L_PATH`) to point at your files. `nisar_tools/io.py`'s product
readers auto-detect band (`LSAR` vs `SSAR`) and product type from each file's own
metadata, so no code changes should be needed beyond the filenames — but re-run
`scripts/inspect_nisar_h5.py` on your files first and sanity-check the printed
covariance terms, polarizations, and geographic extent against what each module
assumes (documented in that module's top cell and in `docs/data_inventory.md`), since
not every real product has the same structure (e.g. Module 03 vs 06 specifically
depends on which covariance terms are present).
