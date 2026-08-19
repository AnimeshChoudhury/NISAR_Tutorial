# Changelog

Corrections to this repo's content, logged here so anyone working through the modules
can see where an interpretation was revised after first being written. This is a
corrections record, not a release/feature log.

## 2026-08-18

**Changed:** Module 04's interpretation of the large-scale phase gradient in the GUNW
interferogram. It was originally described as a generic "atmospheric/orbital ramp."
Quantitative comparison against the product's own `ionospherePhaseScreen` layer (row-mean
correlation r≈0.93 between the gradient and the ionosphere screen, gradient magnitude
matching to within ~2%) showed the gradient is better described as consistent with
ionospheric phase contribution specifically, not a generic atmospheric/orbital effect.

**Added:**
- `GUNWProduct.get_ionospheric_phase_screen()` in `nisar_tools/io.py` — a lazy accessor
  for the GUNW product's `ionospherePhaseScreen` layer, used to run the comparison above.
- A plot panel in Module 04 showing `ionospherePhaseScreen` alongside coherence and
  unwrapped phase, on the same mask and diverging-scale convention as the other panels.
- A paragraph in Module 00's phase-contribution explanation covering why L-band is
  particularly sensitive to ionospheric delay (wavelength-squared scaling), with a
  pointer to where Module 04 checks this on real data.

**Fixed:** A NaN-handling bug in `viz._percentile_clip()`. It computed percentile bounds
from a masked array's unmasked values without also filtering those values for NaNs. A
layer whose own no-data footprint doesn't exactly match the `valid_mask` it's plotted
with (e.g. `ionospherePhaseScreen` vs. `unwrappedPhase` in Module 04) could therefore
produce a colorbar silently collapsed to a degenerate or NaN range, with no visible
error. This is a general defect in the visualization utility, not specific to this one
layer — it could resurface for any future layer plotted against a mask that doesn't
match its own valid-pixel footprint.
