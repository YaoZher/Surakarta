from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .move import Coord, Move


class Color(IntEnum):
    EMPTY = 0
    BLACK = 1
    RED = 2


def opponent(color: Color) -> Color:
    if color == Color.BLACK:
        return Color.RED
    if color == Color.RED:
        return Color.BLACK
    raise ValueError("empty squares do not have an opponent")


_CHAR_TO_COLOR = {
    ".": Color.EMPTY,
    "0": Color.EMPTY,
    "B": Color.BLACK,
    "R": Color.RED,
}
_COLOR_TO_CHAR = {
    Color.EMPTY: ".",
    Color.BLACK: "B",
    Color.RED: "R",
}


@dataclass(frozen=True, slots=True)
class BoardState:
    cells: tuple[tuple[Color, ...], ...]
    side_to_move: Color = Color.BLACK
    ply: int = 0

    @classmethod
    def initial(cls) -> BoardState:
        return cls.from_rows(
            [
                "BBBBBB",
                "BBBBBB",
                "......",
                "......",
                "RRRRRR",
                "RRRRRR",
            ],
            side_to_move=Color.BLACK,
        )

    @classmethod
    def from_rows(cls, rows: list[str] | tuple[str, ...], side_to_move: Color) -> BoardState:
        if len(rows) != 6:
            raise ValueError("Surakarta board must have exactly 6 rows")
        parsed: list[tuple[Color, ...]] = []
        for row in rows:
            if len(row) != 6:
                raise ValueError("Surakarta board rows must have exactly 6 columns")
            parsed.append(tuple(_CHAR_TO_COLOR[ch] for ch in row))
        if side_to_move not in (Color.BLACK, Color.RED):
            raise ValueError("side_to_move must be BLACK or RED")
        return cls(tuple(parsed), side_to_move)

    def to_rows(self) -> list[str]:
        return ["".join(_COLOR_TO_CHAR[cell] for cell in row) for row in self.cells]

    def at(self, coord: Coord) -> Color:
        row, col = coord
        return self.cells[row][col]

    def count(self, color: Color) -> int:
        return sum(cell == color for row in self.cells for cell in row)

    def legal_moves(self, color: Color | None = None) -> list[Move]:
        from .rules import generate_legal_moves

        return generate_legal_moves(self, self.side_to_move if color is None else color)

    def legal_captures(self, color: Color | None = None) -> list[Move]:
        from .rules import generate_legal_captures

        return generate_legal_captures(self, self.side_to_move if color is None else color)

    def apply(self, move: Move) -> BoardState:
        moving = self.at(move.start)
        if moving != self.side_to_move:
            raise ValueError("move start does not contain the side to move")
        target = self.at(move.end)
        if move.is_capture:
            if target != opponent(moving):
                raise ValueError("capture target must contain an opponent piece")
        elif target != Color.EMPTY:
            raise ValueError("quiet move target must be empty")

        rows = [list(row) for row in self.cells]
        rows[move.start[0]][move.start[1]] = Color.EMPTY
        rows[move.end[0]][move.end[1]] = moving
        return BoardState(tuple(tuple(row) for row in rows), opponent(moving), self.ply + 1)

    def is_terminal(self) -> bool:
        if self.count(Color.BLACK) == 0 or self.count(Color.RED) == 0:
            return True
        return not self.legal_moves(Color.BLACK) and not self.legal_moves(Color.RED)

    def winner(self) -> Color | None:
        black = self.count(Color.BLACK)
        red = self.count(Color.RED)
        if black == 0 and red == 0:
            return None
        if red == 0:
            return Color.BLACK
        if black == 0:
            return Color.RED
        if self.is_terminal():
            if black > red:
                return Color.BLACK
            if red > black:
                return Color.RED
        return None
