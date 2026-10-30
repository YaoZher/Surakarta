"""Transport lifecycle tests and real loopback room integration."""

import copy
import json
import queue
import threading
import time
import unittest
from unittest.mock import patch

from networking.client import (
    MAX_EVENTS, MAX_MESSAGE_BYTES, MAX_PENDING_SENDS, NetworkClient,
    _ProtocolError, validate_url,
)


def state(room="ABCDEF", revision=1):
    return {
        "type": "state", "version": 1, "room": room, "revision": revision,
        "status": "waiting", "board": ["BBBBBB", "BBBBBB", "......", "......", "RRRRRR", "RRRRRR"],
        "turn": "black", "ply": 0,
        "players": {"black": {"name": "玩家", "connected": True, "ready": False}, "red": None},
        "moves": [], "result": None, "reconnect_seconds": 60,
    }


def welcome(room="ABCDEF", token="private-token-for-tests"):
    return {"type": "welcome", "version": 1, "room": room, "color": "black", "token": token}


class FakeConnection:
    def __init__(self, messages=(), block_after_messages=None):
        self.incoming = queue.Queue()
        for message in messages:
            self.incoming.put(json.dumps(message) if isinstance(message, dict) else message)
        self.sent = []
        self.closed = False
        self.block_after_messages = block_after_messages
        self.blocked = threading.Event()

    def send(self, message):
        self.sent.append(json.loads(message))

    def recv(self, timeout=None):
        try:
            return self.incoming.get_nowait()
        except queue.Empty:
            if self.block_after_messages is not None:
                self.blocked.set()
                self.block_after_messages.wait(4)
            else:
                time.sleep(0.002)
            raise TimeoutError

    def close(self):
        self.closed = True

    def close_socket(self):
        self.closed = True


class ClientCase(unittest.TestCase):
    def setUp(self):
        self.clients = []
        self.events = {}
        self.original_threads = set(threading.enumerate())

    def make_client(self, url="ws://127.0.0.1:8765", name="玩家"):
        client = NetworkClient(url, name)
        self.clients.append(client)
        self.events[client] = []
        return client

    def tearDown(self):
        workers = [client._thread for client in self.clients]
        for client in self.clients:
            client.close()
        for worker in workers:
            if worker is not None:
                worker.join(5)
                self.assertFalse(worker.is_alive(), "client worker leaked after close")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            leaked = [thread for thread in threading.enumerate() if thread not in self.original_threads]
            if not leaked:
                break
            time.sleep(0.005)
        self.assertFalse(leaked, "client or WebSocket protocol thread leaked after close")

    def wait_for(self, client, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            events = client.poll()
            self.events[client].extend(events)
            for event in events:
                if predicate(event):
                    return event
            time.sleep(0.005)
        self.fail("expected client event was not received")

    def wait_until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.005)
        self.fail("client lifecycle condition timed out")


