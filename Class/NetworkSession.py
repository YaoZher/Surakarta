"""Bridge the authoritative network room to the existing Pygame interface.

Only this main-thread adapter changes the visible board. Socket workers never
touch Pygame, and clicking a destination never applies an unconfirmed move.
"""
from __future__ import annotations

import queue
import re
import socket
import threading

import pygame

from Class.Globals import Globals
from Class.Assembly.ChessManual import ChessManual
from Class.Element.NetworkPanel import NetworkPanel
from Class.MatchRecord import GameRecorder
from engine.board import BoardState, Color
from networking.client import NetworkClient
from networking.server import EmbeddedServer


REASONS = {
    "resign": "认输", "resigned": "认输", "leave": "离开房间",
    "left": "离开房间", "disconnect": "断线超时",
    "disconnect_timeout": "断线超时", "abandoned": "双方离线",
    "no_legal_moves": "无合法走法", "no_moves": "无合法走法",
    "no_pieces": "棋子耗尽", "capture": "棋子耗尽",
    "elimination": "棋子耗尽", "threefold": "三次重复",
    "repetition": "三次重复", "no_capture": "连续80手未吃子",
    "threefold_repetition": "三次重复", "no_capture_80": "连续80手未吃子",
    "idle_timeout": "房间超时",
}


def validate_snapshot(state: dict) -> BoardState:
    """Validate display data before changing any UI or local match record."""
    if state.get("version") != 1 or state.get("status") not in ("waiting", "playing", "finished"):
        raise ValueError("unsupported state")
    if type(state.get("revision")) is not int or state["revision"] < 0:
        raise ValueError("invalid revision")
    rows = state.get("board")
    if not isinstance(rows, list) or len(rows) != 6 or any(
        not isinstance(row, str) or re.fullmatch(r"[BR.]{6}", row) is None for row in rows
    ):
        raise ValueError("invalid board")
    turn = state.get("turn")
    if turn not in ("black", "red"):
        raise ValueError("invalid turn")
    players = state.get("players")
    if not isinstance(players, dict):
        raise ValueError("invalid players")
    for color in ("black", "red"):
        player = players.get(color)
        if player is None and color == "red" and state.get("ply") == 0:
            continue
        if not isinstance(player, dict) or not isinstance(player.get("name"), str):
            raise ValueError("invalid player")
        if len(player["name"]) > 20 or any(ord(ch) < 32 for ch in player["name"]):
            raise ValueError("invalid name")
        if type(player.get("connected")) is not bool or type(player.get("ready")) is not bool:
            raise ValueError("invalid presence")
    moves = state.get("moves")
    if not isinstance(moves, list) or len(moves) > 4096 or state.get("ply") != len(moves):
        raise ValueError("invalid history")
    for move in moves:
        if not isinstance(move, dict) or not isinstance(move.get("text"), str):
            raise ValueError("invalid move record")
        if not re.fullmatch(r"[BR][1-6][A-F]-[1-6][A-F]", move["text"]):
            raise ValueError("invalid move record")
    result = state.get("result")
    if state["status"] == "finished":
        if not isinstance(result, dict) or result.get("winner") not in (None, "black", "red"):
            raise ValueError("invalid result")
        if not isinstance(result.get("reason"), str):
            raise ValueError("invalid result")
    return BoardState.from_rows(rows, side_to_move=Color.BLACK if turn == "black" else Color.RED)


