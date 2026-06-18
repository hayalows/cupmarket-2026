"""Retry the official Round-of-32 bracket lock on every automation run."""

from __future__ import annotations

import json

try:
    from . import bracket_lock_execution, update_pipeline
except ImportError:
    import bracket_lock_execution
    import update_pipeline


def main() -> dict:
    matches, _ = update_pipeline.fetch_world_cup_matches()
    result = bracket_lock_execution.lock_official_bracket_from_matches(
        update_pipeline.REPO_ROOT,
        matches,
    )
    print("Exact bracket lock:", json.dumps(result, sort_keys=True))
    return result


if __name__ == "__main__":
    main()
