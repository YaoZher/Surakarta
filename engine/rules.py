from __future__ import annotations

from functools import lru_cache

from .board import BoardState, Color, opponent
from .move import Coord, Move


QUIET_DIRECTIONS: tuple[Coord, ...] = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


INNER_LOOP: tuple[Coord, ...] = (
    (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1),
    (6, 0), (5, -1),
    (4, 0), (4, 1), (4, 2), (4, 3), (4, 4), (4, 5),
    (5, 6), (6, 5),
    (5, 4), (4, 4), (3, 4), (2, 4), (1, 4), (0, 4),
    (-1, 5), (0, 6),
    (1, 5), (1, 4), (1, 3), (1, 2), (1, 1), (1, 0),
    (0, -1), (-1, 0),
)

OUTER_LOOP: tuple[Coord, ...] = (
    (0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (5, 2),
    (7, 0), (5, -2),
    (3, 0), (3, 1), (3, 2), (3, 3), (3, 4), (3, 5),
    (5, 7), (7, 5),
    (5, 3), (4, 3), (3, 3), (2, 3), (1, 3), (0, 3),
    (-2, 5), (0, 7),
    (2, 5), (2, 4), (2, 3), (2, 2), (2, 1), (2, 0),
    (0, -2), (-2, 0),
)

CAPTURE_LOOPS: tuple[tuple[Coord, ...], ...] = (INNER_LOOP, OUTER_LOOP)
RULE_CACHE_SIZE = 50_000


def in_bounds(coord: Coord) -> bool:
    row, col = coord
    return 0 <= row < 6 and 0 <= col < 6


def _build_capture_paths() -> dict[tuple[Coord, Coord], tuple[tuple[Coord, ...], ...]]:
    paths: dict[tuple[Coord, Coord], set[tuple[Coord, ...]]] = {}
    for loop in CAPTURE_LOOPS:
        starts = [coord for coord in loop if in_bounds(coord)]
        for start in starts:
            indices = [index for index, coord in enumerate(loop) if coord == start]
            for step in (1, -1):
                for start_index in indices:
                    index = start_index
                    passed_arc = False
                    blockers: list[Coord] = []
                    visited = 0
                    while visited < len(loop):
                        index = (index + step) % len(loop)
                        coord = loop[index]
                        visited += 1
                        if not in_bounds(coord):
                            passed_arc = True
                            continue
                        if coord == start:
                            continue
                        if passed_arc:
                            paths.setdefault((start, coord), set()).add(tuple(blockers))
                        blockers.append(coord)
    return {key: tuple(value) for key, value in paths.items()}


CAPTURE_PATHS: dict[tuple[Coord, Coord], tuple[tuple[Coord, ...], ...]] = _build_capture_paths()
CAPTURE_TARGETS: dict[Coord, tuple[Coord, ...]] = {
    start: tuple(sorted(end for source, end in CAPTURE_PATHS if source == start))
    for start in {source for source, _ in CAPTURE_PATHS}
}


# Codex-assisted performance candidate: reuse the exact existing geometry.
# A route can visit a coordinate more than once, so deduplicate blockers
# before converting their bits; arithmetic addition must never carry bits.
CAPTURE_PATH_MASKS: dict[tuple[Coord, Coord], tuple[int, ...]] = {
    key: tuple(sum(1 << (row * 6 + col) for row, col in set(blockers))
               for blockers in paths)
    for key, paths in CAPTURE_PATHS.items()
}


def _occupied_mask(cells: tuple[tuple[Color, ...], ...]) -> int:
    occupied = 0
    for row, values in enumerate(cells):
        for col, piece in enumerate(values):
            if piece != Color.EMPTY:
                occupied |= 1 << (row * 6 + col)
    return occupied


def _has_clear_capture_path(occupied: int, start: Coord, end: Coord) -> bool:
    for blockers in CAPTURE_PATH_MASKS.get((start, end), ()):
        if not occupied & blockers:
            return True
    return False


def generate_legal_moves(board: BoardState, color: Color) -> list[Move]:
    if color not in (Color.BLACK, Color.RED):
        return []
    return list(_cached_legal_moves(board.cells, color))


@lru_cache(maxsize=RULE_CACHE_SIZE)
def _cached_legal_moves(
    cells: tuple[tuple[Color, ...], ...], color: Color
) -> tuple[Move, ...]:
    """Cache the complete move list for a position and side.

    ``BoardState`` is immutable and move legality depends only on ``cells``
    and ``color``.  Keeping the cached result as a tuple prevents callers from
    mutating the shared value while still returning the historical list API.
    This is especially important because evaluation asks for both sides'
    legal moves at most leaves of the search tree.
    """
    board = BoardState(cells, side_to_move=color)
    occupied = _occupied_mask(cells)
    moves: list[Move] = []
    enemy = opponent(color)
    for row in range(6):
        for col in range(6):
            start = (row, col)
            if board.at(start) != color:
                continue
            for d_row, d_col in QUIET_DIRECTIONS:
                end = (row + d_row, col + d_col)
                if in_bounds(end) and board.at(end) == Color.EMPTY:
                    moves.append(Move(start, end, is_capture=False))
            for end in CAPTURE_TARGETS.get(start, ()):
                if board.at(end) == enemy and _has_clear_capture_path(occupied, start, end):
                    moves.append(Move(start, end, is_capture=True))
    return tuple(moves)


def legal_moves_cache_info():
    return _cached_legal_moves.cache_info()


def generate_legal_captures(board: BoardState, color: Color) -> list[Move]:
    if color not in (Color.BLACK, Color.RED):
        return []
    return list(_cached_legal_captures(board.cells, color))


@lru_cache(maxsize=RULE_CACHE_SIZE)
def _cached_legal_captures(cells: tuple[tuple[Color, ...], ...], color: Color) -> tuple[Move, ...]:
    board = BoardState(cells, side_to_move=color)
    occupied = _occupied_mask(cells)
    enemy = opponent(color)
    moves: list[Move] = []
    for row in range(6):
        for col in range(6):
            start = (row, col)
            if board.at(start) != color:
                continue
            for end in CAPTURE_TARGETS.get(start, ()):
                if board.at(end) == enemy and _has_clear_capture_path(occupied, start, end):
                    moves.append(Move(start, end, is_capture=True))
    return tuple(moves)


def capture_cache_info():
    return _cached_legal_captures.cache_info()


def capture_cache_clear() -> None:
    _cached_legal_captures.cache_clear()


def legal_moves_cache_clear() -> None:
    _cached_legal_moves.cache_clear()


def clear_rule_caches() -> None:
    """Clear both bounded move caches between independent benchmark games."""
    legal_moves_cache_clear()
    capture_cache_clear()


def can_capture(board: BoardState, start: Coord, end: Coord) -> bool:
    moving = board.at(start)
    target = board.at(end)
    if moving not in (Color.BLACK, Color.RED) or target != opponent(moving):
        return False
    for blockers in CAPTURE_PATHS.get((start, end), ()):
        if all(board.at(coord) == Color.EMPTY for coord in blockers):
            return True
    return False


def find_capture_route(board: BoardState, start: Coord, end: Coord) -> tuple[Coord, ...] | None:
    """Return one clear loop route, including out-of-board arc control points."""
    moving = board.at(start)
    target = board.at(end)
    if moving not in (Color.BLACK, Color.RED) or target != opponent(moving):
        return None

    for loop in CAPTURE_LOOPS:
        for start_index in (index for index, coord in enumerate(loop) if coord == start):
            for step in (1, -1):
                index = start_index
                route: list[Coord] = [start]
                passed_arc = False
                visited = 0
                while visited < len(loop):
                    index = (index + step) % len(loop)
                    coord = loop[index]
                    route.append(coord)
                    visited += 1
                    if not in_bounds(coord):
                        passed_arc = True
                        continue
                    if coord == end:
                        if passed_arc:
                            return tuple(route)
                        break
                    if coord == start:
                        continue
                    if board.at(coord) != Color.EMPTY:
                        break
    return None


def _loop_path_clear(board: BoardState, loop: tuple[Coord, ...], start: Coord, end: Coord, step: int) -> bool:
    indices = [index for index, coord in enumerate(loop) if coord == start]
    for start_index in indices:
        index = start_index
        passed_arc = False
        visited = 0
        while visited < len(loop):
            index = (index + step) % len(loop)
            coord = loop[index]
            visited += 1
            if not in_bounds(coord):
                passed_arc = True
                continue
            if coord == end:
                if passed_arc:
                    return True
                break
            if coord == start:
                continue
            if board.at(coord) != Color.EMPTY:
                break
    return False
