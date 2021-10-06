"""Test the ignore-unknown-dependency command line option.
"""

import pytest


def test_no_add_dependent(ctestdir):
    """No command line option, e.g. ignore-unknown-dependency is not set.

    Explicitly select only a single test that depends on another one.
    Since the other test has not been run at all, the selected test
    will be skipped.
    """
    ctestdir.makefile('.ini', pytest="""
            [pytest]
            add_dependent = false
            console_output_style = classic
        """)

    ctestdir.makepyfile("""
        import pytest

        @pytest.mark.dependency()
        def test_a():
            pass

        @pytest.mark.dependency()
        def test_b():
            pass

        @pytest.mark.dependency()
        def test_c():
            pass

        @pytest.mark.dependency(depends=["test_c"])
        def test_d():
            pass
    """)
    result = ctestdir.runpytest("--verbose", "test_no_add_dependent.py::test_d")
    result.assert_outcomes(passed=0, skipped=1, failed=0)
    result.stdout.re_match_lines(r"""
        .*::test_d SKIPPED(?:\s+\(.*\))?
    """)


def test_add_dependent(ctestdir):
    """No command line option, e.g. ignore-unknown-dependency is not set.

    Explicitly select only a single test that depends on another one.
    Since the other test has not been run at all, the selected test
    will be skipped.
    """
    ctestdir.makefile('.ini', pytest="""
            [pytest]
            add_dependent = true
            console_output_style = classic
        """)

    ctestdir.makepyfile("""
        import pytest

        @pytest.mark.dependency()
        def test_a():
            pass

        @pytest.mark.dependency()
        def test_b():
            pass

        @pytest.mark.dependency()
        def test_c():
            pass

        @pytest.mark.dependency(depends=["test_c"])
        def test_d():
            pass
    """)
    result = ctestdir.runpytest("--verbose", "test_add_dependent.py::test_d")
    result.assert_outcomes(passed=2, skipped=0, failed=0)
    result.stdout.re_match_lines(r"""
            .*::test_c PASSED
            .*::test_d PASSED
        """)


def test_add_dependent_level_2(ctestdir):
    """No command line option, e.g. ignore-unknown-dependency is not set.

    Explicitly select only a single test that depends on another one.
    Since the other test has not been run at all, the selected test
    will be skipped.
    """
    ctestdir.makefile('.ini', pytest="""
            [pytest]
            add_dependent = true
            console_output_style = classic
        """)

    ctestdir.makepyfile("""
        import pytest

        @pytest.mark.dependency()
        def test_a():
            pass

        @pytest.mark.dependency()
        def test_b():
            pass

        @pytest.mark.dependency(depends=["test_b"])
        def test_c():
            pass

        @pytest.mark.dependency(depends=["test_c"])
        def test_d():
            pass
    """)
    result = ctestdir.runpytest("--verbose", "test_add_dependent_level_2.py::test_d")
    print(result)
    result.assert_outcomes(passed=3, skipped=0, failed=0)
    result.stdout.re_match_lines(r"""
            .*::test_b PASSED
            .*::test_c PASSED
            .*::test_d PASSED
        """)
