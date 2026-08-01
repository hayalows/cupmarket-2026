"""Write durable product-health artifacts after a successful workflow pass."""

from __future__ import annotations

from pathlib import Path

try:
    from . import adaptive_governance, publication_manifest, tournament_retrospective
except ImportError:
    import adaptive_governance
    import publication_manifest
    import tournament_retrospective


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    data_dir = ROOT / "data"
    state_dir = ROOT / "backend" / "state"
    if publication_manifest.is_archive_finalized(ROOT):
        manifest = publication_manifest.load_publication_manifest(ROOT)
        archive = publication_manifest.load_archive_manifest(ROOT)
        if (
            not manifest.get("archive", {}).get("archive_id")
            or manifest.get("archive", {}).get("release_tag")
            != tournament_retrospective.ARCHIVE_RELEASE_TAG
            or manifest.get("archive", {}).get("source_commit")
            != archive.get("source_commit")
            or manifest.get("publication", {}).get("status") != "final_archive_locked"
        ):
            manifest = publication_manifest.write_publication_manifest(ROOT)
            archive = tournament_retrospective.finalize_archive(
                ROOT,
                force=True,
                finalized_at_utc=manifest.get("archive", {}).get("finalized_at_utc"),
            )
            if not manifest.get("archive", {}).get("archive_id"):
                print("Final archive manifest enriched:", archive.get("archive_id"))
            else:
                print("Final archive publication status locked.")
        else:
            print("Final archive locked:", manifest.get("archive", {}).get("archive_id"))
        return

    health = adaptive_governance.write_adaptive_model_health(
        data_dir / "world_cup_2026_matches_latest.csv",
        state_dir / "world_cup_prediction_ledger.csv",
        data_dir / "adaptive_model_health.json",
    )
    provisional_manifest = publication_manifest.build_publication_manifest(ROOT)
    if provisional_manifest.get("archive", {}).get("final_completed"):
        archive = tournament_retrospective.finalize_archive(
            ROOT,
            finalized_at_utc=provisional_manifest.get("generated_at_utc"),
        )
        print("Final archive:", archive.get("archive_id"))
    manifest = publication_manifest.write_publication_manifest(ROOT)
    if manifest.get("archive", {}).get("final_completed"):
        tournament_retrospective.finalize_archive(
            ROOT,
            force=True,
            finalized_at_utc=manifest.get("archive", {}).get("finalized_at_utc"),
        )
    print("Adaptive guardrail:", health["decision"])
    print("Publication manifest:", manifest["publication"]["status"])


if __name__ == "__main__":
    main()
