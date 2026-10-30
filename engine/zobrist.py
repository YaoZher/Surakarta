from __future__ import annotations

import random

from .board import BoardState, Color

_RNG = random.Random(20260709)
_PIECE_KEYS = {
    Color.BLACK: [[_RNG.getrandbits(64) for _ in range(6)] for _ in range(6)],
    Color.RED: [[_RNG.getrandbits(64) for _ in range(6)] for _ in range(6)],
}
_SIDE_KEY = _RNG.getrandbits(64)


def hash_board(board: BoardState) -> int:
    key = 0
    for row in range(6):
        for col in range(6):
            piece = board.cells[row][col]
            if piece in (Color.BLACK, Color.RED):
                key ^= _PIECE_KEYS[piece][row][col]
    if board.side_to_move == Color.RED:
        key ^= _SIDE_KEY
    return key
