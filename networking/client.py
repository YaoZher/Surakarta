"""Threaded WebSocket transport; the game thread only submits and polls.

Credentials live only on this object. Reconnection is explicit and never
replays a queued move. A single worker serializes connection replacements so
an old connection cannot overwrite a freshly started session.
"""

from __future__ import annotations

import json
import logging
import queue
import re
import ssl
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from websockets.exceptions import ConnectionClosed, InvalidHandshake
from websockets.sync.client import connect


MAX_MESSAGE_BYTES = 1024 * 1024
MAX_EVENTS = 128
MAX_PENDING_SENDS = 32
OPEN_TIMEOUT = 3.0
CLOSE_TIMEOUT = 0.25
RECEIVE_INTERVAL = 0.05
HANDSHAKE_TIMEOUT = 5.0
_COLORS = ("black", "red")
_ROOM = re.compile(r"[A-Z0-9]{1,12}\Z")
_LOGGER = logging.getLogger("surakarta.network.client.private")
_LOGGER.addHandler(logging.NullHandler())
_LOGGER.propagate = False
_LOGGER.setLevel(logging.CRITICAL)


def validate_url(url: str) -> str:
    """Return a normalized ws/wss URL without credentials or fragments."""
    if not isinstance(url, str) or not 1 <= len(url) <= 2048:
        raise ValueError("请输入有效的服务器地址。")
    if any(ord(char) < 32 or ord(char) == 127 for char in url):
        raise ValueError("服务器地址不能含控制字符。")
    url = url.strip()
    if any(ord(char) < 33 or ord(char) == 127 for char in url):
        raise ValueError("服务器地址不能含空格或控制字符。")
    try:
        parts = urlsplit(url)
        port = parts.port
        valid = (
            parts.scheme in ("ws", "wss") and bool(parts.hostname)
            and parts.username is None and parts.password is None
            and not parts.fragment and "#" not in url
            and "\\" not in url
            and (port is None or 1 <= port <= 65535)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("地址须为 ws:// 或 wss://，且不能包含登录信息或片段。")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def _integer(value: object, maximum: int = 1_000_000) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _coordinate(value: object) -> bool:
    return (
        isinstance(value, (list, tuple)) and len(value) == 2
        and all(_integer(part, 5) for part in value)
    )


def _name(value: object) -> bool:
    return (
        isinstance(value, str) and 1 <= len(value.strip()) <= 20
        and all(ord(char) >= 32 and ord(char) != 127 for char in value)
    )


def _room(value: object) -> bool:
    return isinstance(value, str) and _ROOM.fullmatch(value) is not None


class _ProtocolError(Exception):
    pass


@dataclass
class _Session:
    url: str
    handshake: dict = field(repr=False)
    stop: threading.Event = field(default_factory=threading.Event)
    outgoing: queue.Queue = field(default_factory=lambda: queue.Queue(MAX_PENDING_SENDS))
    leave_on_close: bool = False


class NetworkClient:
    """Nonblocking game-facing API, with one worker per client object.

    ``close(leave=True)`` asks the worker to send a final leave before closing.
    This is best effort when the peer is reachable. The default close merely
    disconnects, retaining the seat's in-memory resume credential.
    """

    def __init__(self, url: str, name: str = "玩家"):
        self.url = url
        self.name = name
        self.room = ""
        self.color = ""
        self.token = ""
        self.connected = False
        self._lock = threading.RLock()
        self._events: deque[dict] = deque()
        self._session: _Session | None = None
        self._thread: threading.Thread | None = None

    def start(self, mode: str = "create", room: str = "") -> bool:
        """Schedule a fresh create/join; validation failures become events."""
        try:
            url = validate_url(self.url)
        except ValueError as error:
            self._local_error("invalid_address", str(error))
            return False
        if not _name(self.name):
            self._local_error("invalid_name", "昵称须为 1 至 20 个字符，不能包含控制字符。")
            return False
        if mode not in ("create", "join"):
            self._local_error("invalid_mode", "请选择创建房间或加入房间。")
            return False
        room = room.strip().upper() if isinstance(room, str) else ""
        if mode == "join" and not _room(room):
            self._local_error("invalid_room", "请输入有效的房间码。")
            return False
        handshake = {"type": mode, "version": 1, "name": self.name.strip()}
        if mode == "join":
            handshake["room"] = room
        self._launch(_Session(url, handshake))
        return True

    def reconnect(self) -> bool:
        """Explicitly resume a seat; no earlier command is carried over."""
        with self._lock:
            if self.connected:
                self._local_error("already_connected", "当前已经连接，无需重连。")
                return False
            room, token = self.room, self.token
        if not room or not token:
            self._local_error("no_resume_token", "尚无可恢复的房间，请先创建或加入房间。")
            return False
        try:
            url = validate_url(self.url)
        except ValueError as error:
            self._local_error("invalid_address", str(error))
            return False
        self._launch(_Session(url, {"type": "resume", "version": 1, "room": room, "token": token}))
        return True

    def send(self, message_type: str, **fields) -> bool:
        """Queue a command, returning False when offline, invalid, or full."""
        if message_type not in ("ready", "move", "resign", "leave", "sync"):
            self._local_error("invalid_command", "不支持此联机操作。")
            return False
        if message_type == "move":
            if (
                set(fields) != {"revision", "start", "end"}
                or not _integer(fields.get("revision"))
                or not _coordinate(fields.get("start"))
                or not _coordinate(fields.get("end"))
            ):
                self._local_error("invalid_move", "走棋信息无效，请同步棋盘后重试。")
                return False
            fields = {"revision": fields["revision"], "start": list(fields["start"]), "end": list(fields["end"])}
        elif fields:
            self._local_error("invalid_command", "联机操作参数无效。")
            return False
        with self._lock:
            session = self._session
            if not self.connected or session is None or session.stop.is_set():
                self._local_error("not_connected", "尚未连接房间，请连接或手动重连后重试。")
                return False
            try:
                session.outgoing.put_nowait({"type": message_type, **fields})
            except queue.Full:
                self._local_error("client_busy", "发送队列已满，本次操作未发送，请稍后重试。")
                return False
            return True

    def poll(self) -> list[dict]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def close(self, leave: bool = False) -> None:
        """Signal shutdown without waiting on DNS, sockets, or a thread join."""
        with self._lock:
            session = self._session
            if session is not None:
                session.leave_on_close = bool(leave)
                session.stop.set()
                self._session = None
            self.connected = False
            self._events.clear()
            self._events.append({"type": "connection", "status": "disconnected", "message": "连接已关闭。"})

    def _launch(self, session: _Session) -> None:
        with self._lock:
            if self._session is not None:
                self._session.stop.set()
            self._session = session
            self.connected = False
            self._events.clear()
            if self._thread is None:
                self._thread = threading.Thread(target=self._work, name="SurakartaNetworkClient", daemon=True)
                self._thread.start()

    def _local_error(self, code: str, message: str) -> None:
        with self._lock:
            self._append({"type": "error", "code": code, "message": message})

    def _append(self, event: dict) -> None:
        # Call only under _lock. Losing a move acknowledgement silently would
        # be unsafe; stop instead and obtain a fresh snapshot on manual resume.
        if len(self._events) >= MAX_EVENTS:
            if self._session is not None:
                self._session.stop.set()
            self.connected = False
            self._events.clear()
            self._events.append({"type": "connection", "status": "error", "message": "消息积压过多，连接已暂停，请手动重连以同步棋盘。"})
        else:
            self._events.append(event)

    def _publish(self, session: _Session, event: dict) -> bool:
        with self._lock:
            if self._session is not session or session.stop.is_set():
                return False
            self._append(event)
            return not session.stop.is_set()

    def _work(self) -> None:
        while True:
            with self._lock:
                session = self._session
                if session is None:
                    self._thread = None
                    return
            self._run_session(session)
            with self._lock:
                if self._session is session:
                    self._session = None
                    self.connected = False

    def _run_session(self, session: _Session) -> None:
        connection = None
        handshake_sent = False
        welcomed = False
        try:
            connection = connect(
                session.url, proxy=None, open_timeout=OPEN_TIMEOUT,
                close_timeout=CLOSE_TIMEOUT, max_size=MAX_MESSAGE_BYTES,
                max_queue=16, ping_interval=20, ping_timeout=20,
                compression=None, logger=_LOGGER,
            )
            if session.stop.is_set():
                return
            connection.send(json.dumps(session.handshake, ensure_ascii=False))
            handshake_sent = True
            handshake_deadline = time.monotonic() + HANDSHAKE_TIMEOUT
            last_revision = -1
            while not session.stop.is_set():
                if not welcomed and time.monotonic() >= handshake_deadline:
                    raise TimeoutError
                # Limit each send batch so incoming snapshots cannot starve.
                for _ in range(8):
                    if session.stop.is_set():
                        break
                    try:
                        outgoing = session.outgoing.get_nowait()
                    except queue.Empty:
                        break
                    connection.send(json.dumps(outgoing, ensure_ascii=False))
                try:
                    raw = connection.recv(timeout=RECEIVE_INTERVAL)
                except TimeoutError:
                    continue
                event = self._decode(raw)
                kind = event["type"]
                if kind == "welcome":
                    if welcomed:
                        raise _ProtocolError
                    welcomed = True
                    with self._lock:
                        if self._session is not session or session.stop.is_set():
                            return
                        self.room, self.color, self.token = event["room"], event["color"], event.pop("token")
                        self.connected = True
                    self._publish(session, event)
                    self._publish(session, {"type": "connection", "status": "connected", "message": "已连接房间。"})
                elif kind == "state":
                    if not welcomed or event["room"] != self.room or event["revision"] < last_revision:
                        raise _ProtocolError
                    last_revision = event["revision"]
                    self._publish(session, event)
                else:
                    self._publish(session, event)
                    if not welcomed:
                        return
        except _ProtocolError:
            self._publish(session, {"type": "connection", "status": "error", "message": "服务器消息格式无效，连接已断开；请检查服务器或手动重连。"})
        except ssl.SSLError:
            self._publish(session, {"type": "connection", "status": "error", "message": "安全连接失败，请检查服务器证书和地址。"})
        except ConnectionClosed:
            self._publish(session, {"type": "connection", "status": "disconnected", "message": "与服务器的连接已断开，可手动重连。"})
        except (OSError, TimeoutError, InvalidHandshake):
            self._publish(session, {"type": "connection", "status": "error", "message": "无法连接服务器，请检查地址、网络和服务器状态。"})
        except Exception:
            # Never display a raw transport exception, URL, or resume token.
            self._publish(session, {"type": "connection", "status": "error", "message": "联机连接发生错误，请手动重连。"})
        finally:
            with self._lock:
                if self._session is session:
                    self.connected = False
            if connection is not None:
                try:
                    if session.leave_on_close and handshake_sent:
                        connection.send('{"type":"leave"}')
                    connection.close()
                except Exception:
                    # Ensure protocol receiver/keepalive threads also terminate.
                    try:
                        connection.close_socket()
                    except Exception:
                        pass

    @staticmethod
    def _decode(raw: object) -> dict:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise _ProtocolError
        try:
            event = json.loads(raw)
        except (ValueError, RecursionError) as error:
            raise _ProtocolError from error
        if not isinstance(event, dict):
            raise _ProtocolError
        kind = event.get("type")
        if kind == "error":
            code = event.get("code")
            if not isinstance(code, str) or not re.fullmatch(r"[a-zA-Z0-9_]{1,64}", code):
                raise _ProtocolError
            # The server's free-form text may contain echoed input/secrets.
            messages = {
                "room_not_found": "房间不存在或已关闭，请确认房间码。",
                "room_full": "房间已满，请确认房间码。",
                "invalid_token": "无法恢复此座位，请重新加入房间。",
                "seat_connected": "此座位仍在线，请稍候再重连。",
                "resume_expired": "重连期限已过，请重新创建或加入房间。",
                "server_full": "服务器已满，请稍后重试。",
                "stale_revision": "棋盘已更新，本次走棋未接受，请根据最新棋盘重试。",
                "wrong_turn": "还未轮到你走棋。",
                "illegal_move": "此走法不合法，请重新选择。",
                "invalid_coordinate": "走棋坐标无效，请重新选择。",
                "not_ready": "请等待双方就绪后走棋。",
                "opponent_disconnected": "对手已断开，等待对手重连。",
                "rate_limited": "操作过于频繁，请稍后重试。",
            }
            return {"type": "error", "code": code if code in messages else "server_error", "message": messages.get(code, "服务器未接受本次操作，请确认房间状态后重试。")}
        if event.get("version") != 1 or type(event.get("version")) is not int or not _room(event.get("room")):
            raise _ProtocolError
        if kind == "welcome":
            token = event.get("token")
            if event.get("color") not in _COLORS or not isinstance(token, str) or not 1 <= len(token) <= 256:
                raise _ProtocolError
            return {key: event[key] for key in ("type", "version", "room", "color", "token")}
        if kind != "state":
            raise _ProtocolError
        keys = ("type", "version", "room", "revision", "status", "board", "turn", "ply", "players", "moves", "result", "reconnect_seconds")
        if any(key not in event for key in keys):
            raise _ProtocolError
        board = event.get("board")
        if (
            not isinstance(board, list) or len(board) != 6
            or any(not isinstance(row, str) or len(row) != 6 or set(row) - set("BR.") for row in board)
            or event.get("turn") not in _COLORS
            or event.get("status") not in ("waiting", "playing", "finished")
            or not _integer(event.get("revision")) or not _integer(event.get("ply"))
            or not _integer(event.get("reconnect_seconds"), 86400)
        ):
            raise _ProtocolError
        players = event.get("players")
        if not isinstance(players, dict) or set(players) != set(_COLORS):
            raise _ProtocolError
        for color in _COLORS:
            player = players[color]
            if player is None and color == "red":
                continue
            if (
                not isinstance(player, dict) or not _name(player.get("name"))
                or type(player.get("connected")) is not bool or type(player.get("ready")) is not bool
            ):
                raise _ProtocolError
        moves = event.get("moves")
        if not isinstance(moves, list) or len(moves) > 4096:
            raise _ProtocolError
        for move in moves:
            if (
                not isinstance(move, dict) or not _coordinate(move.get("start"))
                or not _coordinate(move.get("end")) or move.get("color") not in _COLORS
                or type(move.get("capture")) is not bool
                or not isinstance(move.get("text"), str) or len(move["text"]) > 32
            ):
                raise _ProtocolError
        result = event.get("result")
        if result is not None and (
            not isinstance(result, dict) or result.get("winner") not in (*_COLORS, None)
            or not isinstance(result.get("reason"), str) or len(result["reason"]) > 80
        ):
            raise _ProtocolError
        # Forward only documented fields; arbitrary extra server data is not
        # exposed to the game or accidentally retained in a replay.
        cleaned = {key: event[key] for key in keys}
        cleaned["players"] = {
            color: None if players[color] is None else {
                key: players[color][key] for key in ("name", "connected", "ready")
            } for color in _COLORS
        }
        cleaned["moves"] = [
            {key: move[key] for key in ("start", "end", "color", "capture", "text")}
            for move in moves
        ]
        cleaned["result"] = None if result is None else {
            key: result[key] for key in ("winner", "reason")
        }
        return cleaned
