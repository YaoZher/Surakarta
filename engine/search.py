from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from itertools import islice

from .board import BoardState, Color, opponent
from .eval_config import DEFAULT_EVAL_WEIGHTS, EvalWeights
from .evaluate import WIN_SCORE, evaluate, no_capture_terminal_score, terminal_score
from .move import Move
from .opening_book import OpeningBook
from .paper_strategy import opening_order_bonuses
from .zobrist import hash_board

EXACT = 0
LOWER_BOUND = 1
UPPER_BOUND = 2
INF = 10_000_000

# ── Module‑1: capture‑ordering table (ref: SIA evaluation, Winands 2015/2016) ──
# Pieces on central squares are more valuable capture targets.
POSITION_CAPTURE_BONUS = [
    [0, 0, 0, 0, 0, 0],
    [0, 1, 2, 2, 1, 0],
    [0, 2, 3, 3, 2, 0],
    [0, 2, 3, 3, 2, 0],
    [0, 1, 2, 2, 1, 0],
    [0, 0, 0, 0, 0, 0],
]
POSITION_CAPTURE_SCALE = 50

# ── Module‑3: repetition penalty (ref: Kishimoto & Müller 2004 AAAI) ──
# Must be large enough to override capture scores so the engine never
# "sacrifices" a piece just to repeat positions.
REPETITION_PENALTY = 5_000
RECENT_MOVE_PENALTY = 1_500
BACKTRACK_PENALTY = 3_500

# ── Module‑4: time‑management constants ──
OPENING_PIECE_THRESHOLD = 20
MIDDLEGAME_PIECE_THRESHOLD = 10
OPENING_TIME_FACTOR = 0.6
ENDGAME_TIME_FACTOR = 0.8
MIDDLEGAME_TIME_FACTOR = 1.0
ENDGAME_DEPTH_THRESHOLD = 6
LATE_ENDGAME_DEPTH_THRESHOLD = 4
ENDGAME_DEPTH_BONUS = 2
LATE_ENDGAME_DEPTH_BONUS = 4
ASPIRATION_BASE = 350
ASPIRATION_DEPTH_FACTOR = 50
ASPIRATION_MIN = 200

# ── Move‑ordering weights ──
TT_MOVE_BONUS = 1_000_000
CAPTURE_BONUS = 80_000
KILLER_BONUS = 70_000
WIN_CAPTURE_BONUS = WIN_SCORE
CENTER_SCALE = 18
IMMEDIATE_RECAPTURE_PENALTY = 1_500
THREATENED_PER_TARGET_PENALTY = 200
GENERAL_REPLY_CAPTURE_PENALTY = 120
DEFENSIVE_EXTENSION_LIMIT = 8
HISTORY_DECAY = 0.85
HISTORY_MIN_ABS = 10


@dataclass(frozen=True, slots=True)
class SearchLimits:
    max_depth: int = 4
    time_ms: int = 1_000
    recent_hashes: tuple[int, ...] = ()
    recent_moves: tuple[Move, ...] = ()
    no_capture_plies: int = 0
    no_capture_limit: int = 80
    # GHI fix: complete game position hashes for 3‑fold detection
    # (ref: Kishimoto & Müller 2004)
    full_history: tuple[int, ...] = ()
    move_count: int = 0


@dataclass(slots=True)
class SearchStats:
    nodes: int = 0
    tt_probes: int = 0
    tt_hits: int = 0
    cutoffs: int = 0
    qnodes: int = 0
    completed_depth: int = 0
    tt_stores: int = 0
    tt_replacements: int = 0
    tt_rejected: int = 0
    aspiration_windows: int = 0
    aspiration_researches: int = 0
    pvs_searches: int = 0
    killer_hits: int = 0
    threat_extensions: int = 0


@dataclass(frozen=True, slots=True)
class SearchResult:
    move: Move | None
    score: int
    depth: int
    nodes: int
    elapsed_ms: float
    timed_out: bool
    tt_probes: int = 0
    tt_hits: int = 0
    cutoffs: int = 0
    aspiration_windows: int = 0
    aspiration_researches: int = 0
    pvs_searches: int = 0