class NetworkSession:
    def __init__(self, game):
        self.game = game
        self.panel = NetworkPanel()
        self.client = None
        self.server = None
        self.state = None
        self.starting = False
        self.pending_move = False
        self.address = ""
        self.mode = ""
        self.connection_status = ""
        self._generation = 0
        self._startup_events = queue.Queue()
        self._startup_lock = threading.Lock()
        self._board_initialized = False
        self._recorded_moves = 0
        self._result_recorded = False
        self._local_controls = None
        self._record_warning = ""

    @property
    def active(self):
        return self.starting or self.client is not None

    @property
    def record_settings(self):
        return {"mode": self.mode, "room": self.client.room if self.client else "",
                "rules": "surakarta-room-v1", "move_clock": "unlimited"}

    def _set_message(self, message):
        self.panel.message = message + ("；" + self._record_warning if self._record_warning else "")
        self.game.user_panel.updateState(self.game.screen, (self._record_warning or message)[:18])

    def _panel_session(self):
        client = self.client
        status = self.connection_status
        if client is not None and client.connected and self.state is not None:
            status = self.state["status"]
        self.panel.set_session(
            room=client.room if client else "", color=client.color if client else "",
            status=status, address=self.address, active=self.active,
        )

    def open(self):
        message = self.panel.message
        self.panel.open(active=self.active)
        self._panel_session()
        if self.active:
            self.panel.message = message

    def handle_event(self, event):
        if self.game.settings_panel.visible and not self.active:
            return False
        if self.panel.visible:
            action = self.panel.handle_event(event)
            if action:
                self.perform(action)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, "button", 1) == 1:
            menu_index = self.game.menu.mouseClick(event.pos)
            if menu_index == 5:
                self.open()
                return True
            if self.active:
                if menu_index == 2:
                    self.game.export_record()
                elif menu_index == 3:
                    self.game._save_record("exit")
                    self.shutdown()
                    pygame.quit()
                    raise SystemExit
                elif self.game.chess_board.rect.collidepoint(event.pos):
                    self._click_board(event.pos)
                return True
        # Do not let local controls or hover styling change an online session.
        return self.active

    def perform(self, action):
        command = action["action"]
        if command == "close":
            self.panel.visible = False
            self.redraw()
        elif command == "host" and not self.active:
            self._host(action["name"], action["port"])
        elif command == "connect" and not self.active:
            self.mode = "online" if action["url"].startswith("wss://") or self.panel.mode == "online" else "lan"
            self.address = action["url"]
            self._connect(action["url"], action["name"], action["mode"], action.get("room", ""))
        elif command == "leave":
            if not self._board_initialized:
                self._cancel_initial_connection("已取消连接，可修改信息后重试")
                return
            self.game._save_record("exit")
            self.shutdown()
            Globals.reset()
            self.game.__init__()
        elif command == "reconnect" and self.client:
            self.pending_move = False
            if self.client.reconnect():
                self.connection_status = "connecting"
                self._set_message("正在重新连接…")
            self._panel_session()
        elif command in ("ready", "resign") and self.client:
            if self.client.send(command):
                self._set_message("已发送，等待确认")

    def _host(self, name, port):
        self.starting = True
        self.connection_status = "connecting"
        self.mode = "lan"
        self._generation += 1
        generation = self._generation
        self._set_message("正在创建局域网房间…")
        self._panel_session()
        self._lock_controls()

        def start():
            server = EmbeddedServer(host="0.0.0.0", port=port)
            try:
                server.start()
                try:
                    addresses = socket.gethostbyname_ex(socket.gethostname())[2]
                    ip = next((value for value in addresses if not value.startswith("127.")), "127.0.0.1")
                except OSError:
                    ip = "127.0.0.1"
                with self._startup_lock:
                    cancelled = generation != self._generation
                    if not cancelled:
                        self._startup_events.put((generation, server, f"ws://{ip}:{server.port}", name))
                if cancelled:
                    server.stop()
            except Exception:
                try:
                    server.stop()
                except Exception:
                    pass
                self._startup_events.put((generation, None, "端口不可用，请换端口后重试", name))

        threading.Thread(target=start, name="surakarta-lan-start", daemon=True).start()

    def _connect(self, url, name, mode, room=""):
        try:
            self.client = NetworkClient(url, name=name)
            self.connection_status = "connecting"
            if self.client.start(mode=mode, room=room):
                self._set_message("正在连接房间…")
            else:
                errors = self.client.poll()
                message = next((event["message"] for event in errors if event.get("type") == "error"), "连接失败，请检查后重试")
                self._cancel_initial_connection(message)
                return
        except (ValueError, OSError):
            self._cancel_initial_connection("地址无效，请检查后重试")
            return
        self._panel_session()
        if self.active:
            self._lock_controls()

    def _cancel_initial_connection(self, message):
        """Return to setup without discarding the previous local match."""
        self.shutdown()
        self.connection_status = "error"
        self.pending_move = False
        if self._local_controls is not None:
            buttons, ai_states = self._local_controls
            for button, enabled in buttons:
                button.is_abled = enabled
            self.game.chess_board.ai_black.is_start, self.game.chess_board.ai_red.is_start = ai_states
            self._local_controls = None
        self._panel_session()
        self._set_message(message)
        self.redraw()

    def poll(self):
        while True:
            try:
                generation, server, address, name = self._startup_events.get_nowait()
            except queue.Empty:
                break
            if generation != self._generation:
                if server:
                    threading.Thread(target=server.stop, daemon=True).start()
                continue
            self.starting = False
            if server is None:
                self._cancel_initial_connection(address)
                continue
            self.server = server
            self.address = address
            self._connect(f"ws://127.0.0.1:{server.port}", name, "create")
        if not self.client:
            return
        for event in self.client.poll():
            if (not self.client.token and self.state is None and
                    (event.get("type") == "error" or
                     event.get("type") == "connection" and event.get("status") in ("error", "disconnected"))):
                self._cancel_initial_connection(event.get("message", "连接失败，请检查后重试"))
                break
            if event.get("type") == "state":
                try:
                    self._apply_state(event)
                except (ValueError, KeyError, TypeError, IndexError):
                    self.pending_move = False
                    self.connection_status = "error"
                    self.client.close()
                    self._set_message("棋局数据异常，请重新连接")
            elif event.get("type") == "welcome":
                self._set_message("已进入房间，请双方准备")
            elif event.get("type") == "error":
                self.pending_move = False
                if not self.client.connected:
                    self.connection_status = "error"
                self._set_message(event.get("message", "操作未成功，请重试"))
            elif event.get("type") == "connection":
                self.connection_status = event.get("status", "disconnected")
                if self.connection_status != "connected":
                    self.pending_move = False
                    self.game.user_panel.stopTimer(1)
                    self.game.user_panel.stopTimer(0)
                    self._set_message(event.get("message", "连接中断，请打开联网对战重连"))
            self._panel_session()

    def _lock_controls(self):
        if not self._board_initialized and self._local_controls is None:
            buttons = (self.game.menu.buttons + self.game.user_panel.control_up.buttons +
                       self.game.user_panel.control_down.buttons)
            self._local_controls = ([(button, button.is_abled) for button in buttons],
                                    (self.game.chess_board.ai_black.is_start, self.game.chess_board.ai_red.is_start))
        for index in (0, 1, 4):
            self.game.menu.buttons[index].is_abled = False
        self.game.menu.buttons[2].is_abled = self.game.recorder is not None
        self.game.menu.buttons[5].is_abled = True
        self.game.chess_board.ai_black.is_start = False
        self.game.chess_board.ai_red.is_start = False
        self.game.user_panel.control_up.deactivate(self.game.screen)
        self.game.user_panel.control_down.deactivate(self.game.screen)
        self.game.menu.draw(self.game.screen)

    def _apply_state(self, state):
        if state.get("room") != self.client.room:
            raise ValueError("room mismatch")
        board = validate_snapshot(state)
        if self.state and state["revision"] < self.state["revision"]:
            return
        if self.state and (len(state["moves"]) < len(self.state["moves"]) or
                           state["moves"][:len(self.state["moves"])] != self.state["moves"]):
            raise ValueError("history changed")
        self.pending_move = False
        self.state = state
        game = self.game
        if not self._board_initialized:
            Globals.reset()
            Globals.chosen_chess_index = None
            old = game.chess_manual
            game.chess_manual = ChessManual(old.up, old.down, old.left, old.right, old.bgcolor)
            game.recorder = None
            game._record_finished = False
            game.user_panel.resetTimer(game.screen, True)
            game.user_panel.resetTimer(game.screen, False)
            self._board_initialized = True
            self._local_controls = None
        if not game.chess_board.chess_locs[0]:
            game.chess_board.initChess()
        colors = {"B": pygame.Color("black"), "R": pygame.Color("red"), ".": pygame.Color("white")}
        for row, text in enumerate(state["board"]):
            for col, value in enumerate(text):
                game.chess_board.chess_locs[row + 2][col + 2].color = colors[value]
        game.chess_board.clear_selection()
        Globals.chosen_chess = None
        Globals.chosen_chess_index = None
        Globals.black, Globals.red = board.count(Color.BLACK), board.count(Color.RED)
        Globals.is_black = state["turn"] == "black"
        Globals.step = state["ply"]
        Globals.game_start = state["status"] == "playing"
        both = all(state["players"].get(color) and state["players"][color]["connected"] for color in ("black", "red"))
        Globals.game_stop = not both
        for color, is_up in (("black", True), ("red", False)):
            player = state["players"].get(color)
            name = player["name"] if player else "等待加入"
            # Names remain complete in the room panel and saved match metadata.
            game.user_panel.updateName(game.screen, name[:12], is_up)
        if state["status"] in ("playing", "finished") and game.recorder is None:
            self._start_record()
        while self._recorded_moves < len(state["moves"]):
            game.chess_manual.addRecord(game.screen, state["moves"][self._recorded_moves]["text"])
            self._recorded_moves += 1
        game.user_panel.stopTimer(True)
        game.user_panel.stopTimer(False)
        if Globals.game_start and both and self.client.connected:
            game.user_panel.startTimer(game.screen, Globals.is_black)
        if state["status"] == "finished":
            result = state["result"]
            winner = {"black": "黑方获胜", "red": "红方获胜", None: "和棋"}[result["winner"]]
            reason = REASONS.get(result["reason"], "对局结束")
            if not self._result_recorded:
                game.chess_manual.addResult(game.screen, f"# {winner}（{reason}）")
                self._result_recorded = True
            game._record_finished = True
            message = f"{winner} · {reason}"
        elif state["status"] == "waiting":
            message = "等待双方准备"
            if state["players"].get(self.client.color, {}).get("ready"):
                message = "已准备，等待对手"
        elif not both:
            message = "对手断线，等待重连"
        else:
            message = "轮到你落子" if state["turn"] == self.client.color else "等待对手落子"
        self._lock_controls()
        self.redraw()
        saved = game._save_record("network_finish" if state["status"] == "finished" else "network_sync")
        if game.recorder is not None:
            self._record_warning = "棋谱保存失败，请截图备份" if saved is None else ""
            if saved is not None:
                game.record_error = ""
        self._set_message(message)

    def _start_record(self):
        from Class.GameManager import RECORDS_DIR

        game = self.game
        if not game.chess_manual.record:
            game.chess_manual.gameStart(game.screen)
        players = self.state["players"]
        try:
            game.recorder = GameRecorder(
                RECORDS_DIR, settings=self.record_settings,
                metadata={"event": "联网友谊对局", "group": self.client.room,
                          "black_team": players["black"]["name"], "red_team": (players.get("red") or {}).get("name", "")},
                initial_rows=BoardState.initial().to_rows(),
            )
            self._record_warning = ""
        except OSError as error:
            game.record_error = str(error)
            self._record_warning = "棋谱保存失败，请检查目录权限"

    def _click_board(self, pos):
        if not self.state or self.state["status"] != "playing" or not self.client.connected or self.pending_move:
            return
        if self.state["turn"] != self.client.color:
            self._set_message("请等待对手落子")
            return
        if not all(player and player["connected"] for player in self.state["players"].values()):
            self._set_message("等待对手重新连接")
            return
        game = self.game
        location = game.chess_board.chooseLoc(pos)
        if location is None:
            return
        col, row = location
        board = BoardState.from_rows(self.state["board"], Color.BLACK if self.client.color == "black" else Color.RED)
        if board.at((row - 2, col - 2)) == board.side_to_move:
            game.chess_board.clear_selection()
            game.chess_board.set_selected_position(location)
            game.chess_board.chess_locs[row][col].selected = True
            self.redraw()
            return
        start = game.chess_board.selected_position
        if start is None:
            return
        source = (start[1] - 2, start[0] - 2)
        target = (row - 2, col - 2)
        if not any(move.start == source and move.end == target for move in board.legal_moves()):
            self._set_message("该走法不合法")
            return
        if self.client.send("move", revision=self.state["revision"], start=list(source), end=list(target)):
            self.pending_move = True
            game.chess_board.clear_selection()
            self._set_message("落子已发送，等待确认")
            self.redraw()

    def redraw(self):
        game = self.game
        game.chess_board.draw(game.screen)
        if self._board_initialized or game.chess_board.chess_locs[0]:
            game.chess_board.drawChess(game.screen)
        game.chess_manual.draw(game.screen)
        page_size = game.chess_manual.index_now % game.chess_manual.max_rows or game.chess_manual.max_rows
        for textbox in game.chess_manual.textboxes[-page_size:]:
            textbox.draw(game.screen)
        game.user_panel.draw(game.screen)
        game.menu.draw(game.screen)
        if self.client and self.client.room:
            color = "黑方" if self.client.color == "black" else "红方"
            game.user_panel.ai_diagnostics.updateContent(game.screen, f"房间 {self.client.room} · {color} · 不限时")

    def draw(self):
        if self.active and self.state and self.state["status"] == "playing" and self.client and self.client.connected and not Globals.game_stop:
            self.game.user_panel.runTimer(self.game.screen, Globals.is_black)
        if self.panel.visible:
            self.redraw()
            self.panel.draw(self.game.screen)

    def shutdown(self):
        with self._startup_lock:
            self._generation += 1
            self.starting = False
        if self.client:
            self.client.close(leave=True)
            self.client = None
        if self.server:
            server, self.server = self.server, None
            threading.Thread(target=server.stop, name="surakarta-lan-stop", daemon=True).start()
        # Drain any completed startup whose result hasn't reached the main loop.
        while True:
            try:
                _, server, _, _ = self._startup_events.get_nowait()
            except queue.Empty:
                break
            if server:
                threading.Thread(target=server.stop, daemon=True).start()
