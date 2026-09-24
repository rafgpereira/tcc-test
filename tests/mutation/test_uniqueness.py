"""The mutants of a problem are different from each other and from the original (the ask of the
round: "garantir que os mutantes são diferentes entre si").

The file is the REAL ``AC_ref.cpp`` of problem 189_C, with its real limits and official suite.
Three properties are proven directly on the final set of mutants:

(a) all ``source_sha256`` are pairwise distinct;
(b) none equals the hash of the original ``AC_ref.cpp``;
(c) generating twice from the same file gives the same hashes in the same order (no seed: the order
    comes from the syntax tree walk).

The unit variant answers from a fake engine (a fixed share of the candidates fails to compile, so
the stream has discards in it) and runs anywhere. The integration variant runs the real engine.
"""

from pathlib import Path

import pytest

from dataset.schemas.metadata import Metadata
from dataset.schemas.testes import Testes
from dataset.validation.engine import real_engine
from dataset.validation.suite import suite_from_testes
from mutation import config
from mutation.orchestrator import select_mutants
from mutation.validation import sha256_of
from sandbox import isolation
from sandbox.types import ExecutionLimits, Verdict

FIXTURE = Path(__file__).parent / "fixtures" / "189_C"
SOURCE = (FIXTURE / "AC_ref.cpp").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def suite():
    return suite_from_testes(Testes.model_validate_json((FIXTURE / "testes.json").read_text()))


@pytest.fixture(scope="module")
def limits():
    metadata = Metadata.from_folder(FIXTURE)
    return ExecutionLimits(metadata.time_limit_seconds, metadata.memory_limit_bytes)


def mixed(source: str) -> list:
    """A deterministic mix by content: a quarter does not compile, a quarter is equivalent."""
    bucket = int(sha256_of(source), 16) % 4
    return ["CE"] if bucket == 0 else [Verdict.AC] if bucket == 1 else [Verdict.WA]


def test_the_final_hundred_are_pairwise_distinct_and_never_the_original(make_engine, suite, limits):
    engine = make_engine(mixed)
    selection = select_mutants("189_C", SOURCE, suite, limits, engine=engine.as_engine())
    hashes = [m.source_sha256 for m in selection.mutants]
    assert len(hashes) == config.MUTANTS_PER_PROBLEM
    assert len(set(hashes)) == len(hashes)  # (a)
    assert sha256_of(SOURCE) not in hashes  # (b)
    assert all(m.source != SOURCE for m in selection.mutants)
    assert selection.discards  # the stream really had discards in it


def test_generating_twice_gives_the_same_hashes_in_the_same_order(make_engine, suite, limits):
    first = select_mutants("189_C", SOURCE, suite, limits, engine=make_engine(mixed).as_engine())
    second = select_mutants("189_C", SOURCE, suite, limits, engine=make_engine(mixed).as_engine())
    assert [m.source_sha256 for m in first.mutants] == [m.source_sha256 for m in second.mutants]
    assert [m.index for m in second.mutants] == list(range(1, 101))  # (c)


def test_no_mutant_alters_a_string_a_comment_or_the_bytes_outside_its_site(
    make_engine, suite, limits
):
    selection = select_mutants(
        "189_C", SOURCE, suite, limits, engine=make_engine(mixed).as_engine()
    )
    original = SOURCE.encode("utf-8")
    for mutant in selection.mutants:
        (site,) = mutant.sites
        changed = mutant.source.encode("utf-8")
        assert changed.startswith(original[: site.start_byte])
        assert changed.endswith(original[site.end_byte :])


@pytest.mark.integration
def test_with_the_real_engine_the_accepted_mutants_are_distinct_and_really_wrong(suite, limits):
    isolation.prepare_slot_workdir(0)
    engine = real_engine()
    selection = select_mutants("189_C", SOURCE, suite, limits, engine=engine, quota=8)
    hashes = [m.source_sha256 for m in selection.mutants]
    assert len(hashes) == 8 and len(set(hashes)) == 8 and sha256_of(SOURCE) not in hashes
    for mutant in selection.mutants[:2]:  # spot check, outside the engine's own validation
        compiled = engine.compile(mutant.source, 0)
        assert compiled.ok
        assert engine.run_suite(compiled.binary, suite.tests, limits, 0).verdict is Verdict.WA
