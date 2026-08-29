"""Deterministic knowledge graph over the wiki infoboxes.

Nothing here calls a model. The graph is built by parsing structured cells with
named handlers (ADR-010), mapping field names to relations through a config file
a judge can argue with (ADR-005's precedent), and resolving entity names by exact
match on a normalised form (ADR-011).
"""
