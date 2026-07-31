"""
Smoke tests for nisar_tools.io against the real NISAR sample products.

These tests read only small metadata (identification, listOfPolarizations,
listOfCovarianceTerms) - never full image cubes - so they run quickly even though
two of the sample files are 14-26 GB.

If SampleData/ is not present (e.g. a fresh clone without the gitignored sample
files), these tests are skipped rather than failed, since SampleData/ is
intentionally excluded from version control (see docs/data_access.md).
"""

from pathlib import Path

import pytest

from nisar_tools.io import GCOVProduct, GUNWProduct, RSLCProduct, open_product

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATA_DIR = REPO_ROOT / "SampleData"

RSLC1 = SAMPLE_DATA_DIR / "NISAR_L1_PR_RSLC_025_034_D_073_2005_DHDH_M_20260710T133917_20260710T133952_P05023_N_F_J_001.h5"
RSLC2 = SAMPLE_DATA_DIR / "NISAR_L1_PR_RSLC_026_034_D_073_4005_DHDH_A_20260722T133916_20260722T133951_P05023_N_F_J_001.h5"
GCOV_L = SAMPLE_DATA_DIR / "NISAR_L2_PR_GCOV_026_091_D_075_4005_DHDH_A_20260726T123348_20260726T123423_P05023_N_F_J_001.h5"
GUNW = SAMPLE_DATA_DIR / "NISAR_L2_PR_GUNW_025_034_D_073_026_2000_SH_20260710T133917_20260710T133952_20260722T133916_20260722T133951_P05023_N_F_J_001.h5"
GCOV_S = SAMPLE_DATA_DIR / "NISAR_S2_PR_GCOV_025_141_A_015_3700_DHNA_A_20260717T231346_20260717T231423_P00500_M_F_I_001.h5"

ALL_FILES = [RSLC1, RSLC2, GCOV_L, GUNW, GCOV_S]

requires_sample_data = pytest.mark.skipif(
    not all(f.exists() for f in ALL_FILES),
    reason="SampleData/ is gitignored and not present; obtain sample files per docs/data_access.md",
)


@requires_sample_data
class TestProductTypeAndBandDetection:
    def test_rslc1_is_rslc_lsar(self):
        with open_product(RSLC1) as prod:
            assert isinstance(prod, RSLCProduct)
            assert prod.product_type == "RSLC"
            assert prod.band_group == "LSAR"
            assert prod.radar_band == "L"

    def test_rslc2_is_rslc_lsar(self):
        with open_product(RSLC2) as prod:
            assert isinstance(prod, RSLCProduct)
            assert prod.product_type == "RSLC"
            assert prod.band_group == "LSAR"

    def test_gcov_l_is_gcov_lsar(self):
        with open_product(GCOV_L) as prod:
            assert isinstance(prod, GCOVProduct)
            assert prod.product_type == "GCOV"
            assert prod.band_group == "LSAR"
            assert prod.radar_band == "L"

    def test_gunw_is_gunw_lsar(self):
        with open_product(GUNW) as prod:
            assert isinstance(prod, GUNWProduct)
            assert prod.product_type == "GUNW"
            assert prod.band_group == "LSAR"

    def test_gcov_s_is_gcov_ssar(self):
        with open_product(GCOV_S) as prod:
            assert isinstance(prod, GCOVProduct)
            assert prod.product_type == "GCOV"
            assert prod.band_group == "SSAR"
            assert prod.radar_band == "S"


@requires_sample_data
class TestTrackFrameIdentity:
    def test_rslc1_rslc2_share_track_frame(self):
        with open_product(RSLC1) as p1, open_product(RSLC2) as p2:
            assert p1.track_number == p2.track_number == 34
            assert p1.frame_number == p2.frame_number == 73

    def test_gcov_l_and_gcov_s_have_distinct_tracks(self):
        with open_product(GCOV_L) as pl, open_product(GCOV_S) as ps:
            assert pl.track_number == 91
            assert ps.track_number == 141
            assert pl.track_number != ps.track_number


@requires_sample_data
class TestPolarizationAndCovarianceTerms:
    def test_rslc1_polarizations(self):
        with open_product(RSLC1) as prod:
            assert set(prod.list_polarizations("A")) == {"HH", "HV"}
            assert set(prod.list_polarizations("B")) == {"HH", "HV"}

    def test_rslc2_polarizations(self):
        with open_product(RSLC2) as prod:
            assert set(prod.list_polarizations("A")) == {"HH", "HV"}
            assert set(prod.list_polarizations("B")) == {"HH", "HV"}

    def test_gcov_l_covariance_terms_are_diagonal_only(self):
        with open_product(GCOV_L) as prod:
            terms = set(prod.list_covariance_terms("A"))
            assert terms == {"HHHH", "HVHV"}
            assert "HHHV" not in terms

    def test_gcov_s_covariance_terms_include_off_diagonal(self):
        with open_product(GCOV_S) as prod:
            terms = set(prod.list_covariance_terms("A"))
            assert {"HHHH", "HVHV", "HHHV"}.issubset(terms)

    def test_gunw_polarization_is_hh_only(self):
        with open_product(GUNW) as prod:
            assert prod.list_polarizations("A") == ["HH"]


@requires_sample_data
class TestGUNWReferenceSecondaryPairing:
    def test_reference_matches_rslc1_actual_acquisition(self):
        with open_product(GUNW) as gunw, open_product(RSLC1) as rslc1:
            assert gunw.reference_zero_doppler_start_time == rslc1.zero_doppler_start_time
            assert gunw.reference_zero_doppler_end_time == rslc1.zero_doppler_end_time

    def test_secondary_matches_rslc2_actual_acquisition(self):
        with open_product(GUNW) as gunw, open_product(RSLC2) as rslc2:
            assert gunw.secondary_zero_doppler_start_time == rslc2.zero_doppler_start_time
            assert gunw.secondary_zero_doppler_end_time == rslc2.zero_doppler_end_time

    def test_gunw_unwrapped_layers_present(self):
        with open_product(GUNW) as prod:
            layers = set(prod.list_unwrapped_layers("A", "HH"))
            assert {"unwrappedPhase", "coherenceMagnitude", "connectedComponents"}.issubset(layers)


@requires_sample_data
class TestGeocodedCoordinates:
    def test_gcov_l_and_gcov_s_share_similar_footprint(self):
        """Files 3 and 5 were confirmed (docs/data_inventory.md) to cover overlapping
        ground footprints despite different track/frame numbers - both geocoded to
        UTM zone 46N (EPSG:32646)."""
        with open_product(GCOV_L) as pl, open_product(GCOV_S) as ps:
            coords_l = pl.coordinates("A")
            coords_s = ps.coordinates("A")
            assert coords_l["epsg"] == coords_s["epsg"] == 32646
            # bounding boxes should overlap substantially, not be disjoint
            assert coords_l["x"].min() < coords_s["x"].max()
            assert coords_s["x"].min() < coords_l["x"].max()
