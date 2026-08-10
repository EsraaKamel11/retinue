"""Seeded generator for UNJUDGED volume only (spec 7.2): rosters the matcher filters.
Judged content is hand-authored and frozen - never generated. All figures invented."""
from __future__ import annotations
import random

_SECTORS = ("logistics", "devtools", "climate", "health-admin")
_JURIS = ("US", "UK", "DE")

def generate_rosters(seed: int, n: int) -> tuple[dict, ...]:
    rng = random.Random(seed)
    return tuple(
        {"investor_id": f"synth-{i:03d}",
         "sector": rng.choice(_SECTORS),
         "stage": rng.choice(("pre-seed", "seed", "series-a")),
         "geography": rng.choice(("us-east", "eu-west", "mena")),
         "jurisdiction": rng.choice(_JURIS),
         "check_floor": rng.choice((100_000, 300_000, 700_000)),
         "check_ceiling": rng.choice((1_500_000, 4_000_000, 9_000_000))}
        for i in range(n))
