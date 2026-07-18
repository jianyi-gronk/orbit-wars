"""Check local infrastructure through both runtime service entry points."""

import json

from dotenv import load_dotenv
from orbit_api.main import dependency_health
from orbit_match_worker.app import dependency_health as check_worker_dependencies


def main() -> None:
    load_dotenv()
    result = {
        "api": dependency_health(),
        "match_worker": check_worker_dependencies(),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
