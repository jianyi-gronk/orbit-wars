"""Provision a small real Agent competition for an otherwise empty deployment."""

from __future__ import annotations

import argparse
import json

from orbit_api.db.session import SessionLocal
from orbit_api.domain.warmup import WARMUP_FIXTURES, provision_warmup
from orbit_api.infrastructure.match_queue import RedisMatchQueue


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matches",
        type=int,
        default=len(WARMUP_FIXTURES),
        help=f"number of stable ranked fixtures to queue (0-{len(WARMUP_FIXTURES)})",
    )
    arguments = parser.parse_args()
    with SessionLocal() as session:
        result = provision_warmup(
            session,
            RedisMatchQueue.from_environment(),
            match_count=arguments.matches,
        )
    print(
        json.dumps(
            {
                "fleetPublicIds": result.fleet_public_ids,
                "matchPublicIds": result.match_public_ids,
                "createdFleets": result.created_fleets,
                "createdMatches": result.created_matches,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