class NetworkClientUnitTests(ClientCase):
    def test_url_validation_and_local_errors_do_not_open_socket(self):
        self.assertEqual(validate_url("ws://localhost:8765"), "ws://localhost:8765/")
        self.assertEqual(validate_url("wss://example.org/game?room=test"), "wss://example.org/game?room=test")
        self.assertEqual(validate_url("ws://[::1]:8765/"), "ws://[::1]:8765/")
        invalid = ["http://example.org", "ws://", "ws://x:0", "ws://x:65536", "ws://u:secret@x", "ws://x/#frag", "ws://x/#", "ws://x\\evil", "ws://bad host", "ws://x/\ninjected", "ws://x/\n"]
        with patch("networking.client.connect") as transport:
            for url in invalid:
                with self.subTest(url=url):
                    client = self.make_client(url)
                    self.assertFalse(client.start())
                    self.assertEqual(client.poll()[0]["type"], "error")
            self.assertFalse(self.make_client(name="x" * 21).start())
            self.assertFalse(self.make_client().start("join", "../bad"))
            self.assertFalse(self.make_client().start("unknown"))
            client = self.make_client()
            self.assertFalse(client.send("ready"))
            self.assertFalse(client.reconnect())
            transport.assert_not_called()

    def test_slow_connect_close_and_restart_are_nonblocking_and_ignore_old_worker(self):
        entered, release = threading.Event(), threading.Event()
        old = FakeConnection([welcome("AAAAAA")])
        new = FakeConnection([welcome("BBBBBB", "new-secret"), state("BBBBBB")])
        calls = []

        def connector(*args, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                entered.set()
                release.wait(4)
                return old
            return new

        client = self.make_client("wss://example.org/game")
        with patch("networking.client.connect", side_effect=connector):
            started = time.perf_counter()
            self.assertTrue(client.start())
            self.assertLess(time.perf_counter() - started, 0.2)
            self.assertTrue(entered.wait(1))
            worker = client._thread
            started = time.perf_counter()
            client.close()
            self.assertTrue(client.start("join", "BBBBBB"))
            self.assertFalse(client.send("ready"))
            self.assertLess(time.perf_counter() - started, 0.2)
            self.assertIs(client._thread, worker)
            release.set()
            self.wait_for(client, lambda event: event["type"] == "state")
            self.assertEqual(client.room, "BBBBBB")
            self.assertEqual(client.token, "new-secret")
            self.assertTrue(old.closed)
            self.assertEqual(old.sent, [])
            self.assertEqual(new.sent[0]["type"], "join")
            self.assertTrue(all(call["proxy"] is None for call in calls))
            self.assertTrue(all("ssl" not in call for call in calls))
            self.assertTrue(all(call["max_size"] == 1024 * 1024 for call in calls))
            self.assertNotIn("new-secret", json.dumps(self.events[client]))

    def test_move_queue_is_bounded_and_manual_resume_does_not_replay(self):
        release = threading.Event()
        first = FakeConnection([welcome(), state()], block_after_messages=release)
        resumed = FakeConnection([welcome(), state(revision=3)])
        client = self.make_client()
        with patch("networking.client.connect", side_effect=[first, resumed]):
            client.start()
            self.wait_for(client, lambda event: event["type"] == "state")
            self.assertTrue(first.blocked.wait(1))
            for _ in range(MAX_PENDING_SENDS):
                self.assertTrue(client.send("move", revision=1, start=[1, 0], end=[2, 0]))
            self.assertFalse(client.send("ready"))
            self.assertEqual(client.poll()[0]["code"], "client_busy")
            old_token = client.token
            client.close()
            self.assertEqual(client.token, old_token)
            self.assertTrue(client.reconnect())
            release.set()
            self.wait_for(client, lambda event: event["type"] == "state" and event["revision"] == 3)
            self.assertEqual([message["type"] for message in first.sent], ["create"])
            self.assertEqual([message["type"] for message in resumed.sent], ["resume"])
            self.assertEqual(resumed.sent[0]["token"], old_token)
            self.assertFalse(client.reconnect())

    def test_graceful_leave_is_sent_by_worker_before_close(self):
        release = threading.Event()
        transport = FakeConnection([welcome(), state()], block_after_messages=release)
        client = self.make_client()
        with patch("networking.client.connect", return_value=transport):
            client.start()
            self.wait_for(client, lambda event: event["type"] == "state")
            self.assertTrue(transport.blocked.wait(1))
            client.close(leave=True)
            self.assertFalse(client.connected)
            release.set()
            self.wait_until(lambda: client._thread is None)
        self.assertEqual([message["type"] for message in transport.sent], ["create", "leave"])
        self.assertTrue(transport.closed)

    def test_malformed_or_oversized_frames_recover_on_new_start(self):
        bad_frames = ["not JSON", "[]", b"binary", "x" * (MAX_MESSAGE_BYTES + 1), json.dumps({"type": "state"})]
        for raw in bad_frames:
            with self.subTest(frame_type=type(raw).__name__, frame_length=len(raw)):
                bad = FakeConnection([raw])
                good = FakeConnection([welcome(), state()])
                client = self.make_client()
                with patch("networking.client.connect", side_effect=[bad, good]):
                    client.start()
                    self.wait_for(client, lambda event: event["type"] == "connection" and event["status"] == "error")
                    self.wait_until(lambda: client._thread is None)
                    self.assertFalse(client.connected)
                    self.assertTrue(client.start())
                    self.wait_for(client, lambda event: event["type"] == "state")
                    self.assertTrue(client.connected)
                    client.close()
                    self.wait_until(lambda: client._thread is None)

    def test_handshake_deadline_and_raw_exception_never_expose_secrets(self):
        client = self.make_client()
        with patch("networking.client.connect", side_effect=OSError("secret-value private-token-for-tests")):
            client.start()
            event = self.wait_for(client, lambda item: item["type"] == "connection")
            self.assertEqual(event["status"], "error")
            self.assertNotIn("secret-value", str(event))
            self.wait_until(lambda: client._thread is None)
        with patch("networking.client.connect", return_value=FakeConnection()), patch("networking.client.HANDSHAKE_TIMEOUT", 0.03):
            client.start()
            self.wait_for(client, lambda item: item["type"] == "connection" and item["status"] == "error")
            self.wait_until(lambda: client._thread is None)

    def test_receive_backlog_is_bounded_and_requires_fresh_sync(self):
        messages = [welcome()] + [state(revision=index) for index in range(MAX_EVENTS + 20)]
        transport = FakeConnection(messages)
        client = self.make_client()
        with patch("networking.client.connect", return_value=transport):
            client.start()
            self.wait_until(lambda: client._thread is None)
        events = client.poll()
        self.assertLessEqual(len(events), MAX_EVENTS)
        self.assertTrue(any(event.get("status") == "error" for event in events))
        self.assertFalse(client.connected)
        self.assertTrue(client.token)

    def test_rejected_handshake_closes_promptly_and_can_be_retried(self):
        rejected = FakeConnection([{"type": "error", "code": "room_full", "message": "untrusted token"}])
        accepted = FakeConnection([welcome(), state()])
        client = self.make_client()
        with patch("networking.client.connect", side_effect=[rejected, accepted]):
            client.start("join", "ABCDEF")
            error = self.wait_for(client, lambda event: event["type"] == "error")
            self.assertEqual(error["code"], "room_full")
            self.wait_until(lambda: client._thread is None, timeout=0.5)
            self.assertTrue(rejected.closed)
            client.start()
            self.wait_for(client, lambda event: event["type"] == "state")

    def test_untrusted_snapshot_schema_and_error_text_are_sanitized(self):
        valid = state()
        valid["token"] = "secret"
        valid["players"]["black"]["token"] = "secret"
        sanitized = NetworkClient._decode(json.dumps(valid))
        self.assertNotIn("secret", str(sanitized))
        for mutate in (
            lambda value: value.update(version=True),
            lambda value: value.update(board=["invalid"] * 6),
            lambda value: value.update(revision=-1),
            lambda value: value.update(players={}),
            lambda value: value.update(moves=[{}]),
            lambda value: value.update(result={"winner": "intruder", "reason": "bad"}),
            lambda value: value.pop("result"),
        ):
            invalid = copy.deepcopy(state())
            mutate(invalid)
            with self.assertRaises(_ProtocolError):
                NetworkClient._decode(json.dumps(invalid))
        for code in ("invalid_token", "private_token_for_tests"):
            error = NetworkClient._decode(json.dumps({"type": "error", "code": code, "message": "private-token-for-tests"}))
            self.assertNotIn("private", str(error))

    def test_outgoing_move_validation_copies_coordinates(self):
        release = threading.Event()
        transport = FakeConnection([welcome(), state()], block_after_messages=release)
        client = self.make_client()
        with patch("networking.client.connect", return_value=transport):
            client.start()
            self.wait_for(client, lambda event: event["type"] == "state")
            self.assertTrue(transport.blocked.wait(1))
            self.assertFalse(client.send("move", revision=True, start=[1, 0], end=[2, 0]))
            self.assertFalse(client.send("move", revision=1, start=[1, 0], end=[6, 0]))
            self.assertFalse(client.send("move", revision=1, start=[1, 0], end=[2, 0], capture=True))
            self.assertFalse(client.send("ready", token="hidden"))
            start = [1, 0]
            self.assertTrue(client.send("move", revision=1, start=start, end=[2, 0]))
            start[0] = 5
            release.set()
            self.wait_until(lambda: len(transport.sent) == 2)
            self.assertEqual(transport.sent[1]["start"], [1, 0])


class NetworkClientSocketTests(ClientCase):
    @classmethod
    def setUpClass(cls):
        from networking.server import EmbeddedServer
        cls.server = EmbeddedServer("127.0.0.1", 0, reconnect_seconds=10, cleanup_interval=0.05, rate_limit=200).start()
        cls.address = f"ws://127.0.0.1:{cls.server.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def create_game(self):
        black = self.make_client(self.address, "黑方")
        red = self.make_client(self.address, "红方")
        black.start()
        self.wait_for(black, lambda event: event["type"] == "state")
        red.start("join", black.room)
        self.wait_for(red, lambda event: event["type"] == "state")
        self.assertTrue(black.send("ready"))
        self.assertTrue(red.send("ready"))
        playing = self.wait_for(black, lambda event: event["type"] == "state" and event["status"] == "playing")
        self.wait_for(red, lambda event: event["type"] == "state" and event["status"] == "playing")
        return black, red, playing

    def test_real_create_join_ready_move_resume_and_leave(self):
        black, red, playing = self.create_game()
        self.assertEqual((black.color, red.color), ("black", "red"))
        self.assertTrue(black.send("move", revision=playing["revision"], start=[1, 0], end=[2, 0]))
        moved_black = self.wait_for(black, lambda event: event["type"] == "state" and event["ply"] == 1)
        moved_red = self.wait_for(red, lambda event: event["type"] == "state" and event["ply"] == 1)
        self.assertEqual(moved_black, moved_red)
        self.assertEqual(moved_red["board"][2][0], "B")
        self.assertEqual(moved_red["turn"], "red")
        token = red.token
        red.close()
        self.wait_for(black, lambda event: event["type"] == "state" and not event["players"]["red"]["connected"])
        self.assertTrue(red.reconnect())
        restored = self.wait_for(red, lambda event: event["type"] == "state")
        self.assertEqual(restored["board"], moved_red["board"])
        self.assertEqual(restored["ply"], 1)
        self.assertEqual(red.token, token)
        self.assertNotIn(token, json.dumps(self.events[red]))
        red.close(leave=True)
        finished = self.wait_for(black, lambda event: event["type"] == "state" and event["status"] == "finished")
        self.assertEqual(finished["result"]["winner"], "black")

    def test_real_stale_move_does_not_change_board_and_sync_recovers(self):
        black, red, playing = self.create_game()
        self.assertTrue(black.send("move", revision=0, start=[1, 0], end=[2, 0]))
        error = self.wait_for(black, lambda event: event["type"] == "error")
        self.assertEqual(error["code"], "stale_revision")
        # The state might share the error's poll batch; ask for another copy.
        self.assertTrue(black.send("sync"))
        unchanged = self.wait_for(black, lambda event: event["type"] == "state")
        self.assertEqual(unchanged["board"], playing["board"])
        self.assertEqual(unchanged["ply"], 0)
        self.assertTrue(red.send("resign"))
        finished = self.wait_for(black, lambda event: event["type"] == "state" and event["status"] == "finished")
        self.assertEqual(finished["result"]["winner"], "black")


if __name__ == "__main__":
    unittest.main()
