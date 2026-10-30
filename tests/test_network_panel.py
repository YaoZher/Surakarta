"""Exercise room panel behavior with real Pygame events and a dummy display."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame

from Class.Element.NetworkPanel import NetworkPanel


class NetworkPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((1400, 700))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.panel = NetworkPanel()
        self.panel.open()
        self.initial_name = self.panel.values['name']

    def click(self, rect):
        return self.panel.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))

    def key(self, key, mod=0):
        return self.panel.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod))

    def text(self, text):
        return self.panel.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=text))

    def fill(self, field, text):
        self.click(self.panel.field_rects[field])
        self.key(pygame.K_a, pygame.KMOD_CTRL)
        self.text(text)

    def tab(self, mode):
        self.click(self.panel.tab_rects[mode])

    def test_host_action_and_invalid_port(self):
        self.fill("name", "对局玩家")
        self.fill("port", "9000")
        self.assertEqual(self.click(self.panel.action_rects["host"]),
                         {"action": "host", "name": "对局玩家", "port": 9000})
        for invalid in ("0", "65536"):
            self.fill("port", invalid)
            self.assertIsNone(self.click(self.panel.action_rects["host"]))
            self.assertIn("1–65535", self.panel.message)

    def test_lan_join_normalizes_address_and_room(self):
        self.tab("join_lan")
        self.fill("name", "红方")
        self.fill("room", "ab12cd")
        self.fill("lan_address", "192.168.1.8")
        self.assertEqual(self.click(self.panel.action_rects["join_lan"]),
                         {"action": "connect", "name": "红方", "url": "ws://192.168.1.8:8765",
                          "mode": "join", "room": "AB12CD"})
        self.fill("lan_address", "[::1]:9000")
        self.assertEqual(self.key(pygame.K_RETURN)["url"], "ws://[::1]:9000")

    def test_online_create_does_not_require_room_but_join_does(self):
        self.tab("online")
        self.fill("online_address", "wss://rooms.example.test/play")
        action = self.click(self.panel.action_rects["create"])
        self.assertEqual(action["mode"], "create")
        self.assertEqual(action["room"], "")
        self.assertIsNone(self.click(self.panel.action_rects["join"]))
        self.assertIn("房间码", self.panel.message)
        self.fill("room", "abc123")
        action = self.click(self.panel.action_rects["join"])
        self.assertEqual(action["mode"], "join")
        self.assertEqual(action["room"], "ABC123")
        self.assertEqual(action["url"], "wss://rooms.example.test/play")

    def test_bad_addresses_report_errors_without_throwing(self):
        self.tab("online")
        for invalid in ("https://example.test", "ws://", "ws://[bad", "ws://example.test:abc",
                        "ws://example.test:0", "ws://example.test:", "ws://name:password@example.test", "ws://a b", "ws://host#part"):
            self.fill("online_address", invalid)
            self.assertIsNone(self.click(self.panel.action_rects["create"]), invalid)
            self.assertIn("服务地址", self.panel.message)

    def test_chinese_ime_selection_cursor_and_deletion(self):
        self.key(pygame.K_a, pygame.KMOD_CTRL)
        self.panel.handle_event(pygame.event.Event(pygame.TEXTEDITING, text="zhong", start=0, length=5))
        self.assertEqual(self.panel.values["name"], self.initial_name)
        self.text("中文昵称")
        self.assertEqual(self.panel.values["name"], "中文昵称")
        self.key(pygame.K_LEFT)
        self.key(pygame.K_BACKSPACE)
        self.text("对局")
        self.assertEqual(self.panel.values["name"], "中文对局称")
        self.key(pygame.K_HOME)
        self.key(pygame.K_DELETE)
        self.assertEqual(self.panel.values["name"], "文对局称")

    def test_name_length_blank_name_and_tab_focus(self):
        self.fill("name", "棋" * 40)
        self.assertEqual(len(self.panel.values["name"]), 20)
        self.key(pygame.K_TAB)
        self.assertEqual(self.panel.focus, "port")
        self.key(pygame.K_TAB, pygame.KMOD_SHIFT)
        self.assertEqual(self.panel.focus, "name")
        self.key(pygame.K_a, pygame.KMOD_CTRL)
        self.key(pygame.K_BACKSPACE)
        self.assertIsNone(self.click(self.panel.action_rects["host"]))
        self.assertIn("昵称", self.panel.message)

    def test_clipboard_paste_and_unavailable_clipboard(self):
        self.tab("online")
        self.click(self.panel.field_rects["online_address"])
        with patch.object(NetworkPanel, "_clipboard_read", return_value="wss://rooms.example.test\n"):
            self.key(pygame.K_v, pygame.KMOD_CTRL)
        self.assertEqual(self.panel.values["online_address"], "wss://rooms.example.test")
        with patch.object(NetworkPanel, "_clipboard_read", side_effect=pygame.error("clipboard unavailable")):
            self.key(pygame.K_v, pygame.KMOD_CTRL)
        self.assertIn("无法读取剪贴板", self.panel.message)

    def test_switching_modes_preserves_separate_addresses(self):
        self.tab("online")
        self.fill("online_address", "wss://rooms.example.test")
        self.tab("join_lan")
        self.fill("lan_address", "192.168.1.8:9000")
        self.tab("online")
        self.assertEqual(self.panel.values["online_address"], "wss://rooms.example.test")
        self.assertEqual(self.panel.values["lan_address"], "192.168.1.8:9000")

    def test_clipboard_decodes_unicode_and_ascii_text(self):
        examples = [("中文昵称".encode("utf-8") + b"\x00", "中文昵称"),
                    ("中文昵称".encode("utf-16-le") + b"\x00\x00", "中文昵称"),
                    ("wss://rooms.example.test".encode("utf-16-le") + b"\x00\x00", "wss://rooms.example.test")]
        for raw, expected in examples:
            with patch.object(pygame.scrap, "get_init", return_value=True), patch.object(pygame.scrap, "get", return_value=raw):
                self.assertEqual(NetworkPanel._clipboard_read(), expected)

    def test_active_room_prevents_new_room_and_uses_session_buttons(self):
        self.panel.set_session(room="ABC123", color="black", status="waiting", address="ws://localhost:8765")
        self.assertEqual(self.click(self.panel.action_rects["ready"]), {"action": "ready"})
        self.assertIsNone(self.click(self.panel.action_rects["resign"]))
        self.assertIsNone(self.click(self.panel.tab_rects["online"]))
        self.assertEqual(self.panel.mode, "host")
        self.assertIsNone(self.panel._activate("host"))
        self.assertIsNone(self.panel._activate("create"))
        self.text("cannot edit while connected")
        self.assertEqual(self.panel.values["name"], self.initial_name)
        self.panel.set_session(room="ABC123", color="black", status="playing")
        self.assertIsNone(self.click(self.panel.action_rects["ready"]))
        self.assertEqual(self.click(self.panel.action_rects["resign"]), {"action": "resign"})
        self.assertEqual(self.click(self.panel.action_rects["leave"]), {"action": "leave"})
        self.panel.set_session(room="ABC123", color="black", status="disconnected")
        self.assertEqual(self.click(self.panel.action_rects["reconnect"]), {"action": "reconnect"})

    def test_close_and_escape_hide_without_leaving_room(self):
        self.panel.open(active=True, room="ABC123", color="red", status="playing")
        self.assertEqual(self.key(pygame.K_ESCAPE), {"action": "close"})
        self.assertFalse(self.panel.visible)
        self.assertTrue(self.panel.active)
        self.assertEqual(self.panel.room, "ABC123")
        self.assertIsNone(self.key(pygame.K_RETURN))
        self.panel.open(active=True, room="ABC123", color="red", status="playing")
        self.assertEqual(self.click(self.panel.close_rect), {"action": "close"})

    def test_all_layouts_render_and_click_targets_fit_card(self):
        for mode, _ in self.panel.MODES:
            self.tab(mode)
            self.panel.message = "这是较长的状态说明。" * 50
            self.panel.draw(self.screen)
            for key in self.panel._fields():
                self.assertTrue(self.panel.card.contains(self.panel.field_rects[key]))
            for key in self.panel._actions():
                self.assertTrue(self.panel.card.contains(self.panel.action_rects[key]))
            self.assertEqual(self.screen.get_clip(), self.screen.get_rect())
        for status in NetworkPanel.STATUS_LABELS:
            self.panel.set_session(room="ABC123", color="red", status=status,
                                   address="wss://example.test/" + "a" * 500)
            self.panel.draw(self.screen)
            for key in self.panel._actions():
                self.assertTrue(self.panel.card.contains(self.panel.action_rects[key]))


if __name__ == "__main__":
    unittest.main()
