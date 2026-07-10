"""Write durable product-health artifacts after a successful workflow pass."""

from __future__ import annotations

from pathlib import Path

try:
    from . import adaptive_governance, publication_manifest
except ImportError:
    import adaptive_governance
    import publication_manifest


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    data_dir = ROOT / "data"
    state_dir = ROOT / "backend" / "state"
    health = adaptive_governance.write_adaptive_model_health(
        data_dir / "world_cup_2026_matches_latest.csv",
        state_dir / "world_cup_prediction_ledger.csv",
        data_dir / "adaptive_model_health.json",
    )
    manifest = publication_manifest.write_publication_manifest(ROOT)
    print("Adaptive guardrail:", health["decision"])
    print("Publication manifest:", manifest["publication"]["status"])


if __name__ == "__main__":
    main()
