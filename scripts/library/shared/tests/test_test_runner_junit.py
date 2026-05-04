"""Tests for TestRunner JUnit XML integration.

Verifies that _build_pytest_args correctly handles the junit_xml_path
parameter, and that --junit-xml coexists with -o addopts overrides.
"""

from pathlib import Path

from shared.test_runner import TestConfig, TestRunner


def _make_runner(
    has_xdist: bool = False,
    exclude_markers: list[str] | None = None,
) -> TestRunner:
    """Create a TestRunner with controlled xdist state.

    Args:
        has_xdist: Whether to simulate pytest-xdist availability.
        exclude_markers: Optional markers to exclude.

    Returns:
        Configured TestRunner instance.
    """
    config = TestConfig(
        project_root=Path("/fake/project"),
        project_name="test-project",
        exclude_markers=exclude_markers,
    )
    runner = TestRunner(config)
    runner.has_xdist = has_xdist
    return runner


class TestBuildPytestArgsJunitXml:
    """_build_pytest_args with junit_xml_path parameter."""

    def test_junit_xml_path_appended_when_provided(self) -> None:
        """--junit-xml flag appears in args when path is provided."""
        runner = _make_runner()
        xml_path = Path("/fake/run-dir/junit.xml")

        args = runner._build_pytest_args(
            python_exe="python",
            coverage=False,
            verbose=False,
            junit_xml_path=xml_path,
        )

        assert "--junit-xml" in args
        idx = args.index("--junit-xml")
        assert args[idx + 1] == str(xml_path)

    def test_no_junit_xml_when_none(self) -> None:
        """No --junit-xml flag when junit_xml_path is None."""
        runner = _make_runner()

        args = runner._build_pytest_args(
            python_exe="python",
            coverage=False,
            verbose=False,
            junit_xml_path=None,
        )

        assert "--junit-xml" not in args

    def test_no_junit_xml_when_omitted(self) -> None:
        """No --junit-xml flag when junit_xml_path is not passed."""
        runner = _make_runner()

        args = runner._build_pytest_args(
            python_exe="python",
            coverage=False,
            verbose=False,
        )

        assert "--junit-xml" not in args

    def test_junit_xml_alongside_addopts_override(self) -> None:
        """--junit-xml coexists with -o addopts in parallel-phase args.

        When xdist is enabled and no coverage, _build_pytest_args produces
        an -o addopts=... override. The --junit-xml flag should appear as
        a separate flag, not inside addopts.
        """
        runner = _make_runner(has_xdist=True)
        xml_path = Path("/fake/run-dir/junit-parallel.xml")

        args = runner._build_pytest_args(
            python_exe="python",
            coverage=False,
            verbose=False,
            junit_xml_path=xml_path,
        )

        # Both -o and --junit-xml should be present
        assert "-o" in args
        assert "--junit-xml" in args

        # --junit-xml should be a standalone flag, not buried inside addopts
        junit_idx = args.index("--junit-xml")
        assert args[junit_idx + 1] == str(xml_path)

        # The addopts value should NOT contain --junit-xml
        o_idx = args.index("-o")
        addopts_value = args[o_idx + 1]
        assert "--junit-xml" not in addopts_value

    def test_junit_xml_with_coverage_no_xdist_flags(self) -> None:
        """--junit-xml works with coverage enabled (no parallel flags)."""
        runner = _make_runner(has_xdist=True)
        xml_path = Path("/fake/run-dir/junit.xml")

        args = runner._build_pytest_args(
            python_exe="python",
            coverage=True,
            verbose=False,
            junit_xml_path=xml_path,
        )

        assert "--junit-xml" in args
        # Coverage disables parallel, so no -n auto
        assert "-n" not in args

    def test_junit_xml_with_verbose_and_marker(self) -> None:
        """--junit-xml appears alongside verbose and marker flags."""
        runner = _make_runner()
        xml_path = Path("/fake/run-dir/junit.xml")

        args = runner._build_pytest_args(
            python_exe="python",
            coverage=False,
            verbose=True,
            marker_expr="unit",
            junit_xml_path=xml_path,
        )

        assert "--junit-xml" in args
        assert "-v" in args
        assert "-m" in args
