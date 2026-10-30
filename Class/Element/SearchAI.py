import os
from pathlib import Path
from Class.Settings import MAX_TOTAL_CLOCK_MS

from engine import BoardState, Color, TotalClock
from engine.eval_config import get_eval_weights
from engine.opening_book import OpeningBook
from engine.search import SearchLimits, SearchResult, Searcher
from engine.zobrist import hash_board


class SearchAI:
    def __init__(self, chess_color):
        self.chess_color = chess_color
        self.engine_color = self._to_engine_color(chess_color)
        self.is_start = False
        # The formal UI default is the cross-budget control.  Per-colour
        # overrides make role experiments explicit without hard-coding an
        # opponent strategy or changing the legacy constructor API.
        role_name = "BLACK" if self.engine_color == Color.BLACK else "RED"
        role_profile = os.getenv(f"SURAKARTA_{role_name}_EVAL_PROFILE", "")
        self.eval_profile = os.getenv("SURAKARTA_EVAL_PROFILE", role_profile or "baseline")
        book_path = os.getenv("SURAKARTA_OPENING_BOOK", "")
        opening_book = OpeningBook.load(book_path) if book_path and Path(book_path).is_file() else None
        self.searcher = Searcher(
            eval_weights=get_eval_weights(self.eval_profile),
            opening_book=opening_book,
        )
        self.max_depth = self._env_int("SURAKARTA_AI_DEPTH", 5, 1, 12)
        # SURAKARTA_AI_MS remains a useful fixed-budget override for quick UI
        # debugging. Competition mode defaults to one 15-minute clock per AI
        # and has no increment.
        self.time_ms = self._env_int("SURAKARTA_AI_MS", 5_000, 50, 20_000)
        self.total_time_ms = self._env_int("SURAKARTA_TOTAL_TIME_MS", 900_000, 0, MAX_TOTAL_CLOCK_MS)
        self.clock = TotalClock(initial_ms=self.total_time_ms) if self.total_time_ms > 0 else None
        self.last_budget_ms = self.time_ms
        self.time_forfeit = False
        self.last_result: SearchResult | None = None
        self.last_error = ""
        self.used_fallback = False
        # GHI: track full game position hashes for 3‑fold detection
        # (ref: Kishimoto & Müller 2004)
        self._history: list[int] = []
        self._move_count: int = 0
        self._last_observed_counts: tuple[int, int] | None = None
        self._no_capture_plies: int = 0
        self.no_capture_limit = self._env_int("SURAKARTA_NO_CAPTURE_LIMIT", 80, 0, 300)

    def configure(
        self,
        *,
        depth: int,
        time_ms: int,
        total_time_ms: int,
        eval_profile: str,
    ) -> None:
        """Apply settings from the UI and reset per-game search context."""
        self.max_depth = max(1, min(12, int(depth)))
        self.time_ms = max(50, min(20_000, int(time_ms)))
        self.total_time_ms = max(0, min(MAX_TOTAL_CLOCK_MS, int(total_time_ms)))
        self.eval_profile = eval_profile
        self.searcher.eval_weights = get_eval_weights(eval_profile)
        self.reset_game_state()

    def getChessLocs(self, chess_board):
        # Kept for compatibility with the original AI API.
        return None

    def to_engine_board(self, chess_board) -> BoardState:
        rows: list[str] = []
        for row in range(2, 8):
            values: list[str] = []
            for col in range(2, 8):
                color = self._to_engine_color(chess_board.chess_locs[row][col].color)
                if color == Color.BLACK:
                    values.append("B")
                elif color == Color.RED:
                    values.append("R")
                else:
                    values.append(".")
            rows.append("".join(values))
        return BoardState.from_rows(rows, side_to_move=self.engine_color)

    def ai_move(self, chess_board):
        self.last_error = ""
        self.used_fallback = False
        self.time_forfeit = False
        self._move_count += 1
        try:
            board = self.to_engine_board(chess_board)
            legal_moves = board.legal_moves()
        except Exception as error:
            self.last_result = None
            self.last_error = f"board conversion failed: {error}"
            return None, None

        if not legal_moves:
            self.last_result = SearchResult(None, 0, 0, 0, 0.0, False)
            return None, None

        self._sync_observed_position(board)
        full_history = tuple(self._history[:-1])
        recent_hashes = tuple(full_history[-8:])

        budget_ms = self.time_ms
        if self.clock is not None:
            if not self.clock.start_turn(self.engine_color):
                self.time_forfeit = True
                self.last_result = SearchResult(None, 0, 0, 0, 0.0, False)
                self.last_error = "AI total clock expired before search"
                return None, None
            budget_ms = self.clock.allocate_turn_ms(
                self.engine_color,
                expected_remaining_turns=self._estimate_remaining_turns(board),
            )
            budget_ms = min(budget_ms, self.time_ms)
        self.last_budget_ms = budget_ms

        try:
            result = self.searcher.search(
                board,
                SearchLimits(
                    max_depth=self.max_depth,
                    time_ms=budget_ms,
                    recent_hashes=recent_hashes,
                    no_capture_plies=self._no_capture_plies,
                    no_capture_limit=self.no_capture_limit,
                    full_history=full_history,
                    move_count=self._move_count,
                ),
            )
        except Exception as error:
            self.last_result = self._fallback_result(legal_moves[0])
            self.last_error = f"search failed: {error}"
            self.used_fallback = True
        else:
            if result.move not in legal_moves:
                self.last_result = self._fallback_result(legal_moves[0], result)
                self.last_error = "search returned illegal move"
                self.used_fallback = True
            else:
                self.last_result = result
        finally:
            if self.clock is not None:
                self.clock.stop_turn(self.engine_color)

        if self.clock is not None and self.clock.is_expired(self.engine_color):
            self.time_forfeit = True
            self.last_error = "AI total clock expired during search"
            return None, None

        # Record the resulting position hash for 3‑fold detection
        if self.last_result.move is not None and self.last_result.move in legal_moves:
            try:
                child = board.apply(self.last_result.move)
                self._history.append(hash_board(child))
                self._last_observed_counts = (
                    child.count(Color.BLACK),
                    child.count(Color.RED),
                )
                self._no_capture_plies = (
                    0 if self.last_result.move.is_capture else self._no_capture_plies + 1
                )
            except ValueError:
                pass

        start = self.last_result.move.start
        end = self.last_result.move.end
        start_chess = chess_board.chess_locs[start[0] + 2][start[1] + 2]
        end_chess = chess_board.chess_locs[end[0] + 2][end[1] + 2]
        return start_chess, end_chess

    def diagnostics(self) -> dict[str, int | float | bool]:
        result = self.last_result
        remaining_ms = self.clock.remaining_ms(self.engine_color) if self.clock is not None else None
        if result is None:
            return {
                "depth": 0,
                "elapsed_ms": 0.0,
                "nodes": 0,
                "timed_out": False,
                "fallback": self.used_fallback,
                "budget_ms": self.last_budget_ms,
                "remaining_ms": remaining_ms,
                "time_forfeit": self.time_forfeit,
            }
        return {
            "depth": result.depth,
            "elapsed_ms": result.elapsed_ms,
            "nodes": result.nodes,
            "timed_out": result.timed_out,
            "fallback": self.used_fallback,
            "budget_ms": self.last_budget_ms,
            "remaining_ms": remaining_ms,
            "time_forfeit": self.time_forfeit,
        }

    def reset_game_state(self) -> None:
        """Reset the 15+0 clock and repetition context for a new UI game."""
        self._history.clear()
        self._move_count = 0
        self.last_result = None
        self.last_error = ""
        self.used_fallback = False
        self.time_forfeit = False
        self._last_observed_counts = None
        self._no_capture_plies = 0
        if self.total_time_ms > 0:
            self.clock = TotalClock(initial_ms=self.total_time_ms)
        else:
            self.clock = None

    @staticmethod
    def _estimate_remaining_turns(board: BoardState) -> int:
        pieces = board.count(Color.BLACK) + board.count(Color.RED)
        return min(110, max(12, 16 + 3 * pieces))

    def _sync_observed_position(self, board: BoardState) -> None:
        """Add the current UI position before searching.

        The adapter is called only on this colour's turns, so the current
        board is the authoritative observation after the opponent's move.
        Comparing material counts lets the adapter keep the same no-capture
        counter as headless play without changing the legacy UI call sites.
        """
        current_hash = hash_board(board)
        counts = (board.count(Color.BLACK), board.count(Color.RED))
        if not self._history:
            self._history.append(current_hash)
        elif self._history[-1] != current_hash:
            if self._last_observed_counts is not None:
                if counts != self._last_observed_counts:
                    self._no_capture_plies = 0
                else:
                    self._no_capture_plies += 1
            self._history.append(current_hash)
        self._last_observed_counts = counts

    @staticmethod
    def _fallback_result(move, source: SearchResult | None = None) -> SearchResult:
        if source is None:
            return SearchResult(move, 0, 0, 0, 0.0, False)
        return SearchResult(
            move,
            source.score,
            source.depth,
            source.nodes,
            source.elapsed_ms,
            source.timed_out,
            source.tt_hits,
            source.cutoffs,
            source.aspiration_windows,
            source.aspiration_researches,
            source.pvs_searches,
        )

    @staticmethod
    def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(os.getenv(name, str(default)))
        except ValueError:
            value = default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _to_engine_color(color) -> Color:
        rgb = (
            getattr(color, "r", None),
            getattr(color, "g", None),
            getattr(color, "b", None),
        )
        if rgb == (0, 0, 0):
            return Color.BLACK
        if rgb == (255, 0, 0):
            return Color.RED
        if rgb == (255, 255, 255):
            return Color.EMPTY

        text = str(color).lower()
        if "black" in text or text == "b":
            return Color.BLACK
        if "red" in text or text == "r":
            return Color.RED
        return Color.EMPTY
