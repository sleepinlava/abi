"""Tests for abi.doctor — health check and diagnostic reporting."""

from __future__ import annotations

from abi.doctor import Doctor, HealthCheck, HealthReport

# ── HealthCheck ──────────────────────────────────────────────────────────────


class TestHealthCheck:
    """Construction and field access for the HealthCheck dataclass."""

    def test_construction_all_fields(self) -> None:
        c = HealthCheck(
            name="test",
            status="passed",
            message="all good",
            details={"extra": 42},
        )
        assert c.name == "test"
        assert c.status == "passed"
        assert c.message == "all good"
        assert c.details == {"extra": 42}

    def test_default_details_is_empty_dict(self) -> None:
        c = HealthCheck(name="test", status="ok", message="msg")
        assert c.details == {}
        assert isinstance(c.details, dict)

    def test_default_details_factory_is_independent_per_instance(self) -> None:
        """Each HealthCheck gets its own empty dict, not a shared mutable default."""
        a = HealthCheck(name="a", status="ok", message="msg")
        b = HealthCheck(name="b", status="ok", message="msg")
        a.details["key"] = "value"
        assert "key" not in b.details

    def test_field_assignment(self) -> None:
        c = HealthCheck(name="x", status="warning", message="uh oh")
        c.status = "passed"
        assert c.status == "passed"


# ── HealthReport ─────────────────────────────────────────────────────────────


class TestHealthReportPassed:
    """The ``passed`` property."""

    def test_all_passed_returns_true(self) -> None:
        r = HealthReport(
            checks=[
                HealthCheck(name="a", status="passed", message="ok"),
                HealthCheck(name="b", status="passed", message="ok"),
            ]
        )
        assert r.passed is True

    def test_warning_does_not_cause_failure(self) -> None:
        r = HealthReport(
            checks=[
                HealthCheck(name="a", status="passed", message="ok"),
                HealthCheck(name="b", status="warning", message="watch out"),
            ]
        )
        assert r.passed is True

    def test_single_failed_returns_false(self) -> None:
        r = HealthReport(
            checks=[
                HealthCheck(name="a", status="passed", message="ok"),
                HealthCheck(name="b", status="failed", message="boom"),
            ]
        )
        assert r.passed is False

    def test_all_failed_returns_false(self) -> None:
        r = HealthReport(
            checks=[
                HealthCheck(name="a", status="failed", message="boom 1"),
                HealthCheck(name="b", status="failed", message="boom 2"),
            ]
        )
        assert r.passed is False

    def test_empty_checks_returns_true(self) -> None:
        """all() on an empty iterable returns True."""
        r = HealthReport(checks=[])
        assert r.passed is True


class TestHealthReportSummary:
    """The ``summary`` property."""

    def test_empty(self) -> None:
        r = HealthReport(checks=[])
        assert r.summary == {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "warning": 0,
            "healthy": True,
        }

    def test_all_passed(self) -> None:
        r = HealthReport(
            checks=[
                HealthCheck(name="a", status="passed", message="ok"),
            ]
        )
        assert r.summary == {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "warning": 0,
            "healthy": True,
        }

    def test_mixed_statuses(self) -> None:
        r = HealthReport(
            checks=[
                HealthCheck(name="a", status="passed", message="ok"),
                HealthCheck(name="b", status="passed", message="ok too"),
                HealthCheck(name="c", status="warning", message="hmm"),
                HealthCheck(name="d", status="failed", message="boom"),
            ]
        )
        assert r.summary == {
            "total": 4,
            "passed": 2,
            "failed": 1,
            "warning": 1,
            "healthy": False,
        }

    def test_all_warning(self) -> None:
        r = HealthReport(
            checks=[
                HealthCheck(name="a", status="warning", message="a"),
                HealthCheck(name="b", status="warning", message="b"),
            ]
        )
        assert r.summary == {
            "total": 2,
            "passed": 0,
            "failed": 0,
            "warning": 2,
            "healthy": True,
        }

    def test_all_failed(self) -> None:
        r = HealthReport(
            checks=[
                HealthCheck(name="a", status="failed", message="a"),
                HealthCheck(name="b", status="failed", message="b"),
                HealthCheck(name="c", status="failed", message="c"),
            ]
        )
        assert r.summary == {
            "total": 3,
            "passed": 0,
            "failed": 3,
            "warning": 0,
            "healthy": False,
        }


