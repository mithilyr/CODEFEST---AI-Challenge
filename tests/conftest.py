"""Fixtures shared across the whole test suite.

WHY THESE ARE SESSION-SCOPED
------------------------------
`build_graph()` costs about 14 seconds. Seven test modules each declared their
own module-scoped `graph` fixture, so the suite built the same 117-entity graph
seven times and spent roughly two minutes doing it - measured with
`pytest --durations`, where nine of the twelve slowest entries were fixture
*setup* rather than any test's own work.

The graph is read-only once built, and every test that takes it only queries
it, so one build serves the whole session. Module scope bought nothing that
session scope does not.

A module may still declare its own `graph` if it ever needs a mutated one;
pytest resolves the nearest definition, so overriding stays possible without
anything here changing.
"""

from __future__ import annotations

import pytest

from src.graph.build import build_graph, load_relation_map
from src.settings import get_settings


@pytest.fixture(scope="session")
def corpus_root():
    """Skip rather than fail when the corpus is absent - it is ~123 MB and
    deliberately not committed (see README.md)."""
    settings = get_settings()
    if not settings.corpus_path.is_dir():
        pytest.skip(f"Corpus not present at {settings.corpus_path}; see README.md")
    return settings.corpus_path


@pytest.fixture(scope="session")
def graph(corpus_root):
    """The built knowledge graph: 117 entities, 261 edges. Built once."""
    return build_graph()


@pytest.fixture(scope="session")
def relations():
    """`config/relations.yaml`, parsed. Needs no corpus."""
    return load_relation_map()
