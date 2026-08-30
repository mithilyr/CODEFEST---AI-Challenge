"""The query layer: question text in, an answer traceable to the graph's evidence out.

Every stage tries a deterministic resolution first and only escalates to an LLM
on an explicit, testable failure condition (CLAUDE.md's architectural
principle). Nothing here calls a model by default.

    question -> entity resolution -> question routing -> bounded traversal
             -> evidence sufficiency -> answer, with provenance attached

Each stage is its own module so a teammate can point at one file and defend it:

- `resolve.py`   - entity mentions to graph keys (ADR-011: exact, then
  normalised, then a measured alias rule, then fuzzy *candidates* that are
  never auto-selected).
- `route.py`     - the small set of structural question shapes actually
  present in the 1B dev set, matched by trigger phrase, not by hard-coding a
  question's entities.
- `conflict.py`  - same-tier contradiction detection between what a target
  page asserts and what the claimed source's own page says, distinguishing an
  explicit denial from mere silence (F-014).
- `evidence.py`  - the sufficiency states a traversal can end in, named
  explicitly rather than collapsed into "found" / "not found".
- `engine.py`    - wires the above into one call, `answer_question`.
"""
