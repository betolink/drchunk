import drchunk


class TestReport:
    def test_includes_granule_count(self, sample_df):
        r = drchunk.report(sample_df)
        assert "Granules inspected : 2" in r

    def test_includes_date_range(self, sample_df):
        r = drchunk.report(sample_df)
        assert "2020-01-15" in r
        assert "2020-02-15" in r

    def test_lists_variables(self, sample_df):
        r = drchunk.report(sample_df)
        assert "temperature" in r
        assert "precip" in r
        assert "lat" in r

    def test_fully_homogeneous_variable(self, sample_df):
        r = drchunk.report(sample_df)
        assert "lat" in r
        # lat appears in both files with same chunks → should be in homogeneous
        assert "Fully homogeneous" in r

    def test_heterogeneous_variable(self, sample_df):
        r = drchunk.report(sample_df)
        # precip differs between files
        assert "Heterogeneous" in r or "heterogeneous" in r

    def test_single_variable(self, single_var_df):
        r = drchunk.report(single_var_df)
        assert "sst" in r
        assert "Granules inspected : 1" in r
        assert "100.0%" in r

    def test_errors_are_reported(self, error_df):
        r = drchunk.report(error_df)
        assert "Errors" in r
        assert "1" in r

    def test_empty_df_no_crash(self):
        import pandas as pd
        df = pd.DataFrame({"url": [], "date": [], "variables": [], "coords": [], "error": []})
        r = drchunk.report(df)
        assert "No variables" in r or "No data" in r

    def test_spark_bar_format(self, sample_df):
        r = drchunk.report(sample_df)
        assert "█" in r  # spark bars present


class TestReportAPI:
    def test_returns_string(self, sample_df):
        r = drchunk.report(sample_df)
        assert isinstance(r, str)
        assert len(r) > 0

    def test_report_from_empty_error_filtered(self, error_df):
        r = drchunk.report(error_df)
        assert "var" in r
        assert "ok.nc" not in r  # urls not shown in report
