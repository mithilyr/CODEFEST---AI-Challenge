"""The corpus's folder names are config, not code (ADR-035).

WHY THIS FILE EXISTS. `build.py` filtered on the literal string `"wiki"` and
`corroborate.py` on a frozenset of three literal collection names. MEASURED on
6 Sep, by copying a synthetic corpus and renaming its folders to `manuals/`,
`specs/` and `logs/`: ingestion read all 10 documents and all 18 evidence units
correctly, assigned the three new collections correctly, and the graph then
built **0 nodes and 0 edges** — silently, because no unit's collection was the
string "wiki".

That is the worst failure shape this project recognises: not a wrong answer, not
a decline, but a system that reads every file and answers nothing while
reporting no problem at all. A corpus with differently named folders and a
corpus with no infoboxes were indistinguishable.

The competition's final round requires adapting the solution to requirements
announced on the day, so "the folder must be called wiki" is a constraint that
had to be either removed or said out loud. These tests pin the removal.
"""

from __future__ import annotations

import pytest
import yaml

from src.graph.build import RelationMap, build_graph, load_relation_map
from src.settings import PROJECT_ROOT, get_settings

@pytest.fixture
def synthetic_corpus(tmp_path, monkeypatch):
    """Point the process at a throwaway corpus, and put it back afterwards.

    `get_settings()` is `@lru_cache(maxsize=1)`, so setting CORPUS_PATH after
    any other test has already read the settings does nothing. These two tests
    passed alone and failed in the suite until this fixture existed - the cache
    has to be cleared on the way in *and* on the way out, or every later test
    inherits the throwaway corpus and the session-scoped `graph` fixture is
    built from three fake pages.
    """
    root = _synthetic_corpus(tmp_path / "corpus")
    monkeypatch.setenv("CORPUS_PATH", str(root))
    get_settings.cache_clear()
    try:
        yield root
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

def test_the_shipped_config_declares_the_corpus_we_measured_against():
    """`sources` is config, and it still says what the ADRs quote."""
    relations = load_relation_map()
    assert relations.builds == frozenset({"wiki"})
    assert relations.corroborates == frozenset({"chronicles", "codex", "ephemera"})

def test_a_collection_cannot_both_build_and_corroborate(tmp_path):
    """An edge parsed from a page is not corroborated by that same page.

    ADR-027's rule, now enforceable because both lists are in one file where an
    editor can put a name in both by accident. Raised rather than resolved: either
    resolution would be a guess at what the editor meant.
    """
    source = (PROJECT_ROOT / "config" / "relations.yaml").read_text(encoding="utf-8")
    raw = yaml.safe_load(source)
    raw["sources"] = {"builds": ["wiki"], "corroborates": ["wiki", "codex"]}
    path = tmp_path / "relations.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="both"):
        load_relation_map(path)

def test_absent_sources_key_falls_back_to_the_shipped_default(tmp_path):
    """A config written before ADR-035 still builds the graph it always did."""
    raw = yaml.safe_load(
        (PROJECT_ROOT / "config" / "relations.yaml").read_text(encoding="utf-8")
    )
    raw.pop("sources", None)
    path = tmp_path / "relations.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    assert load_relation_map(path).builds == frozenset({"wiki"})

def _synthetic_corpus(root):
    """A three-page corpus in the shape the parser expects, under `manuals/`."""
    (root / "manuals").mkdir(parents=True)
    (root / "specs").mkdir()
    (root / "manuals" / "harbourwatch_guild.md").write_text(
        "# The Harbourwatch Guild\n\n"
        "| Name | The Harbourwatch Guild |\n"
        "| Members | [[Perrin Vale]] |\n"
        "| Victor of | [[The Saltpier Dispute]] |\n",
        encoding="utf-8",
    )
    (root / "manuals" / "perrin_vale.md").write_text(
        "# Perrin Vale\n\n"
        "| Name | Perrin Vale |\n"
        "| Membership | [[The Harbourwatch Guild]] |\n",
        encoding="utf-8",
    )
    (root / "manuals" / "the_saltpier_dispute.md").write_text(
        "# The Saltpier Dispute\n\n"
        "| Name | The Saltpier Dispute |\n"
        "| Victor | [[The Harbourwatch Guild]] |\n",
        encoding="utf-8",
    )
    (root / "specs" / "notes.txt").write_text(
        "Perrin Vale is a member of The Harbourwatch Guild.\n", encoding="utf-8"
    )
    return root

def test_a_corpus_with_different_folder_names_says_so_instead_of_going_silent(
    synthetic_corpus,
):
    """The measured 6 Sep failure, pinned: 0 nodes and 0 edges, no explanation.

    The error must name what the corpus actually has, because the person reading
    it is holding a corpus they did not create and has no reason to guess that a
    folder name is the problem.
    """
    with pytest.raises(ValueError) as excinfo:
        build_graph()

    message = str(excinfo.value)
    assert "manuals" in message, "the error must name the collections found"
    assert "sources.builds" in message, "the error must name the fix"

def test_pointing_sources_at_the_new_folder_builds_the_graph(synthetic_corpus):
    """The fix is config, not code: name the folder and the edges appear.

    This is the claim the final round's "adapt on the day" requirement rests on,
    so it is a test rather than a sentence in a README.
    """
    shipped = load_relation_map()
    relations = RelationMap(
        forward=shipped.forward,
        reverse=shipped.reverse,
        inverses=shipped.inverses,
        attributes=shipped.attributes,
        verbs=shipped.verbs,
        question_cues=shipped.question_cues,
        builds=frozenset({"manuals"}),
        corroborates=frozenset({"specs"}),
    )

    graph = build_graph(relations=relations)

    assert graph.nodes, "a renamed corpus must build nodes once config names it"
    assert graph.edges, "a renamed corpus must build edges once config names it"
    assert "perrin_vale" in graph.nodes
    assert any(
        e.source == "perrin_vale" and e.relation == "member_of" for e in graph.edges
    )