@dataclass(frozen=True, slots=True)
class TTEntry:
    depth: int
    score: int
    flag: int
    best_move: Move | None


class SearchTimeout(Exception):
    pass


def _configured_defensive_extension_limit() -> int:
    """Read the experimental defensive-extension cap without changing code."""
    try:
        requested = int(os.getenv("SURAKARTA_DEFENSIVE_EXTENSION_LIMIT", "0"))
    except ValueError:
        requested = 0
    return min(max(requested, 0), DEFENSIVE_EXTENSION_LIMIT)


def _configured_reply_capture_penalty_scale() -> float:
    """c022: configurable scale for reply-capture penalties in move ordering.

    Set SURAKARTA_REPLY_CAPTURE_PENALTY_SCALE to a float in [0.0, 2.0].
    Default 1.0 = c016 baseline.
    """
    try:
        requested = float(os.getenv("SURAKARTA_REPLY_CAPTURE_PENALTY_SCALE", "1.0"))
    except ValueError:
        requested = 1.0
    return min(max(requested, 0.0), 2.0)


@dataclass
class Searcher:
    table: dict[int, TTEntry] = field(default_factory=dict)
    history: dict[Move, int] = field(default_factory=dict)
    stats: SearchStats = field(default_factory=SearchStats)
    killers: dict[int, tuple[Move, ...]] = field(default_factory=dict)
    max_quiescence_depth: int = 8
    table_limit: int = 300_000
    aspiration_delta: int = 350  # kept for compat; runtime value is adaptive now
    eval_weights: EvalWeights = DEFAULT_EVAL_WEIGHTS
    opening_book: OpeningBook | None = None
    # The tactic is symmetric but not yet proven to improve formal 15+0
    # strength, so the competition default is off.  Set the environment
    # variable to 4 or 8 for a reproducible experiment.
    defensive_extension_limit: int = field(
        default_factory=_configured_defensive_extension_limit
    )
    # c022: configurable scale for reply-capture penalties.
    # Default 1.0 = c016 baseline.
    reply_capture_penalty_scale: float = field(
        default_factory=_configured_reply_capture_penalty_scale
    )
    # Optional root sorting only; default off until independent validation.
    paper_opening_ordering: bool = field(default_factory=lambda:
        os.getenv("SURAKARTA_PAPER_OPENING_ORDERING", "0") == "1")
    _tt_context_key: int = field(default=0, init=False, repr=False)
    _root_opening_bonuses: dict[Move, int] = field(default_factory=dict, init=False, repr=False)

    def search(self, board: BoardState, limits: SearchLimits | None = None) -> SearchResult:
        limits = limits or SearchLimits()
        self.stats = SearchStats()
        # TT scores are only valid for the same history and no-capture context.
        # The board hash alone is insufficient because repetition and long-run
        # pressure are part of the search state even though they are not board
        # cells.  Hash the immutable context once per root search; the per-node
        # key below adds the capped no-capture counter.
        self._tt_context_key = hash((
            limits.full_history,
            frozenset(limits.recent_hashes),
            limits.no_capture_limit,
            self.eval_weights,
            self.max_quiescence_depth,
            self.defensive_extension_limit,
            self.reply_capture_penalty_scale,
        ))

        # ── Module‑2: age history table (ref: SIA search enhancements) ──
        self._decay_history()

        # ── Module‑2: reset killer table each search ──
        self.killers = {}

        start_time = time.perf_counter()

        # ── Module‑4: time allocation by game phase (ref: SIA 5s/move experiments) ──
        effective_ms = self._time_budget(board, limits)

        deadline = start_time + max(effective_ms, 1) / 1000.0

        legal_moves = board.legal_moves()
        self._root_opening_bonuses = (opening_order_bonuses(
            board, legal_moves, own_move_count=limits.move_count,
        ) if self.paper_opening_ordering else {})
        if not legal_moves:
            terminal = terminal_score(board)
            score = terminal if terminal is not None else self._evaluate(
                board,
                limits.no_capture_plies,
                limits.recent_hashes,
            )
            return SearchResult(None, score, 0, 0, 0.0, False)

        ordered = self._order_moves(board, legal_moves, None, depth=1, recent_moves=limits.recent_moves,
                                    opening_bonuses=self._root_opening_bonuses)
        best_move = ordered[0]
        best_score = -INF
        completed_depth = 0
        timed_out = False

        max_depth = max(limits.max_depth, 1) + self._endgame_depth_bonus(board)
        for depth in range(1, max_depth + 1):
            try:
                if completed_depth > 0:
                    self.stats.aspiration_windows += 1
                    # ── Module‑4: adaptive aspiration window ──
                    delta = max(ASPIRATION_MIN, ASPIRATION_BASE + depth * ASPIRATION_DEPTH_FACTOR)
                    alpha = best_score - delta
                    beta = best_score + delta
                    score, move = self._root_search(board, depth, deadline, limits, alpha, beta)
                    if score <= alpha or score >= beta:
                        self.stats.aspiration_researches += 1
                        score, move = self._root_search(board, depth, deadline, limits, -INF, INF)
                else:
                    score, move = self._root_search(board, depth, deadline, limits, -INF, INF)
                if move is not None:
                    best_score = score
                    best_move = move
                    completed_depth = depth
                    self.stats.completed_depth = depth
            except SearchTimeout:
                timed_out = True
                break

        if completed_depth == 0:
            completed_depth = 1
            best_score = self._evaluate(board, limits.no_capture_plies, limits.recent_hashes)

        elapsed = (time.perf_counter() - start_time) * 1000.0
        return SearchResult(
            best_move,
            best_score,
            completed_depth,
            self.stats.nodes,
            elapsed,
            timed_out,
            self.stats.tt_probes,
            self.stats.tt_hits,
            self.stats.cutoffs,
            self.stats.aspiration_windows,
            self.stats.aspiration_researches,
            self.stats.pvs_searches,
        )

    @staticmethod
    def _endgame_depth_bonus(board: BoardState) -> int:
        """Spend available time on extra quiet depth in small endgames."""
        pieces = board.count(Color.BLACK) + board.count(Color.RED)
        if pieces <= LATE_ENDGAME_DEPTH_THRESHOLD:
            return LATE_ENDGAME_DEPTH_BONUS
        if pieces <= ENDGAME_DEPTH_THRESHOLD:
            return ENDGAME_DEPTH_BONUS
        return 0

    # ─────────────────────────────────────────────────────────────
    #  Module‑4: time budget
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _time_budget(board: BoardState, limits: SearchLimits) -> float:
        # Only apply phase‑based allocation when the budget is generous
        # enough.  Small budgets (tests, speed runs) keep the full amount.
        if limits.time_ms < 800:
            return float(limits.time_ms)
        pieces = board.count(Color.BLACK) + board.count(Color.RED)
        if pieces > OPENING_PIECE_THRESHOLD:
            factor = OPENING_TIME_FACTOR
        elif pieces > MIDDLEGAME_PIECE_THRESHOLD:
            factor = MIDDLEGAME_TIME_FACTOR
        else:
            factor = ENDGAME_TIME_FACTOR
        return limits.time_ms * factor

    # ─────────────────────────────────────────────────────────────
    #  Module‑2: history decay
    # ─────────────────────────────────────────────────────────────

    def _decay_history(self) -> None:
        for key in list(self.history.keys()):
            val = int(self.history[key] * HISTORY_DECAY)
            if abs(val) < HISTORY_MIN_ABS:
                del self.history[key]
            else:
                self.history[key] = val

    # ─────────────────────────────────────────────────────────────
    #  Module‑1: threatened‑piece detection
    #  (ref: Quiescent Search lecture, Academia Sinica 2023)
    # ─────────────────────────────────────────────────────────────

    def _has_threatened_piece(self, board: BoardState) -> bool:
        """Return True when any piece of the side‑to‑move is under threat of capture."""
        enemy = opponent(board.side_to_move)
        return len(board.legal_captures(enemy)) > 0

    # ─────────────────────────────────────────────────────────────
    #  Root search (with PVS)
    # ─────────────────────────────────────────────────────────────

    def _tt_key(
        self,
        board: BoardState,
        no_capture_plies: int,
        path_history: tuple[int, ...] = (),
    ) -> int:
        """Build a TT key for all state that can affect a returned score.

        Repetition is path-dependent.  Including the exact ancestor sequence
        prevents a score from a non-repeating path being reused on a path that
        is one move away from a threefold draw.  The default empty sequence
        keeps the small public helper/tests backward compatible.
        """
        no_capture_count = max(no_capture_plies, 0)
        return hash((hash_board(board), no_capture_count, self._tt_context_key, path_history))

    def _root_search(
        self,
        board: BoardState,
        depth: int,
        deadline: float,
        limits: SearchLimits,
        alpha: int = -INF,
        beta: int = INF,
    ) -> tuple[int, Move | None]:
        best_score = -INF
        best_move: Move | None = None
        key = self._tt_key(board, limits.no_capture_plies)
        tt_move = self.table.get(key).best_move if key in self.table else None
        alpha_original = alpha

        recent_hashes = set(limits.recent_hashes)
        path_history = (hash_board(board),)
        searched = 0
        for move in self._order_moves(
            board,
            board.legal_moves(),
            tt_move,
            depth,
            recent_moves=limits.recent_moves,
            ply=0,
            opening_bonuses=self._root_opening_bonuses,
        ):
            self._check_time(deadline)
            child = board.apply(move)
            child_hash = hash_board(child)
            child_no_capture = 0 if move.is_capture else limits.no_capture_plies + 1
            if searched == 0:
                score = -self._negamax(
                    child, depth - 1, -beta, -alpha, 1, deadline,
                    child_no_capture, recent_hashes, path_history,
                    limits,
                )
            else:
                self.stats.pvs_searches += 1
                score = -self._negamax(
                    child, depth - 1, -alpha - 1, -alpha, 1, deadline,
                    child_no_capture, recent_hashes, path_history,
                    limits,
                )
                if alpha < score < beta:
                    score = -self._negamax(
                        child, depth - 1, -beta, -score, 1, deadline,
                        child_no_capture, recent_hashes, path_history,
                        limits,
                    )
            # ── Module‑3: penalise returning to a recent position ──
            if child_hash in recent_hashes:
                score -= REPETITION_PENALTY
            if score > best_score:
                best_score = score
                best_move = move
            if score > alpha:
                alpha = score
            if alpha >= beta:
                # The aspiration caller will re-search with a full window.
                # Do not spend the remaining root budget proving a bound that
                # is already sufficient to trigger that re-search.
                self.stats.cutoffs += 1
                break
            searched += 1

        flag = EXACT
        if best_score <= alpha_original:
            flag = UPPER_BOUND
        elif best_score >= beta:
            flag = LOWER_BOUND
        self._store(key, TTEntry(depth, best_score, flag, best_move))
        return best_score, best_move

    # ─────────────────────────────────────────────────────────────
    #  Negamax (with GHI‑safe repetition detection)
    #  (ref: Kishimoto & Müller 2004)
    # ─────────────────────────────────────────────────────────────

    def _negamax(
        self,
        board: BoardState,
        depth: int,
        alpha: int,
        beta: int,
        ply: int,
        deadline: float,
        no_capture_plies: int,
        recent_hashes: set[int],
        path_history: tuple[int, ...],
        limits: SearchLimits,
    ) -> int:
        self._check_time(deadline)
        self.stats.nodes += 1

        terminal = terminal_score(board, ply)
        if terminal is not None:
            return terminal

        if limits.no_capture_limit > 0 and no_capture_plies >= limits.no_capture_limit:
            return no_capture_terminal_score(board, ply)

        board_hash = hash_board(board)
        key = self._tt_key(board, no_capture_plies, path_history)

        # ── Module‑3: 3‑fold repetition via full game history ──
        full_count = sum(1 for h in limits.full_history if h == board_hash)
        in_path = path_history.count(board_hash)
        if full_count + in_path >= 2:
            # A real threefold repetition is a draw.  Move ordering and the
            # recent-position heuristic handle cycle avoidance separately.
            return 0

        # ── Module‑3: immediate revisit penalty (kept for path‑local detection) ──
        # This function returns a score from the current side-to-move's
        # perspective. A child that repeats a recent position is bad for the
        # player who just made the move, so the child must receive a positive
        # score here; negamax then turns it into a negative parent score.
        if board_hash in recent_hashes:
            return REPETITION_PENALTY - ply

        if depth <= 0:
            return self._quiescence(
                board, alpha, beta, ply, deadline, 0,
                no_capture_plies, recent_hashes, limits.no_capture_limit,
            )

        entry = self.table.get(key)
        self.stats.tt_probes += 1
        alpha_original = alpha
        tt_move = entry.best_move if entry else None
        if entry and entry.depth >= depth:
            self.stats.tt_hits += 1
            if entry.flag == EXACT:
                return entry.score
            if entry.flag == LOWER_BOUND:
                alpha = max(alpha, entry.score)
            elif entry.flag == UPPER_BOUND:
                beta = min(beta, entry.score)
            if alpha >= beta:
                return entry.score

        best_score = -INF
        best_move: Move | None = None
        moves = board.legal_moves()
        if not moves:
            return evaluate(board, weights=self.eval_weights)

        searched = 0
        for move in self._order_moves(
            board, moves, tt_move, depth, recent_moves=limits.recent_moves, ply=ply,
        ):
            child = board.apply(move)
            child_no_capture = 0 if move.is_capture else no_capture_plies + 1
            if searched == 0:
                score = -self._negamax(
                    child, depth - 1, -beta, -alpha, ply + 1, deadline,
                    child_no_capture, recent_hashes, path_history + (board_hash,),
                    limits,
                )
            else:
                self.stats.pvs_searches += 1
                score = -self._negamax(
                    child, depth - 1, -alpha - 1, -alpha, ply + 1, deadline,
                    child_no_capture, recent_hashes, path_history + (board_hash,),
                    limits,
                )
                if alpha < score < beta:
                    score = -self._negamax(
                        child, depth - 1, -beta, -score, ply + 1, deadline,
                        child_no_capture, recent_hashes, path_history + (board_hash,),
                        limits,
                    )
            if score > best_score:
                best_score = score
                best_move = move
            if score > alpha:
                alpha = score
            if alpha >= beta:
                self.stats.cutoffs += 1
                self.history[move] = self.history.get(move, 0) + depth * depth
                self._record_killer(ply, move)
                break
            searched += 1

        flag = EXACT
        if best_score <= alpha_original:
            flag = UPPER_BOUND
        elif best_score >= beta:
            flag = LOWER_BOUND
        self._store(key, TTEntry(depth, best_score, flag, best_move))
        return best_score

    # ─────────────────────────────────────────────────────────────
    #  Module‑1: quiescence with threat detection
    #  (ref: Quiescent Search lecture, Academia Sinica 2023)
    # ─────────────────────────────────────────────────────────────

    def _quiescence(
        self,
        board: BoardState,
        alpha: int,
        beta: int,
        ply: int,
        deadline: float,
        qdepth: int,
        no_capture_plies: int,
        recent_hashes: set[int],
        no_capture_limit: int = 80,
    ) -> int:
        self._check_time(deadline)
        self.stats.qnodes += 1

        # ── Module‑1.3: don't truncate at terminal_score when captures remain ──
        terminal = terminal_score(board, ply)
        if terminal is not None:
            captures = board.legal_captures()
            if not captures:
                return terminal

        if no_capture_limit > 0 and no_capture_plies >= no_capture_limit:
            return no_capture_terminal_score(board, ply)

        enemy_captures = board.legal_captures(opponent(board.side_to_move))
        under_threat = bool(enemy_captures)

        stand_pat = self._evaluate(board, no_capture_plies, recent_hashes)

        # ── Module‑1.1: threatened‑piece check ──
        # A capture threat is not a compulsory check. Keep the existing
        # stand-pat approximation, but resolve fail-high before raising alpha.
        if stand_pat >= beta:
            return beta
        alpha = max(alpha, stand_pat)
        if qdepth >= self.max_quiescence_depth:
            return alpha

        captures = board.legal_captures()
        tactical_moves = list(captures)
        if under_threat and not captures and self.defensive_extension_limit > 0:
            defensive_moves = self._defensive_extension_moves(
                board,
                enemy_captures,
                limit=self.defensive_extension_limit,
            )
            if defensive_moves:
                self.stats.threat_extensions += len(defensive_moves)
                tactical_moves.extend(defensive_moves)

        for move in self._order_moves(board, tactical_moves, None, depth=1, ply=ply):
            child = board.apply(move)
            score = -self._quiescence(
                child, -beta, -alpha, ply + 1, deadline,
                qdepth + 1,
                0 if move.is_capture else no_capture_plies + 1,
                recent_hashes,
                no_capture_limit,
            )
            if score >= beta:
                self.stats.threat_extensions += 1
                return beta
            if score > alpha:
                alpha = score
        return alpha

    def _defensive_extension_moves(
        self,
        board: BoardState,
        enemy_captures: list[Move],
        *,
        limit: int = DEFENSIVE_EXTENSION_LIMIT,
    ) -> list[Move]:
        """Return a bounded set of quiet moves that reduce immediate threats."""
        threatened_targets = {move.end for move in enemy_captures}
        candidates: list[tuple[tuple[int, int, str], Move]] = []
        for move in board.legal_moves():
            if move.is_capture:
                continue
            child = board.apply(move)
            replies = child.legal_captures()
            still_targeted = any(reply.end == move.end for reply in replies)
            reduces_threat = len(replies) < len(enemy_captures)
            moves_threatened_piece = move.start in threatened_targets
            if not (reduces_threat or moves_threatened_piece or not replies):
                continue
            # Prefer removing the original target, then reducing the total
            # number of replies.  A move that is still immediately capturable
            # remains a last-resort defensive extension, never a top choice.
            key = (
                1 if still_targeted else 0,
                len(replies),
                move.uci(),
            )
            candidates.append((key, move))
        candidates.sort(key=lambda item: item[0])
        bounded_limit = min(max(limit, 0), DEFENSIVE_EXTENSION_LIMIT)
        return [move for _, move in candidates[:bounded_limit]]

    # ─────────────────────────────────────────────────────────────
    #  Module‑2: move ordering
    #  (ref: SIA, Winands 2015/2016; PVS paper, 2023)
    # ─────────────────────────────────────────────────────────────

    def _order_moves(
        self,
        board: BoardState,
        moves: list[Move],
        tt_move: Move | None,
        depth: int,
        recent_moves: tuple[Move, ...] = (),
        ply: int | None = None,
        opening_bonuses: dict[Move, int] | None = None,
    ) -> list[Move]:
        """Sort moves by estimated quality.

        ``ply``, when provided, is used for killer‑move lookup instead of
        ``depth``, fixing the ply‑vs‑depth mismatch in internal nodes.
        ``depth`` is also used as a tie‑breaker so deeper searches prefer
        moves that were good at similar remaining depths.

        Each child board is created once via ``board.apply()`` and reply
        captures are checked there — the same approach as the original code
        that achieved 100‑0 wins vs greedy.  ``legal_captures()`` results
        are LRU‑cached, making iterative deepening re‑visits fast.
        """
        killer_key = ply if ply is not None else depth
        return sorted(
            moves,
            key=lambda m: self._move_score(
                board, m, tt_move, killer_key, recent_moves, depth,
            ) + (opening_bonuses.get(m, 0) if opening_bonuses else 0),
            reverse=True,
        )

    def _move_score(
        self,
        board: BoardState,
        move: Move,
        tt_move: Move | None,
        killer_key: int,
        recent_moves: tuple[Move, ...],
        depth_tiebreaker: int = 1,
    ) -> int:
        score = self.history.get(move, 0)

        if move == tt_move:
            score += TT_MOVE_BONUS

        if self.opening_book is not None:
            score += self.opening_book.bonus(board, move)

        if move in self.killers.get(killer_key, ()):
            score += KILLER_BONUS
            self.stats.killer_hits += 1

        # ── Module‑3: cycle detection (2‑step + 3‑step) ──
        if self._is_cycle(move, recent_moves):
            score -= BACKTRACK_PENALTY
        elif any(move == recent for recent in recent_moves):
            score -= RECENT_MOVE_PENALTY

        # ── Create child board once for reply‑capture checks ──
        try:
            child = board.apply(move)
        except ValueError:
            return int(score - 1_000_000)

        if move.is_capture:
            score += CAPTURE_BONUS
            # ── Module‑1.2: position‑based capture bonus (SIA) ──
            end_row, end_col = move.end
            score += POSITION_CAPTURE_BONUS[end_row][end_col] * POSITION_CAPTURE_SCALE

            moving = board.side_to_move
            if child.winner() == moving:
                score += WIN_CAPTURE_BONUS
        else:
            row, col = move.end
            score += (3 - abs(2.5 - row)) * CENTER_SCALE
            score += (3 - abs(2.5 - col)) * CENTER_SCALE

        # ── Reply‑capture detection (on child board) ──
        # ``child.legal_captures()`` is LRU‑cached; iterative deepening
        # visits hit the cache making this fast on the second pass.
        reply_captures = child.legal_captures()
        threatened_targets = len({rc.end for rc in reply_captures})
        score -= int(threatened_targets * THREATENED_PER_TARGET_PENALTY * self.reply_capture_penalty_scale)  # c022
        if any(rc.end == move.end for rc in reply_captures):
            score -= int(IMMEDIATE_RECAPTURE_PENALTY * self.reply_capture_penalty_scale)  # c022
        if reply_captures:
            score -= int(GENERAL_REPLY_CAPTURE_PENALTY * self.reply_capture_penalty_scale)  # c022

        score += depth_tiebreaker
        return int(score)

    # ─────────────────────────────────────────────────────────────
    #  Module‑2: killer‑move recording
    # ─────────────────────────────────────────────────────────────

    def _record_killer(self, ply: int, move: Move) -> None:
        if move.is_capture:
            return
        current = self.killers.get(ply, ())
        updated = (move,) + tuple(existing for existing in current if existing != move)
        self.killers[ply] = updated[:2]

    # ─────────────────────────────────────────────────────────────
    #  Module‑3: cycle detection (2‑step backtrack + 3‑step cycle)
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _is_cycle(move: Move, recent_moves: tuple[Move, ...]) -> bool:
        """Detect A→B→A (2‑step) and A→B→C→A (3‑step) cycles."""
        # 2‑step backtrack: A→B, B→A
        for recent in recent_moves:
            if move.start == recent.end and move.end == recent.start:
                return True
        # 3‑step cycle: A→B, B→C, C→A
        for recent in recent_moves:
            if recent.start == move.end:  # B→C found
                for other in recent_moves:
                    if other.start == recent.end and other.end == move.start:  # C→A found
                        return True
        return False

    # ─────────────────────────────────────────────────────────────
    #  Evaluation wrapper
    # ─────────────────────────────────────────────────────────────

    def _evaluate(
        self,
        board: BoardState,
        no_capture_plies: int,
        recent_hashes: tuple[int, ...] | set[int],
    ) -> int:
        my_moves = board.legal_moves()
        enemy_moves = board.legal_moves(opponent(board.side_to_move))
        return evaluate(
            board,
            repeated=hash_board(board) in recent_hashes,
            no_capture_plies=no_capture_plies,
            my_moves=my_moves,
            enemy_moves=enemy_moves,
            weights=self.eval_weights,
        )

    # ─────────────────────────────────────────────────────────────
    #  Transposition table
    # ─────────────────────────────────────────────────────────────

    def _store(self, key: int, entry: TTEntry) -> None:
        self.stats.tt_stores += 1
        if self.table_limit <= 0:
            self.stats.tt_rejected += 1
            return
        existing = self.table.get(key)
        if existing is not None:
            if existing.depth > entry.depth:
                self.stats.tt_rejected += 1
                return
            self.stats.tt_replacements += 1
            self.table[key] = entry
            return
        if len(self.table) >= self.table_limit:
            # Sample old entries rather than scanning up to 300,000 keys.
            victim_key = min(islice(self.table, 8), key=lambda item: self.table[item].depth)
            self.table.pop(victim_key)
            self.stats.tt_replacements += 1
        self.table[key] = entry

    @staticmethod
    def _check_time(deadline: float) -> None:
        if time.perf_counter() >= deadline:
            raise SearchTimeout


def select_move(board: BoardState, limits: SearchLimits | None = None) -> SearchResult:
    return Searcher().search(board, limits)
