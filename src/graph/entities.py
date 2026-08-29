"""Entity names in, canonical keys out. Exact match only.

ADR-011 is the whole of this module's design, and its measurement is why the
module is this short. Across 125 entity names the corpus shares 20 given names
and 19 surnames, and six pairs of *genuinely distinct* entities sit at >= 0.80
string similarity - `caedmon_fellgard ~ ederon_fellgard` at 0.839, where
`ederon_fellgard` is the subject of dev question 1b_007. Any similarity
threshold loose enough to be useful merges those two; any threshold tight enough
to separate them is tight enough that exact matching would have worked anyway.

So there is no fuzzy matching here, and no embedding similarity either (ADR-011
rejected both on the same measurement). Fuzzy matching may *generate candidates*
for a human or a disambiguator to choose between; it may never *select a winner*
(F-010). This module does not even generate candidates - it resolves, or it
reports that it cannot.

The normalisation is deliberately closed: lowercase, collapse non-alphanumerics
to `_`, drop a leading `the_`. Nothing else. The article rule was verified rather
than assumed - it merges exactly 5 pairs corpus-wide, every one genuinely the
same entity, and collides nothing. 1b_009 needs it, because
`the_purge_of_blackport.md` writes `[[Iron-Ring Cartel]]` while every other page
writes `[[The Iron-Ring Cartel]]`.
"""

from __future__ import annotations

import re
import unicodedata

#: Matches a leading English article on an already-slugified name.
_LEADING_ARTICLE = re.compile(r"^the_")

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Lowercase, collapse runs of non-alphanumerics to `_`, trim.

    Curly apostrophes are folded to ASCII first: the corpus uses U+2019, and a
    name that slugifies differently depending on which apostrophe a scribe typed
    is two nodes where there should be one.
    """
    folded = unicodedata.normalize("NFKD", name).replace("’", "'")
    return _NON_ALNUM.sub("_", folded.lower()).strip("_")


def canonical_key(name: str) -> str:
    """The key two mentions of the same entity must agree on.

    This is `slugify` plus the measured article rule, and nothing more. Resist
    adding steps: every extra normalisation is a chance to merge two entities the
    corpus distinguishes, and the corpus distinguishes `gloamreach` from
    `gloammarch` by one letter.
    """
    return _LEADING_ARTICLE.sub("", slugify(name))


def display_name(name: str) -> str:
    """The name as written, with whitespace tidied. Never reconstructed.

    Slugification is one-way - "The Thrice-Bound Edge" becomes
    "the_thrice_bound_edge" and the hyphen cannot be recovered. So a display name
    is always carried through from the source text rather than rebuilt from a
    key, and comparisons always happen on keys.
    """
    return re.sub(r"\s+", " ", name).strip()
