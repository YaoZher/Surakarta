"""Exercise the authoritative service through real localhost WebSockets."""
import json
import os
from pathlib import Path
import queue
import socket as socket_module
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import AsyncMock

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from engine.board import BoardState, Color
from networking.server import EmbeddedServer, Player, RequestError, Room, RoomService


class RoomServerTests(unittest.TestCase):
    def setUp(self):
        self.sockets = []
        self.server = None
        self.start_server()

    def start_server(self, **options):
        if self.server is not None:
            for socket in self.sockets:
                socket.close()
            self.sockets.clear()
            self.server.stop()
        settings = dict(reconnect_seconds=0.5, cleanup_interval=0.02,
                        finished_seconds=2, idle_seconds=30, rate_limit=200)
        settings.update(options)
        self.server = EmbeddedServer("127.0.0.1", 0, **settings).start()
        self.url = f"ws://127.0.0.1:{self.server.port}"

    def tearDown(self):
        for socket in self.sockets:
            socket.close()
        self.server.stop()

    def socket(self):
        socket = connect(self.url, proxy=None, close_timeout=0.2, max_size=1024 * 1024)
        self.sockets.append(socket)
        return socket

    @staticmethod
    def send(socket, kind, **fields):
        socket.send(json.dumps({"type": kind, **fields}))

    def receive(self, socket, kind, predicate=lambda event: True, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            event = json.loads(socket.recv(timeout=max(0.01, deadline - time.monotonic())))
            if event["type"] == kind and predicate(event):
                return event
        self.fail(f"No matching {kind} event")

    def bind(self, kind, **fields):
        socket = self.socket()
        self.send(socket, kind, version=1, **fields)
        return socket, self.receive(socket, "welcome"), self.receive(socket, "state")

    def pair(self, ready=True):
        black, welcome, _ = self.bind("create", name="黑方")
        red, red_welcome, state = self.bind("join", room=welcome["room"], name="红方")
        self.receive(black, "state", lambda s: s["revision"] == state["revision"])
        if ready:
            for socket in (black, red):
                self.send(socket, "ready")
                state = self.receive(black, "state")
                self.receive(red, "state", lambda s: s["revision"] == state["revision"])
            self.assertEqual(state["status"], "playing")
        return black, red, welcome, red_welcome, state

    def error(self, socket, code, kind, **fields):
        self.send(socket, kind, **fields)
        event = self.receive(socket, "error")
        self.assertEqual(event["code"], code, event)

    def test_ready_legality_turn_coordinates_duplicate_revision(self):
        black, red, _, _, state = self.pair(ready=False)
        self.error(black, "not_ready", "move", revision=state["revision"], start=[1, 0], end=[2, 0])
        for socket in (black, red):
            self.send(socket, "ready")
            state = self.receive(black, "state")
            self.receive(red, "state")
        revision = state["revision"]
        self.error(red, "wrong_turn", "move", revision=revision, start=[4, 0], end=[3, 0])
        self.error(black, "illegal_move", "move", revision=revision, start=[4, 0], end=[3, 0])
        self.error(black, "illegal_move", "move", revision=revision, start=[1, 0], end=[3, 0])
        for start in ([-1, 0], [True, 0], [1.0, 0], [1, 0, 0], "10"):
            self.error(black, "invalid_coordinate", "move", revision=revision, start=start, end=[2, 0])
        self.error(black, "invalid_revision", "move", revision=True, start=[1, 0], end=[2, 0])
        self.error(black, "stale_revision", "move", revision=revision + 1, start=[1, 0], end=[2, 0])
        self.assertEqual(self.receive(black, "state")["ply"], 0)
        self.send(black, "move", revision=revision, start=[1, 0], end=[2, 0], capture=True, color="red")
        moved = self.receive(black, "state")
        self.assertEqual(self.receive(red, "state"), moved)
        self.assertEqual(moved["revision"], revision + 1)
        self.assertEqual(moved["moves"][0], {"start": [1, 0], "end": [2, 0],
                                          "color": "black", "capture": False, "text": "B2A-3A"})
        self.error(black, "stale_revision", "move", revision=revision, start=[1, 0], end=[2, 0])
        self.assertEqual(self.receive(black, "state"), moved)

    def test_room_full_tokens_and_malformed_messages(self):
        black, _, welcome, _, state = self.pair()
        stranger = self.socket()
        self.error(stranger, "not_joined", "move", revision=0, start=[1, 0], end=[2, 0])
        self.error(stranger, "version_mismatch", "join", version=2, room=welcome["room"], name="甲")
        self.error(stranger, "room_full", "join", version=1, room=welcome["room"], name="甲")
        for token in ("bad", "中文", "", "\ud800"):
            self.error(stranger, "invalid_token", "resume", version=1, room=welcome["room"], token=token)
        self.error(stranger, "seat_connected", "resume", version=1, room=welcome["room"], token=welcome["token"])
        self.assertNotIn(welcome["token"], json.dumps(state))
        for raw in ("[]", "not JSON", '{"type":false}', b"binary"):
            stranger.send(raw)
            self.assertEqual(self.receive(stranger, "error")["code"], "invalid_message")
        self.send(black, "sync")
        self.assertEqual(self.receive(black, "state"), state)
        self.error(stranger, "invalid_name", "create", version=1, name="\ud800")

    def test_disconnect_pause_and_token_resume_full_state(self):
        black, red, welcome, _, state = self.pair()
        self.send(black, "move", revision=state["revision"], start=[1, 0], end=[2, 0])
        state = self.receive(red, "state")
        self.receive(black, "state")
        black.close()
        disconnected = self.receive(red, "state", lambda s: not s["players"]["black"]["connected"])
        self.error(red, "opponent_disconnected", "move", revision=disconnected["revision"], start=[4, 0], end=[3, 0])
        resumed, resume_welcome, resumed_state = self.bind("resume", room=welcome["room"], token=welcome["token"])
        self.assertEqual(resume_welcome["token"], welcome["token"])
        self.assertEqual(resumed_state["board"], state["board"])
        self.assertEqual(resumed_state["moves"], state["moves"])
        self.assertEqual(resumed_state["turn"], "red")
        self.assertTrue(resumed_state["players"]["black"]["connected"])
        self.receive(red, "state", lambda s: s["revision"] == resumed_state["revision"])
        self.send(red, "move", revision=resumed_state["revision"], start=[4, 0], end=[3, 0])
        self.assertEqual(self.receive(resumed, "state")["ply"], 2)

    def test_disconnect_timeout_awards_opponent(self):
        black, red, welcome, _, _ = self.pair()
        black.close()
        ended = self.receive(red, "state", lambda s: s["status"] == "finished")
        self.assertEqual(ended["result"], {"winner": "red", "reason": "disconnect_timeout"})
        visitor = self.socket()
        self.error(visitor, "resume_expired", "resume", version=1, room=welcome["room"], token=welcome["token"])
        self.error(red, "game_finished", "move", revision=ended["revision"], start=[4, 0], end=[3, 0])

    def test_resign_and_explicit_leave_invalidates_token(self):
        black, red, welcome, _, _ = self.pair()
        self.send(red, "resign")
        ended = self.receive(black, "state")
        self.assertEqual(ended["result"], {"winner": "black", "reason": "resign"})
        self.assertEqual(ended, self.receive(red, "state"))
        self.send(black, "leave")
        self.receive(black, "state")
        visitor = self.socket()
        self.error(visitor, "invalid_token", "resume", version=1, room=welcome["room"], token=welcome["token"])

    def test_leave_live_game_awards_opponent(self):
        black, red, _, _, _ = self.pair()
        self.send(black, "leave")
        self.assertEqual(self.receive(red, "state")["result"], {"winner": "red", "reason": "leave"})

    def test_threefold_draw_and_independent_rooms(self):
        black, red, _, _, state = self.pair()
        other, _, initial = self.bind("create", name="独立房间")
        cycle = [(black, [1, 0], [2, 0]), (red, [4, 5], [3, 5]),
                 (black, [2, 0], [1, 0]), (red, [3, 5], [4, 5])]
        for socket, start, end in cycle * 2:
            self.send(socket, "move", revision=state["revision"], start=start, end=end)
            state = self.receive(black, "state")
            self.assertEqual(state, self.receive(red, "state"))
        self.assertEqual(state["ply"], 8)
        self.assertEqual(state["result"], {"winner": None, "reason": "threefold_repetition"})
        self.send(other, "sync")
        self.assertEqual(self.receive(other, "state"), initial)

    def test_capacity_idle_cleanup_and_handshake_timeout(self):
        self.start_server(max_rooms=1, idle_seconds=0.15, finished_seconds=0.1, handshake_seconds=0.5)
        black, _, _ = self.bind("create", name="甲")
        visitor = self.socket()
        self.error(visitor, "server_full", "create", version=1, name="乙")
        ended = self.receive(black, "state", lambda s: s["status"] == "finished")
        self.assertEqual(ended["result"]["reason"], "idle_timeout")
        with self.assertRaises(ConnectionClosed):
            black.recv(timeout=2)
        _, _, state = self.bind("create", name="丙")
        self.assertEqual(state["status"], "waiting")
        self.assertEqual(self.receive(visitor, "error")["code"], "handshake_timeout")

    def test_abandoned_room_is_cleaned(self):
        self.start_server(reconnect_seconds=0.1, finished_seconds=0.1)
        black, welcome, _ = self.bind("create", name="甲")
        black.close()
        time.sleep(0.3)
        visitor = self.socket()
        self.error(visitor, "room_not_found", "join", version=1, room=welcome["room"], name="乙")

    def test_expired_room_cannot_be_joined_before_cleanup_tick(self):
        self.start_server(reconnect_seconds=0.1, cleanup_interval=5)
        black, welcome, _ = self.bind("create", name="甲")
        black.close()
        time.sleep(0.2)
        visitor = self.socket()
        self.error(visitor, "room_full", "join", version=1, room=welcome["room"], name="乙")
        self.error(visitor, "resume_expired", "resume", version=1, room=welcome["room"], token=welcome["token"])

    def test_ready_player_resumes_into_started_game(self):
        black, red, _, welcome, _ = self.pair(ready=False)
        self.send(red, "ready")
        self.receive(black, "state")
        self.receive(red, "state")
        red.close()
        self.receive(black, "state", lambda s: not s["players"]["red"]["connected"])
        self.send(black, "ready")
        self.assertEqual(self.receive(black, "state")["status"], "waiting")
        _, _, state = self.bind("resume", room=welcome["room"], token=welcome["token"])
        self.assertEqual(state["status"], "playing")

    def test_rate_and_frame_limits(self):
        self.start_server(rate_limit=3)
        socket, _, _ = self.bind("create", name="甲")
        for _ in range(2):
            self.send(socket, "sync")
            self.receive(socket, "state")
        self.send(socket, "sync")
        self.assertEqual(self.receive(socket, "error")["code"], "rate_limited")
        huge = self.socket()
        huge.send("x" * 4097)
        with self.assertRaises(ConnectionClosed):
            huge.recv(timeout=2)

    def test_startup_error_propagates(self):
        occupied = EmbeddedServer("127.0.0.1", self.server.port)
        with self.assertRaises(OSError):
            occupied.start()
        occupied.stop()

    def test_standalone_cli_serves_without_importing_pygame(self):
        root = Path(__file__).resolve().parents[1]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.run([sys.executable, "-B", "-c",
                        "import sys, server.__main__; assert 'pygame' not in sys.modules"],
                       cwd=root, check=True, timeout=10, creationflags=flags)
        process = subprocess.Popen(
            [sys.executable, "-B", "-u", "-m", "server", "--host", "127.0.0.1", "--port", "0"],
            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            creationflags=flags,
        )
        lines = queue.Queue()
        reader = threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True)
        reader.start()
        try:
            line = lines.get(timeout=10)
            self.assertIn("listening on 127.0.0.1:", line)
            port = int(line.rsplit(":", 1)[1])
            with connect(f"ws://127.0.0.1:{port}", proxy=None, close_timeout=0.2) as socket:
                self.send(socket, "create", version=1, name="独立服务")
                self.assertEqual(self.receive(socket, "welcome")["color"], "black")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            reader.join(timeout=1)
            process.stdout.close()


