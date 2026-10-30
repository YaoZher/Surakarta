"""Quick project checks; --with-ui also initializes Pygame without a game loop."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def check_sources() -> dict:
    sources = [ROOT / "main.py", Path(__file__).resolve()]
    for folder in ("engine", "Class", "Func", "networking", "server", "tests"):
        sources.extend(sorted((ROOT / folder).rglob("*.py")))
    for path in sources:
        compile(path.read_bytes(), str(path), "exec")
    print(f"PASS: Python syntax ({len(sources)} files)")

    version = json.loads((ROOT / "VERSION.json").read_text(encoding="utf-8-sig"))
    for field, filename in (
        ("rules_sha256", "rules.py"),
        ("search_sha256", "search.py"),
        ("strategy_sha256", "paper_strategy.py"),
    ):
        actual = hashlib.sha256((ROOT / "engine" / filename).read_bytes()).hexdigest()
        if actual != version[field]:
            raise AssertionError(f"VERSION.json checksum mismatch: engine/{filename}")
    print("PASS: all three VERSION.json source checksums")
    return version


def check_engine(version: dict) -> None:
    from engine.board import BoardState, Color
    from engine.eval_config import get_eval_weights
    from engine.search import Searcher, SearchLimits

    board = BoardState.initial()
    original_rows = board.to_rows()
    moves = board.legal_moves()
    assert len(moves) == len(set(moves)) == 16, "Unexpected initial legal moves"
    assert not board.is_terminal() and board.winner() is None
    for move in moves:
        assert not move.is_capture, "Initial position should have no captures"
        child = board.apply(move)
        assert child.at(move.start) == Color.EMPTY
        assert child.at(move.end) == Color.BLACK
        assert child.side_to_move == Color.RED and child.ply == 1
        assert child.count(Color.BLACK) == child.count(Color.RED) == 12
    assert board.to_rows() == original_rows, "Applying a move changed the input board"
    print("PASS: initial legal moves and state transitions")

    searcher = Searcher(
        eval_weights=get_eval_weights(version["default_settings"]["eval_profile"]),
        paper_opening_ordering=version["paper_opening_ordering"],
    )
    for _ in range(2):
        result = searcher.search(board, SearchLimits(max_depth=2, time_ms=250))
        assert result.move in board.legal_moves(), "AI returned an illegal move"
        board = board.apply(result.move)
    print("PASS: short AI searches return legal moves for both sides")


def check_ui() -> None:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    os.chdir(ROOT)  # The application loads its bundled fonts relative to cwd.
    import pygame

    try:
        import main as app

        game = app.GameManage()
        assert pygame.display.get_init()
        assert game.screen.get_size() == (game.width, game.height)
        assert game.recorder is None, "UI initialization unexpectedly started recording"
    finally:
        pygame.quit()
    assert not pygame.get_init()
    print("PASS: Pygame interface initializes and exits with dummy display/audio")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-ui", action="store_true", help="also check Pygame and fonts")
    args = parser.parse_args()
    version = check_sources()
    check_engine(version)
    if args.with_ui:
        check_ui()
    print("All requested checks passed.")


if __name__ == "__main__":
    main()
