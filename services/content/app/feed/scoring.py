"""Pure feed scoring functions — no I/O, no framework imports.

Default weights (must sum to 1.0):
  recency   = 0.40  — exponential decay, half-life = 24 h
  specialty = 0.30  — tag overlap with user's declared interests
  affinity  = 0.30  — accumulated interaction points with the post's author

All functions return values in [0.0, 1.0].

The WeightConfig dataclass allows per-cohort and per-experiment weight overrides.
All callers that omit the config= argument continue to use DEFAULT_WEIGHT_CONFIG.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timezone

# Points awarded per interaction type (used by service layer to compute raw score)
AFFINITY_POINTS: dict[str, float] = {
    "like": 1.0,
    "comment": 3.0,
    "share": 5.0,
}


@dataclass
class WeightConfig:
    """Feed scoring weight configuration.

    Used by cohorts and A/B experiments to override the default 40/30/30 split.
    All three weights should sum to 1.0 (not enforced at runtime — validated in schemas).
    """

    recency: float = 0.40
    specialty: float = 0.30
    affinity: float = 0.30
    # Cold-start threshold: users with fewer total interactions use cold-start feed.
    cold_start_threshold: int = 10
    # Affinity normalisation ceiling: this many raw pts = 1.0 affinity score.
    # e.g. 10 likes (1pt each) + 1 share (5pt) = 15 pts → 15/50 = 0.30 affinity
    affinity_ceiling: float = 50.0


DEFAULT_WEIGHT_CONFIG = WeightConfig()


def score_recency(created_at: datetime) -> float:
    """Exponential decay with a 24-hour half-life.

    Returns 1.0 for a brand-new post, 0.5 after 24 h, 0.25 after 48 h, etc.
    Posts older than 7 days receive a score close to 0 (~0.02) but never exactly 0.
    """
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    hours_old = max(0.0, (now - created_at).total_seconds() / 3600.0)
    return math.pow(2.0, -hours_old / 24.0)


def _tag_overlap(tags: list[str] | None, interests: list[str] | None) -> float:
    """Return 1.0 if any case-insensitive overlap, else 0.0."""
    if not tags or not interests:
        return 0.0
    tag_set = {t.lower().strip() for t in tags}
    interest_set = {i.lower().strip() for i in interests}
    return 1.0 if tag_set & interest_set else 0.0


def score_specialty(
    post_tags: list[str] | None,
    user_interests: list[str],
    post_hashtags: list[str] | None = None,
) -> float:
    """Combined topic relevance score (specialty tags + hashtags).

    Specialty tag match (controlled taxonomy) → 1.0.
    Hashtag overlap with user interests      → 0.7 (lower weight, freeform tags).
    Returns max of the two, capped at 1.0.
    """
    specialty_score = _tag_overlap(post_tags, user_interests)
    hashtag_score = _tag_overlap(post_hashtags, user_interests)
    return min(1.0, max(specialty_score, 0.7 * hashtag_score))


def normalise_affinity(
    raw_points: float,
    config: WeightConfig = DEFAULT_WEIGHT_CONFIG,
) -> float:
    """Normalise raw affinity points to [0.0, 1.0] using the config ceiling."""
    return min(1.0, raw_points / config.affinity_ceiling)


def score_composite(
    recency: float,
    specialty: float,
    affinity: float,
    config: WeightConfig = DEFAULT_WEIGHT_CONFIG,
) -> float:
    """Weighted composite ranking score in [0.0, 1.0]."""
    return (
        config.recency * recency
        + config.specialty * specialty
        + config.affinity * affinity
    )