class ListenerBindingTests(unittest.TestCase):
    def test_wildcard_and_loopback_cannot_share_a_port(self):
        for first_host, second_host in (("127.0.0.1", "0.0.0.0"),
                                        ("0.0.0.0", "127.0.0.1")):
            with self.subTest(first=first_host, second=second_host):
                first = EmbeddedServer(first_host, 0).start()
                second = EmbeddedServer(second_host, first.port)
                try:
                    with self.assertRaises(OSError):
                        second.start()
                    # Failure must not disturb the original listener.
                    with connect(f"ws://127.0.0.1:{first.port}", proxy=None,
                                 close_timeout=0.2) as client:
                        client.send('{"type":"create","version":1,"name":"test"}')
                        self.assertEqual(json.loads(client.recv(timeout=2))["type"], "welcome")
                finally:
                    second.stop()
                    first.stop()

    def test_hostname_listener_accepts_connections(self):
        server = EmbeddedServer("localhost", 0).start()
        try:
            with connect(f"ws://localhost:{server.port}", proxy=None,
                         close_timeout=0.2) as client:
                client.send('{"type":"create","version":1,"name":"test"}')
                self.assertEqual(json.loads(client.recv(timeout=2))["type"], "welcome")
        finally:
            server.stop()

    def test_ipv6_listener_accepts_connections(self):
        if not socket_module.has_ipv6:
            self.skipTest("IPv6 unavailable")
        try:
            with socket_module.socket(socket_module.AF_INET6) as probe:
                probe.bind(("::1", 0))
        except OSError:
            self.skipTest("IPv6 loopback unavailable")
        server = EmbeddedServer("::1", 0).start()
        try:
            with connect(f"ws://[::1]:{server.port}", proxy=None,
                         close_timeout=0.2) as client:
                client.send('{"type":"create","version":1,"name":"test"}')
                self.assertEqual(json.loads(client.recv(timeout=2))["type"], "welcome")
        finally:
            server.stop()


class RoomDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_expiry_precedes_resign_or_leave_command(self):
        # Exercise the gap before a cleanup tick without sleeps or live sockets.
        for command in ("resign", "leave"):
            with self.subTest(command=command):
                service = RoomService()
                socket = AsyncMock()
                room = Room("TEST", Player("黑方", socket=socket),
                            red=Player("红方", disconnected_at=time.monotonic() - 61),
                            status="playing")
                service.bindings[socket] = room, "black"
                service._broadcast = AsyncMock()
                service._send = AsyncMock()
                if command == "resign":
                    with self.assertRaises(RequestError) as raised:
                        await service._bound_request(socket, {"type": command})
                    self.assertEqual(raised.exception.code, "game_finished")
                else:
                    await service._bound_request(socket, {"type": command})
                    socket.close.assert_awaited_once()
                self.assertEqual(room.status, "finished")
                self.assertEqual(room.result, {"winner": "black", "reason": "disconnect_timeout"})
                self.assertGreater(room.revision, 0)
                service._broadcast.assert_awaited()


class RoomEndRuleTests(unittest.TestCase):
    """Seed rare end positions directly; normal request paths use real sockets above."""

    def room(self, rows=None):
        board = BoardState.initial() if rows is None else BoardState.from_rows(rows, Color.BLACK)
        room = Room("TEST", Player("黑方", socket=object()),
                    red=Player("红方", socket=object()), board=board, status="playing")
        return RoomService(), room

    def test_capture_last_piece_wins(self):
        service, room = self.room([".B....", "......", "......", "......", "R.....", "......"])
        service._move(room, "black", {"start": [0, 1], "end": [4, 0], "capture": False})
        self.assertEqual(room.result, {"winner": "black", "reason": "no_pieces"})
        self.assertTrue(room.moves[-1]["capture"])

    def test_opponent_without_legal_move_loses(self):
        service, room = self.room(["RBBBBB", "BBBBBB", "BBBBBB", "BBBBBB", "BBBBBB", "BBBBB."])
        service._move(room, "black", {"start": [5, 4], "end": [5, 5]})
        self.assertEqual(room.result, {"winner": "black", "reason": "no_legal_moves"})

    def test_eighty_halfmoves_without_capture_draws(self):
        service, room = self.room()
        room.no_capture = 79
        service._move(room, "black", {"start": [1, 0], "end": [2, 0]})
        self.assertEqual(room.result, {"winner": None, "reason": "no_capture_80"})

    def test_capture_resets_non_capture_counter(self):
        service, room = self.room([".B....", "......", "......", "......", "R.....", ".....R"])
        room.no_capture = 79
        service._move(room, "black", {"start": [0, 1], "end": [4, 0]})
        self.assertEqual(room.no_capture, 0)
        self.assertIsNone(room.result)


if __name__ == "__main__":
    unittest.main()
