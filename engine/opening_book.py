from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .board import BoardState, Color, opponent
from .move import Move
from .zobrist import hash_board


BOOK_MOVE_BONUS = 2_000_000


@dataclass(frozen=True, slots=True)
class OpeningBookLine:
    moves: tuple[str, ...]
    visits: int = 1
    score: int = 0


@dataclass(slots=True)
class OpeningBook:
    entries: dict[int, dict[str, int]] = field(default_factory=dict)

    @classmethod
    def from_lines(
        cls,
        lines: list[list[str]] | tuple[tuple[str, ...], ...],
        *,
        min_plies: int = 4,
        max_plies: int = 8,
    ) -> OpeningBook:
        book = cls()
        for line in lines:
            if not min_plies <= len(line) <= max_plies:
                continue
            board = BoardState.initial()
            for ply, move_text in enumerate(line):
                move = find_legal_move(board, move_text)
                if move is None:
                    break
                remaining_depth = max_plies - ply
                book.add(board, move, priority=BOOK_MOVE_BONUS + remaining_depth)
                board = board.apply(move)
        return book

    @classmethod
    def load(cls, path: str | Path) -> OpeningBook:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        lines = [line["moves"] for line in payload.get("lines", [])]
        metadata = payload.get("metadata", {})
        return cls.from_lines(
            lines,
            min_plies=int(metadata.get("min_plies", 4)),
            max_plies=int(metadata.get("max_plies", 8)),
        )

    def add(self, board: BoardState, move: Move, *, priority: int = BOOK_MOVE_BONUS) -> None:
        choices = self.entries.setdefault(hash_board(board), {})
        choices[move.uci()] = max(priority, choices.get(move.uci(), 0))

    def bonus(self, board: BoardState, move: Move) -> int:
        return self.entries.get(hash_board(board), {}).get(move.uci(), 0)


def find_legal_move(board: BoardState, move_text: str) -> Move | None:
    for move in board.legal_moves():
        if move.uci() == move_text:
            return move
    return None


def is_stable_candidate(board: BoardState, move: Move) -> bool:
    if move not in board.legal_moves():
        return False
    moving = board.side_to_move
    before_material = board.count(moving) - board.count(opponent(moving))
    child = board.apply(move)
    after_material = child.count(moving) - child.count(opponent(moving))
    if after_material < before_material:
        return False
    return not any(reply.end == move.end for reply in child.legal_captures())


def line_is_stable(moves: list[Move], *, max_material_gap: int = 0) -> bool:
    board = BoardState.initial()
    for move in moves:
        if not is_stable_candidate(board, move):
            return False
        board = board.apply(move)
    return abs(board.count(Color.BLACK) - board.count(Color.RED)) <= max_material_gap
