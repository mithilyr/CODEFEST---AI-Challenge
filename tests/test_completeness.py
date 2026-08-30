"""Tests for the independent answer-key completeness checker.

The first test is the load-bearing one: it enforces mechanically that this
checker never imports `src/graph/`. Ground truth validated by the system under
test is not ground truth, and a future refactor that "helpfully" reuses the
graph's entity resolver would silently make every Checkpoint 2 number
meaningless while all the tests still passed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from eval.completeness import (
    FIELD_STEMS,
    build_vocabulary,
    check,
    enumerate_entity_answers,
    normalise,
    wiki_units,
)
from src.ingest.pipeline import ingest
from src.settings import PROJECT_ROOT, get_settings

MODULE = PROJECT_ROOT / "eval" / "completeness.py"


@pytest.fixture(scope="module")
def evidence():
    if not get_settings().corpus_path.is_dir():
        pytest.skip("Corpus not present; see README.md")
    return ingest().evidence


def test_checker_never_imports_the_system_it_checks():
    """The independence guarantee, enforced rather than promised."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    offenders = [m for m in imported if m.startswith("src.graph")]
    assert not offenders, (
        f"completeness.py imports {offenders}. Ground truth validated by the "
        "system under test is not ground truth - see the module docstring."
    )


def test_checker_does_not_read_the_graphs_config_files():
    """`relations.yaml` is the graph's map; reading it would close the loop.

    Checks string constants the code actually evaluates, not prose. The module
    docstring names the file in order to explain why it is *not* used, and a
    naive text search would fail on its own explanation.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    # The project's shared configuration is YAML. A checker that reads no YAML
    # cannot be reading the graph's relation map or the authority model, which
    # is the invariant that matters - not whether the prose mentions them.
    assert "yaml" not in imported


def test_type_suffix_is_stripped_from_names():
    """The checker's own first bug: `(faction)` hid the pivot's page.

    With the suffix left in, `the_silent_choir.md` normalised to
    `silent_choir_faction`, never matched the pivot, and the faction-page
    direction never ran - reproducing F-015's blind spot inside the tool built
    to catch it.
    """
    assert normalise("The Silent Choir (faction)") == normalise("The Silent Choir")
    assert normalise("Corvus Hollowmere the Pale (character)") == normalise(
        "Corvus Hollowmere the Pale"
    )


def test_leading_article_folds_but_distinct_names_do_not():
    assert normalise("[[Iron-Ring Cartel]]") == normalise("The Iron-Ring Cartel")
    assert normalise("Gloamreach") != normalise("Gloammarch")


def test_1b_006_enumerates_fourteen_from_both_directions(evidence):
    """F-015's question, and the whole reason this module exists.

    Six names live on the faction page's `Members` row and eight on individual
    character pages, with zero overlap. A checker that reads one direction finds
    half and reports confidence, which is exactly what the human reviewer did.
    """
    by_doc = wiki_units(evidence)
    found = enumerate_entity_answers(
        "The Silent Choir", "has_member", by_doc, build_vocabulary(by_doc)
    )

    assert len(found) == 14

    directions = {
        name: {s.direction for s in supports} for name, supports in found.items()
    }
    from_faction_page = [n for n, d in directions.items() if "pivot_page" in d]
    from_character_pages = [n for n, d in directions.items() if "subject_page" in d]

    assert len(from_faction_page) == 6
    assert len(from_character_pages) == 8
    assert not set(from_faction_page) & set(from_character_pages), "disjoint by design"


def test_every_candidate_carries_a_citable_passage(evidence):
    """A candidate without evidence is an assertion, which is what we are avoiding."""
    by_doc = wiki_units(evidence)
    found = enumerate_entity_answers(
        "The Silent Choir", "has_member", by_doc, build_vocabulary(by_doc)
    )
    for supports in found.values():
        assert supports
        for support in supports:
            assert support.document and support.locator and support.text.strip()


def test_single_answer_siblings_are_not_reported_as_missing(evidence):
    """1b_007: the Cartel won two conflicts; only one is an accord.

    Both are true facts. Reporting the other as a "missing answer" would train
    the team to ignore this report, so a single-answer question routes extras to
    `semantic_siblings` for a human instead.
    """
    import json

    key = json.loads((PROJECT_ROOT / "eval" / "answer_key.json").read_text("utf-8"))
    findings = {f.qid: f for f in check(key, evidence)}

    finding = findings["1b_007"]
    assert finding.missing_from_key == []
    assert finding.semantic_siblings, "the other victories should still be surfaced"


def test_recorded_conflicts_are_not_reported_as_missing(evidence):
    """1c_000's 286 AS decoy is documented in the key, so it is not an omission."""
    import json

    key = json.loads((PROJECT_ROOT / "eval" / "answer_key.json").read_text("utf-8"))
    findings = {f.qid: f for f in check(key, evidence)}

    assert findings["1c_000"].missing_from_key == []
    assert "286_as" in findings["1c_000"].known_conflicts


def test_no_question_currently_shows_a_recall_defect(evidence):
    """The standing result. If this fails, the key has drifted narrower."""
    import json

    key = json.loads((PROJECT_ROOT / "eval" / "answer_key.json").read_text("utf-8"))
    offenders = {f.qid: f.missing_from_key for f in check(key, evidence) if f.missing_from_key}
    assert not offenders, f"key narrower than the corpus: {offenders}"


def test_relation_families_cover_every_relation_the_key_uses(evidence):
    """An unmapped relation would enumerate nothing and look like agreement."""
    import json

    key = json.loads((PROJECT_ROOT / "eval" / "answer_key.json").read_text("utf-8"))
    used = {
        hop["relation"]
        for q in key["questions"]
        for p in q.get("acceptable_paths", [])
        for hop in p["hops"]
    }
    assert not used - set(FIELD_STEMS), f"no field family for {used - set(FIELD_STEMS)}"
