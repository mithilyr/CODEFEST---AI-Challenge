"""The demo surface. A presentation layer over `src.query.engine`, nothing more.

Every fact this package displays is read from an `Answer` the engine already
produced. Nothing here retrieves, traverses, resolves an entity, ranks a tier,
decides a conflict, or writes a sentence of prose about the result. If a
question cannot be answered, the UI says which named `EvidenceStatus` the
engine returned and shows the note it attached - it does not soften it,
reword it, or guess.

That boundary is enforced by a test, not just by intent:
`tests/test_ui.py::test_view_and_render_import_no_reasoning_code`.
"""