class TestHealthReportToDict:
    """The ``to_dict()`` method."""

    def test_structure(self) -> None:
        r = HealthReport(
            checks=[
                HealthCheck(name="alpha", status="passed", message="great", details={"v": 1}),
                HealthCheck(name="beta", status="warning", message="meh"),
            ]
        )
        d = r.to_dict()
        assert "summary" in d
        assert "checks" in d
        assert d["summary"] == r.summary
        assert len(d["checks"]) == 2

    def test_check_entry_structure(self) -> None:
        r = HealthReport(
            checks=[
                HealthCheck(name="chk", status="passed", message="msg", details={"k": "v"}),
            ]
        )
        entry = r.to_dict()["checks"][0]
        assert entry == {
            "name": "chk",
            "status": "passed",
            "message": "msg",
            "details": {"k": "v"},
        }

    def test_empty_report(self) -> None:
        r = HealthReport(checks=[])
        d = r.to_dict()
        assert d["summary"] == r.summary
        assert d["checks"] == []


# ── Doctor._check_python ─────────────────────────────────────────────────────


class TestDoctorCheckPython:
    """``Doctor._check_python()`` returns a correct HealthCheck."""

    def test_returns_healthcheck(self) -> None:
        result = Doctor._check_python()
        assert isinstance(result, HealthCheck)

    def test_name_is_python_version(self) -> None:
        result = Doctor._check_python()
        assert result.name == "python_version"

    def test_status_is_passed_on_python_310_plus(self) -> None:
        result = Doctor._check_python()
        assert result.status == "passed", f"expected 'passed', got {result.status!r}"

    def test_message_contains_version_and_platform(self) -> None:
        import sys

        result = Doctor._check_python()
        assert "Python" in result.message
        assert sys.platform in result.message
        assert "supported" in result.message  # 3.10+ should always show supported

    def test_details_contain_expected_keys(self) -> None:
        import sys

        result = Doctor._check_python()
        assert "version" in result.details
        assert "platform" in result.details
        assert "executable" in result.details
        assert result.details["platform"] == sys.platform
        assert result.details["executable"] == sys.executable


# ── Doctor.run_all ───────────────────────────────────────────────────────────


class TestDoctorRunAllWithoutAnalysisType:
    """``Doctor.run_all()`` with no analysis_type."""

    def test_returns_healthreport(self) -> None:
        doctor = Doctor()
        report = doctor.run_all()
        assert isinstance(report, HealthReport)

    def test_three_checks_returned(self) -> None:
        doctor = Doctor()
        report = doctor.run_all()
        assert len(report.checks) == 3

    def test_checks_have_expected_names(self) -> None:
        doctor = Doctor()
        report = doctor.run_all()
        names = {c.name for c in report.checks}
        assert names == {"python_version", "abi_install", "plugins"}


class TestDoctorRunAllWithAnalysisType:
    """``Doctor.run_all()`` with an analysis_type."""

    def test_returns_healthreport(self) -> None:
        doctor = Doctor()
        report = doctor.run_all(analysis_type="metagenomic_plasmid")
        assert isinstance(report, HealthReport)

    def test_five_checks_returned(self) -> None:
        doctor = Doctor()
        report = doctor.run_all(analysis_type="metagenomic_plasmid")
        assert len(report.checks) == 5

    def test_checks_include_resources_and_tools(self) -> None:
        doctor = Doctor()
        report = doctor.run_all(analysis_type="metagenomic_plasmid")
        names = {c.name for c in report.checks}
        assert "resources.metagenomic_plasmid" in names
        assert "tools.metagenomic_plasmid" in names

    def test_analysis_type_is_passed_through_to_check_names(self) -> None:
        doctor = Doctor()
        report = doctor.run_all(analysis_type="custom_type")
        names = {c.name for c in report.checks}
        assert "resources.custom_type" in names
        assert "tools.custom_type" in names

    def test_unknown_analysis_type_handled_gracefully(self) -> None:
        """An unknown analysis_type should not crash run_all."""
        doctor = Doctor()
        # _check_resources and _check_tools catch exceptions and return
        # HealthCheck(status="failed", ...), so this should succeed.
        report = doctor.run_all(analysis_type="nonexistent_plugin_xyz")
        assert isinstance(report, HealthReport)
        assert len(report.checks) == 5


# ── Integration / edge cases ─────────────────────────────────────────────────


class TestDoctorIntegration:
    """End-to-end sanity checks."""

    def test_run_all_report_is_healthy(self) -> None:
        """In a dev environment the report should be healthy."""
        doctor = Doctor()
        report = doctor.run_all()
        # Python, install, and plugins checks should all pass in CI/dev.
        assert report.passed is True

    def test_run_all_summary_has_correct_total(self) -> None:
        doctor = Doctor()
        report = doctor.run_all()
        assert report.summary["total"] == 3
        assert report.summary["healthy"] is True

    def test_to_dict_round_trips_with_analysis_type(self) -> None:
        doctor = Doctor()
        report = doctor.run_all(analysis_type="metagenomic_plasmid")
        d = report.to_dict()
        assert d["summary"]["total"] == 5
        assert len(d["checks"]) == 5
        for entry in d["checks"]:
            assert "name" in entry
            assert "status" in entry
            assert "message" in entry
            assert "details" in entry
