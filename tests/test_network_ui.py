"""Exercise the Pygame adapter against a real independent second player."""
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame

from Class.Globals import Globals
from Class.NetworkSession import validate_snapshot
from engine.board import BoardState, Color
from networking.client import NetworkClient
from networking.server import EmbeddedServer

ROOT = Path(__file__).resolve().parents[1]
manager = importlib.import_module("Class.GameManager")


class NetworkUITest(unittest.TestCase):
    def setUp(self):
        self.previous_cwd = Path.cwd()
        os.chdir(ROOT)
        self.records = tempfile.TemporaryDirectory()
        self.record_patch = patch.object(manager, "RECORDS_DIR", Path(self.records.name))
        self.record_patch.start()
        Globals.reset()
        self.game = manager.GameManage()
        self.server = EmbeddedServer(host="127.0.0.1", port=0).start()
        self.peer = None
        self.peer_state = None

    def tearDown(self):
        self.game.network.shutdown()
        if self.peer:
            self.peer.close(leave=True)
        self.server.stop()
        pygame.quit()
        self.record_patch.stop()
        self.records.cleanup()
        os.chdir(self.previous_cwd)

    def wait_for(self, predicate, timeout=6):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.game.network.poll()
            if self.peer:
                for event in self.peer.poll():
                    if event.get("type") == "state":
                        self.peer_state = event
            if predicate():
                return
            time.sleep(0.01)
        self.fail(f"Timed out; panel message={self.game.network.panel.message!r}")

    def connect_pair(self):
        session = self.game.network
        url = f"ws://127.0.0.1:{self.server.port}"
        session.panel.mode = "online"
        session.perform({"action": "connect", "name": "本机", "url": url, "mode": "create", "room": ""})
        self.wait_for(lambda: session.state is not None)
        self.peer = NetworkClient(url, name="对手")
        self.peer.start(mode="join", room=session.client.room)
        self.wait_for(lambda: self.peer.connected and session.state["players"]["red"] is not None)
        session.perform({"action": "ready"})
        self.peer.send("ready")
        self.wait_for(lambda: session.state["status"] == "playing" and self.peer_state and self.peer_state["status"] == "playing")
        return session

    def test_confirmed_moves_reconnect_record_export_and_resign(self):
        session = self.connect_pair()
        self.assertIsNotNone(self.game.recorder)
        self.assertFalse(self.game.menu.buttons[0].is_abled)
        self.assertFalse(self.game.menu.buttons[1].is_abled)
        self.assertFalse(self.game.menu.buttons[4].is_abled)
        self.assertTrue(self.game.menu.buttons[5].is_abled)
        self.assertTrue(all(not button.is_abled for button in self.game.user_panel.control_up.buttons))
        first = BoardState.initial().legal_moves()[0]
        points = self.game.chess_board.board_point_locs
        session._click_board(points[first.start[0] + 2][first.start[1] + 2])
        session._click_board(points[first.end[0] + 2][first.end[1] + 2])
        # The UI is unchanged until the authoritative response is polled.
        self.assertEqual(Globals.step, 0)
        self.assertTrue(session.pending_move)
        session._click_board(points[first.end[0] + 2][first.end[1] + 2])
        self.wait_for(lambda: session.state["ply"] == 1 and self.peer_state["ply"] == 1)
        self.assertEqual(Globals.step, 1)
        self.assertEqual(self.game.chess_board.ai_black.to_engine_board(self.game.chess_board).to_rows(), session.state["board"])
        self.assertEqual(session.state["board"], self.peer_state["board"])

        second = BoardState.from_rows(self.peer_state["board"], Color.RED).legal_moves()[0]
        self.peer.send("move", revision=self.peer_state["revision"], start=list(second.start), end=list(second.end))
        self.wait_for(lambda: session.state["ply"] == 2 and self.peer_state["ply"] == 2)
        record_before = list(self.game.chess_manual.record)
        self.assertEqual(len([entry for entry in record_before if entry.startswith(("B", "R"))]), 2)

        self.peer.close()
        self.wait_for(lambda: not session.state["players"]["red"]["connected"])
        self.assertTrue(Globals.game_stop)
        self.peer.reconnect()
        self.wait_for(lambda: session.state["players"]["red"]["connected"] and self.peer.connected)
        self.assertEqual(self.game.chess_manual.record, record_before)
        self.assertFalse(Globals.game_stop)

        exported = self.game.export_record()
        self.assertIsNotNone(exported)
        data = json.loads(Path(exported).with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["moves"]), 2)
        self.assertEqual(data["metadata"]["black_team"], "本机")
        self.assertEqual(data["metadata"]["red_team"], "对手")
        self.assertNotIn(session.client.token, json.dumps(data))
        self.assertEqual(data["current_settings"]["move_clock"], "unlimited")

        self.peer.send("resign")
        self.wait_for(lambda: session.state["status"] == "finished")
        self.assertEqual(session.state["result"]["winner"], "black")
        self.assertTrue(self.game._record_finished)
        self.assertFalse(Globals.game_start)
        session.open()
        session.draw()
        session.perform({"action": "close"})
        self.assertTrue(session.active)
        self.assertFalse(session.panel.visible)
        session.perform({"action": "leave"})
        self.assertFalse(self.game.network.active)
        self.assertTrue(self.game.menu.buttons[0].is_abled)

    def test_host_button_starts_embedded_service_off_main_thread(self):
        session = self.game.network
        started = time.monotonic()
        session.perform({"action": "host", "name": "房主", "port": 0})
        self.assertLess(time.monotonic() - started, 0.3)
        self.wait_for(lambda: session.state is not None)
        self.assertIsNotNone(session.server)
        self.assertTrue(session.address.startswith("ws://"))
        self.assertEqual(session.client.color, "black")
        self.assertEqual(session.state["status"], "waiting")
        self.assertIsNone(self.game.recorder)

    def test_bad_snapshot_never_changes_board(self):
        session = self.connect_pair()
        state = dict(session.state)
        state["board"] = ["X" * 6] * 6
        with self.assertRaises(ValueError):
            validate_snapshot(state)
        self.assertEqual(Globals.step, 0)

    def test_record_export_succeeds_with_limited_console_encoding(self):
        self.connect_pair()
        for encoding in ("ascii", "cp1252"):
            with self.subTest(encoding=encoding):
                with io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors="strict") as console:
                    with patch("sys.stdout", console):
                        exported = self.game.export_record()
                self.assertIsNotNone(exported)
                self.assertTrue(exported.is_file())
                data = json.loads(exported.with_suffix(".json").read_text(encoding="utf-8"))
                self.assertEqual(data["metadata"]["black_team"], "本机")
                self.assertEqual(data["metadata"]["red_team"], "对手")
                self.assertIn("已保存", self.game.user_panel.state.content)

    def completed_local_match(self):
        self.game.chess_board.drawChess(self.game.screen)
        self.game.chess_manual.gameStart(self.game.screen)
        self.game.menu.gameStart(self.game.screen)
        self.game._start_recording()
        self.game.game_over(result="# 黑方获胜")
        self.game.chess_board.ai_black.is_start = True
        buttons = (self.game.menu.buttons + self.game.user_panel.control_up.buttons +
                   self.game.user_panel.control_down.buttons)
        return (self.game.recorder, list(self.game.chess_manual.record),
                self.game.chess_board.ai_black.to_engine_board(self.game.chess_board).to_rows(),
                [(button, button.is_abled) for button in buttons])

    def assert_local_match_preserved(self, prior):
        recorder, records, board, buttons = prior
        self.assertIs(self.game.recorder, recorder)
        self.assertEqual(self.game.chess_manual.record, records)
        self.assertEqual(self.game.chess_board.ai_black.to_engine_board(self.game.chess_board).to_rows(), board)
        self.assertTrue(self.game.chess_board.ai_black.is_start)
        self.assertTrue(self.game._record_finished)
        for button, enabled in buttons:
            self.assertEqual(button.is_abled, enabled)
        self.assertFalse(self.game.network.active)
        self.assertFalse(self.game.network.panel.active)

    def test_host_failure_preserves_local_match_and_allows_retry(self):
        prior = self.completed_local_match()
        session = self.game.network
        with patch("Class.NetworkSession.EmbeddedServer.start", side_effect=OSError("address in use")):
            session.perform({"action": "host", "name": "玩家", "port": self.server.port})
            self.wait_for(lambda: not session.active)
        self.assertIn("端口", session.panel.message)
        self.assert_local_match_preserved(prior)
        session.perform({"action": "host", "name": "玩家", "port": 0})
        self.wait_for(lambda: session.state is not None)
        self.assertEqual(session.state["status"], "waiting")

    def test_rejected_join_preserves_local_record_and_allows_retry(self):
        prior = self.completed_local_match()
        session = self.game.network
        url = f"ws://127.0.0.1:{self.server.port}"
        session.perform({"action": "connect", "name": "玩家", "url": url, "mode": "join", "room": "MISSING"})
        saved = self.game._save_record("export")
        data = json.loads(saved.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(data["current_settings"], self.game.ai_settings.to_dict())
        self.wait_for(lambda: not session.active)
        self.assertIn("房间不存在", session.panel.message)
        self.assert_local_match_preserved(prior)
        session.perform({"action": "connect", "name": "玩家", "url": url, "mode": "create"})
        self.wait_for(lambda: session.state is not None)
        self.assertEqual(session.state["status"], "waiting")

    def test_cancel_before_initial_snapshot_keeps_local_match(self):
        prior = self.completed_local_match()
        session = self.game.network
        session.perform({"action": "connect", "name": "玩家", "url": f"ws://127.0.0.1:{self.server.port}", "mode": "create"})
        session.perform({"action": "leave"})
        self.assertIs(self.game.network, session)
        self.assert_local_match_preserved(prior)

    def test_record_failures_remain_visible_until_successful_save(self):
        with patch("Class.NetworkSession.GameRecorder", side_effect=OSError("directory unavailable")):
            session = self.connect_pair()
            self.assertIsNone(self.game.recorder)
            self.assertIn("棋谱保存失败", session.panel.message)
            self.assertIn("棋谱保存失败", self.game.user_panel.state.content)
            session._set_message("等待对手落子")
            self.assertIn("棋谱保存失败", session.panel.message)
        session._apply_state(dict(session.state))
        self.assertIsNotNone(self.game.recorder)
        self.assertNotIn("棋谱保存失败", session.panel.message)
        with patch.object(self.game.recorder, "save", side_effect=OSError("disk full")):
            session._apply_state(dict(session.state))
            session.draw()
            self.assertIn("棋谱保存失败", session.panel.message)
            self.assertIn("棋谱保存失败", self.game.user_panel.state.content)
        session._apply_state(dict(session.state))
        self.assertNotIn("棋谱保存失败", session.panel.message)


if __name__ == "__main__":
    unittest.main()
