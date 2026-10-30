"""Optional opening heuristics inspired by Li, Hu and Wang (2022), pp.124-125.

The article illustrates opening a loop in three own moves, but supplies no
complete move list or blocker formula. The bounded lane measure below is our
testable adaptation, not a transcription of an opening book from the paper.
It only orders legal root moves; it never forces a move or changes legality.
"""
from __future__ import annotations

from functools import lru_cache

from .board import BoardState, Color, opponent
from .move import Move
from .rules import CAPTURE_PATHS

OPENING_OWN_MOVES = 3
MIN_OPENING_PIECES = 20
LANE_ORDER_SCALE = 120
MAX_LANE_ORDER_BONUS = 600

# Derive the same full-arc geometry as the rules engine, retaining blockers
# that revisit the target. Such a path remains blocked by that enemy piece.
_LANES = tuple(
    (1 << (start[0] * 6 + start[1]), 1 << (end[0] * 6 + end[1]),
     tuple(sorted({sum(1 << (r * 6 + c) for r, c in set(path)) for path in paths})))
    for (start, end), paths in sorted(CAPTURE_PATHS.items())
)


@lru_cache(maxsize=4096)
def lane_readiness(cells: tuple[tuple[Color, ...], ...], color: Color) -> int:
    """Count distinct enemy targets reachable after clearing <=2 own blockers.

    A clear route scores 3, one own blocker 2, two own blockers 1. An enemy
    blocker invalidates that route. Each target contributes its best route
    once; counting many equivalent paths must not inflate its value. A blocker
    is not guaranteed to be movable, so this is a sorting heuristic, not a
    tactical proof that the target can be captured in three moves.
    """
    own = enemy = 0
    other = opponent(color)
    for row, values in enumerate(cells):
        for col, piece in enumerate(values):
            bit = 1 << (row * 6 + col)
            if piece == color:
                own |= bit
            elif piece == other:
                enemy |= bit
    targets: dict[int, int] = {}
    for start, end, paths in _LANES:
        if not start & own or not end & enemy:
            continue
        for mask in paths:
            if mask & enemy:
                continue
            blockers = (mask & own).bit_count()
            if blockers <= 2:
                targets[end] = max(targets.get(end, 0), 3 - blockers)
    return sum(targets.values())


def opening_order_bonuses(
    board: BoardState, moves: list[Move], *, own_move_count: int = 0,
) -> dict[Move, int]:
    """Nudge safe opening moves that open our lanes and close the opponent's.

    The UI supplies its own turn count because its board adapter has ply=0.
    Headless games instead carry an actual ply count. Both stop after each
    side's third turn. Reject sparse/reconstructed endgames even with ply=0.
    """
    turn = own_move_count if own_move_count > 0 else board.ply // 2 + 1
    if turn > OPENING_OWN_MOVES or sum(bool(p) for row in board.cells for p in row) < MIN_OPENING_PIECES:
        return {}
    color, enemy = board.side_to_move, opponent(board.side_to_move)
    before = lane_readiness(board.cells, color) - lane_readiness(board.cells, enemy)
    bonuses = {}
    for move in moves:
        if move.is_capture:
            continue
        child = board.apply(move)
        # Do not add strategic incentives when any immediate reply can take
        # a piece. Existing search, capture and recapture ordering handle it.
        if child.legal_captures():
            continue
        after = lane_readiness(child.cells, color) - lane_readiness(child.cells, enemy)
        bonus = max(-MAX_LANE_ORDER_BONUS, min(MAX_LANE_ORDER_BONUS,
                    (after - before) * LANE_ORDER_SCALE))
        if bonus:
            bonuses[move] = bonus
    return bonuses
