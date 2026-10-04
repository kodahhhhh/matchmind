"""Reproduce W12 without refitting upstream models or overwriting the baseline."""

import shutil

from matchmind.backtest.common import output, root, save


def snapshot() -> None:
    destination = output() / "w12_before"
    if (destination / "backtest.json").exists():
        return
    destination.mkdir(exist_ok=True)
    for path in output().iterdir():
        if path.is_file() and not path.name.startswith("squad_"):
            shutil.copy2(path, destination / path.name)
    for path in (root() / "models").glob("backtest_inplay.*"):
        shutil.copy2(path, destination / path.name)


def backtest_candidates() -> None:
    from matchmind.backtest import polymarket, prematch

    bookmaker, metrics = prematch.run(
        "squad_prematch_candidate_predictions.json",
        "squad_prematch_candidate_selection.json",
        publish=False,
    )
    markets, diagnostic = polymarket.run(
        "squad_inplay_candidate_predictions.parquet", publish=False
    )
    save(
        output() / "squad_candidate_backtest.json",
        {
            "strategies": bookmaker + markets,
            "prematch_metrics": metrics,
            "polymarket_diagnostics": diagnostic,
        },
    )


def main() -> None:
    from matchmind.backtest import squad_fetch, squad_train, squads
    from matchmind.backtest.__main__ import run

    snapshot()
    squad_fetch.fetch()
    if not (root() / "processed/players/_READY").exists():
        raise RuntimeError(
            "W11 mapping not ready; run squad_fetch and squads "
            "separately for club-only preparation"
        )
    squads.build()
    squad_train.main()
    backtest_candidates()
    run(artifact_directory=output() / "w12")


if __name__ == "__main__":
    main()
