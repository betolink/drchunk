"""
Integration tests that hit CMR for real.
Run with:  pytest -m integration
Skip with:  pytest -m "not integration"

Set the collection to test via DRCHUNK_TEST_CONCEPT_ID env var.
"""

import os

import pytest

import drchunk

CONCEPT_ID = os.environ.get("DRCHUNK_TEST_CONCEPT_ID", "C1996881146-POCLOUD")

pytestmark = pytest.mark.integration


class TestSampleInfoReport:
    """
    Full pipeline: sample → info → report.
    Parametrized frequency to keep granules ≤ 20.
    """

    @pytest.mark.parametrize("freq", ["2Y", "5Y", "10Y"])
    def test_full_pipeline(self, freq):
        granules = drchunk.sample(
            concept_id=CONCEPT_ID,
            freq=freq,
            seed=42,
            max_granules=20,
        )

        assert isinstance(granules, list)
        assert len(granules) > 0, f"No granules returned for freq={freq}"
        assert len(granules) <= 20, (
            f"Got {len(granules)} granules for freq={freq}, expected ≤ 20"
        )

        # Verify granule structure
        for g in granules:
            assert "meta" in g
            assert "umm" in g
            assert "concept-id" in g.get("meta", {}), "Granule missing concept-id"

        # Pipe into info
        df = drchunk.info(granules)
        assert len(df) == len(granules)
        assert "url" in df.columns
        assert "variables" in df.columns
        assert "coords" in df.columns
        assert "error" in df.columns

        # Check error rate
        errors = df[df["error"].notna() & (df["error"] != "")]
        if len(errors) > 0:
            # Warn but don't fail — some granules may be inaccessible
            print(f"\n  {len(errors)}/{len(df)} granules had errors")

        # Generate report
        report = drchunk.report(df)
        assert isinstance(report, str)
        assert "Dr. Chunk" in report
        assert "Homogeneity" in report

    def test_sample_deterministic_with_seed(self):

        g1 = drchunk.sample(concept_id=CONCEPT_ID, freq="5Y", seed=123)
        g2 = drchunk.sample(concept_id=CONCEPT_ID, freq="5Y", seed=123)

        ids1 = [g["meta"]["concept-id"] for g in g1]
        ids2 = [g["meta"]["concept-id"] for g in g2]
        assert ids1 == ids2

    def test_info_dataframe_shape(self):
        granules = drchunk.sample(concept_id=CONCEPT_ID, freq="5Y", seed=42)
        assert len(granules) <= 20

        df = drchunk.info(granules)

        # Each row should have non-empty variables or coords (or error)
        for _, row in df.iterrows():
            has_vars = isinstance(row.get("variables"), dict) and row["variables"]
            has_coords = isinstance(row.get("coords"), dict) and row["coords"]
            has_error = bool(row.get("error", ""))
            assert has_vars or has_coords or has_error, (
                f"Row has no vars, coords, or error: {row['url']}"
            )
