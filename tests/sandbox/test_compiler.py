"""Tests for the compiler (T039; FR-008).

The flag tests are unit tests; compiling with the real g++ is an integration test that only runs
in the `sandbox` service.
"""

import pytest

from sandbox import compiler

VALID = '#include <cstdio>\nint main(){ std::puts("ok"); }\n'
# A dynamic exception specification is an error since C++17 but is accepted by gnu++14 and gnu++11.
ONLY_UP_TO_CXX14 = "void f() throw(int);\nint main(){ return 0; }\n"
SYNTAX_ERROR = "int main( { return 0 }\n"


def test_the_flags_are_exactly_those_of_the_original_judge():
    assert compiler.COMPILE_FLAGS == (
        "-Wall",
        "-Wextra",
        "-Wconversion",
        "-static",
        "-DONLINE_JUDGE",
        "-O2",
    )


def test_the_command_has_the_standard_and_no_windows_linker_option():
    command = compiler.build_command("gnu++17", "main.cpp", "main")
    assert command[0] == "g++"
    assert "-std=gnu++17" in command
    assert not any("--stack" in part or part.startswith("-Wl,") for part in command)
    for flag in compiler.COMPILE_FLAGS:
        assert flag in command


def test_the_cascade_of_standards_is_from_the_newest_to_the_oldest():
    assert compiler.STANDARD_CASCADE == ("gnu++20", "gnu++17", "gnu++14", "gnu++11")


@pytest.mark.integration
def test_a_valid_program_compiles_with_the_newest_standard(workdir, slot):
    result = compiler.compile_cpp(VALID, workdir, slot)
    assert result.ok
    assert result.standard_used == "gnu++20"
    assert result.binary is not None and result.binary.is_file()
    assert [a.standard for a in result.attempts] == ["gnu++20"]


@pytest.mark.integration
def test_the_cascade_falls_back_until_a_standard_accepts_the_program(workdir, slot):
    result = compiler.compile_cpp(ONLY_UP_TO_CXX14, workdir, slot)
    assert result.ok
    assert result.standard_used == "gnu++14"
    assert [a.standard for a in result.attempts] == ["gnu++20", "gnu++17", "gnu++14"]
    assert [a.ok for a in result.attempts] == [False, False, True]


@pytest.mark.integration
def test_a_syntax_error_fails_the_four_standards_with_the_four_diagnostics(workdir, slot):
    result = compiler.compile_cpp(SYNTAX_ERROR, workdir, slot)
    assert not result.ok
    assert result.binary is None
    assert result.standard_used is None
    assert [a.standard for a in result.attempts] == list(compiler.STANDARD_CASCADE)
    assert all(not a.ok and a.diagnostic.strip() for a in result.attempts)
