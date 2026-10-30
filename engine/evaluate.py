from __future__ import annotations

from functools import lru_cache

from .board import BoardState, Color, opponent
from .eval_config import DEFAULT_EVAL_WEIGHTS, EvalWeights
from .move import Move

WIN_SCORE = 1_000_000

POSITION_VALUES = (
    (20, 30, 45, 45, 30, 20),
    (30, 70, 55, 55, 70, 30),
    (45, 55, 90, 90, 55, 45),
    (45, 55, 90, 90, 55, 45),
    (30, 70, 55, 55, 70, 30),
    (20, 30, 45, 45, 30, 20),
)

# Li Dongxuan, Hu Wei, Wang Jingwen (2022), journal p.124, section 2.2.1.
# The article does not specify how material and this table were scaled.
# The factor 2 and the 50% trial blend are our parameters, not paper claims.
PAPER_POSITION_VALUES = (
    (5, 20, 20, 20, 20, 5),
    (20, 30, 50, 50, 30, 20),
    (20, 50, 40, 40, 50, 20),
    (20, 50, 40, 40, 50, 20),
    (20, 30, 50, 50, 30, 20),
    (5, 20, 20, 20, 20, 5),
)


@lru_cache(maxsize=101)
def blended_position_values(blend: int) -> tuple[tuple[int, ...], ...]:
    blend = max(0, min(100, int(blend)))
    if blend == 0:
        return POSITION_VALUES
    return tuple(tuple((old * (100 - blend) + 2 * new * blend) // 100
                       for old, new in zip(old_row, new_row))
                 for old_row, new_row in zip(POSITION_VALUES, PAPER_POSITION_VALUES))

INNER_RING = {(row, col) for row in (1, 4) for col in range(6)} | {
    (row, col) for col in (1, 4) for row in range(6)
}
OUTER_RING = {(row, col) for row in (2, 3) for col in range(6)} | {
    (row, col) for col in (2, 3) for row in range(6)
}
CENTER = {(2, 2), (2, 3), (3, 2), (3, 3)}


def terminal_score(board: BoardState, ply: int = 0) -> int | None:
    winner = board.winner()
    if winner is None:
        if board.is_terminal():
            return 0
        return None
    if winner == board.side_to_move:
        return WIN_SCORE - ply
    return -WIN_SCORE + ply


def no_capture_terminal_score(board: BoardState, ply: int = 0) -> int:
    """Score the adjudication used when the no-capture limit is reached."""
    black = board.count(Color.BLACK)
    red = board.count(Color.RED)
    if black == red:
        return 0
    winner = Color.BLACK if black > red else Color.RED
    return WIN_SCORE - ply if winner == board.side_to_move else -WIN_SCORE + ply


def evaluate(
    board: BoardState,
    perspective: Color | None = None,
    *,
    repeated: bool = False,
    no_capture_plies: int = 0,
    my_moves: list[Move] | None = None,
    enemy_moves: list[Move] | None = None,
    weights: EvalWeights = DEFAULT_EVAL_WEIGHTS,
) -> int:
    """Return a zero-sum score from ``color``'s point of view.

    Search uses negamax, so swapping the two colors and the side to move must
    negate the evaluation.  The original implementation used separate
    positive and negative coefficients for mirrored features (for example,
    own capture opportunities versus enemy capture threats).  That made the
    leaf score depend on the absolute color and introduced a measurable
    first-player/second-player bias.  Mirrored features are now represented
    as signed differences with the mean of their legacy coefficients.
    """
    color = board.side_to_move if perspective is None else perspective
    enemy = opponent(color)
    attack_boost = min(max(no_capture_plies, 0), 80)
    position_values = blended_position_values(weights.paper_position_blend)

    capture_weight = (weights.capture_opportunity + weights.enemy_capture_threat) // 2
    capture_attack_weight = (
        weights.capture_attack_boost + weights.enemy_capture_attack_boost
    ) // 2
    target_weight = (weights.target_diversity + weights.enemy_target_threat) // 2
    threatened_piece_weight = (
        weights.own_piece_under_threat + weights.enemy_piece_under_threat
    ) // 2

    material = board.count(color) - board.count(enemy)
    score = material * weights.piece_value

    my_moves = board.legal_moves(color) if my_moves is None else my_moves
    enemy_moves = board.legal_moves(enemy) if enemy_moves is None else enemy_moves
    my_captures = [move for move in my_moves if move.is_capture]
    enemy_captures = [move for move in enemy_moves if move.is_capture]

    score += (len(my_moves) - len(enemy_moves)) * weights.mobility
    capture_delta = len(my_captures) - len(enemy_captures)
    score += capture_delta * (capture_weight + attack_boost * capture_attack_weight)

    my_targets = {move.end for move in my_captures}
    enemy_targets = {move.end for move in enemy_captures}
    target_delta = len(my_targets) - len(enemy_targets)
    score += target_delta * (target_weight + attack_boost * weights.target_attack_boost)

    for row in range(6):
        for col in range(6):
            piece = board.cells[row][col]
            if piece == Color.EMPTY:
                continue
            sign = 1 if piece == color else -1
            coord = (row, col)
            score += sign * position_values[row][col]
            if coord in INNER_RING:
                score += sign * weights.inner_ring_control
            if coord in OUTER_RING:
                score += sign * weights.outer_ring_control
            if coord in CENTER:
                score += sign * weights.center_control
            if coord in enemy_targets and piece == color:
                score -= threatened_piece_weight
            if coord in my_targets and piece == enemy:
                score += threatened_piece_weight

    if board.count(color) <= 3 or board.count(enemy) <= 3:
        score += material * weights.endgame_material
        score += (len(my_captures) - len(enemy_captures)) * weights.endgame_capture_delta
    if no_capture_plies >= 40:
        score += (len(my_moves) - len(enemy_moves)) * weights.long_no_capture_mobility
        score += target_delta * weights.long_no_capture_target

    # A repeated position is a draw condition, not an advantage for the side
    # to move.  Search handles repetition as a dedicated terminal condition;
    # omitting an asymmetric leaf penalty keeps this function zero-sum.

    return score
