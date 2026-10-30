"""Authoritative, in-memory rooms shared by LAN hosting and standalone service."""
from __future__ import annotations

import asyncio
from collections import Counter, deque
from dataclasses import dataclass, field
import errno
import json
import math
import os
import secrets
import socket
import threading
import time
from typing import Any

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from engine.board import BoardState, Color, opponent

VERSION = 1
COLORS = {"black": Color.BLACK, "red": Color.RED}


async def _exclusive_windows_sockets(host: str, port: int) -> list[socket.socket]:
    """Reserve all resolved addresses before handing listeners to asyncio.

    Windows permits wildcard/specific address sharing even without REUSEADDR.
    EXCLUSIVEADDRUSE must be set before bind to prevent joining another service.
    """
    addresses = await asyncio.get_running_loop().getaddrinfo(
        host or None, port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE,
    )
    listeners = []
    chosen_port = port
    try:
        for family, socktype, protocol, _, address in dict.fromkeys(addresses):
            try:
                listener = socket.socket(family, socktype, protocol)
            except OSError as error:
                if error.errno in (errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT):
                    continue
                raise
            listeners.append(listener)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            if family == socket.AF_INET6:
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            address = (address[0], chosen_port, *address[2:])
            try:
                listener.bind(address)
            except OSError as error:
                if error.errno == errno.EADDRNOTAVAIL:
                    listeners.pop().close()
                    continue
                raise
            chosen_port = listener.getsockname()[1]
            listener.setblocking(False)
        if not listeners:
            raise OSError("No usable listening address")
        return listeners
    except BaseException:
        for listener in listeners:
            listener.close()
        raise


class RequestError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class Player:
    name: str
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    socket: Any = field(default=None, repr=False)
    ready: bool = False
    disconnected_at: float | None = None


@dataclass
class Room:
    code: str
    black: Player
    red: Player | None = None
    board: BoardState = field(default_factory=BoardState.initial)
    revision: int = 0
    status: str = "waiting"
    moves: list = field(default_factory=list)
    result: dict | None = None
    no_capture: int = 0
    positions: Counter = field(default_factory=Counter)
    activity: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def __post_init__(self):
        self.positions[(self.board.cells, self.board.side_to_move)] = 1

    def player(self, color: str) -> Player | None:
        return self.black if color == "black" else self.red


class RoomService:
    """One asyncio event loop owns all rooms. Each room serializes its broadcasts."""

    def __init__(self, *, reconnect_seconds: float = 60, max_rooms: int = 128,
                 max_connections: int = 256, idle_seconds: float = 1800,
                 finished_seconds: float = 300, handshake_seconds: float = 15,
                 rate_limit: int = 40, rate_window: float = 10,
                 cleanup_interval: float = 1, send_timeout: float = 2):
        values = (reconnect_seconds, max_rooms, max_connections, idle_seconds,
                  finished_seconds, handshake_seconds, rate_limit, rate_window,
                  cleanup_interval, send_timeout)
        if any(not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError("Room service limits must be positive finite numbers")
        self.reconnect_seconds = reconnect_seconds
        self.max_rooms, self.max_connections = int(max_rooms), int(max_connections)
        self.idle_seconds, self.finished_seconds = idle_seconds, finished_seconds
        self.handshake_seconds = handshake_seconds
        self.rate_limit, self.rate_window = int(rate_limit), rate_window
        self.cleanup_interval, self.send_timeout = cleanup_interval, send_timeout
        self.rooms: dict[str, Room] = {}
        self.bindings: dict[Any, tuple[Room, str]] = {}
        self.connections: set = set()
        self._servers = []
        self._cleaner = None
        self.host, self.port = "", 0

    async def start(self, host: str = "0.0.0.0", port: int = 8765) -> RoomService:
        if self._servers:
            raise RuntimeError("Service already started")
        options = dict(max_size=4096, max_queue=8,
            compression=None, open_timeout=5, close_timeout=1,
            ping_interval=20, ping_timeout=20, write_limit=32768,
            origins=[None], server_header=None,
        )
        listeners = []
        try:
            if os.name == "nt":
                listeners = await _exclusive_windows_sockets(host, port)
                for listener in listeners:
                    self._servers.append(await serve(self.handle, sock=listener, **options))
            else:
                self._servers.append(await serve(self.handle, host, port, **options))
        except BaseException:
            await self.close()
            for listener in listeners:
                listener.close()
            raise
        self.host = host
        self.port = self._servers[0].sockets[0].getsockname()[1]
        self._cleaner = asyncio.create_task(self._cleanup())
        return self

    async def close(self) -> None:
        if self._cleaner is not None:
            self._cleaner.cancel()
            await asyncio.gather(self._cleaner, return_exceptions=True)
            self._cleaner = None
        servers, self._servers = self._servers, []
        for server in servers:
            server.close()
        await asyncio.gather(*(server.wait_closed() for server in servers))
        self.rooms.clear()

    async def _send(self, socket, payload: dict) -> None:
        try:
            await asyncio.wait_for(socket.send(json.dumps(payload, ensure_ascii=False)),
                                   timeout=self.send_timeout)
        except (ConnectionClosed, asyncio.TimeoutError):
            await socket.close(code=1013, reason="Connection unavailable")

    async def _error(self, socket, code: str, message: str) -> None:
        await self._send(socket, {"type": "error", "code": code, "message": message})

    def snapshot(self, room: Room) -> dict:
        def public(player):
            return None if player is None else {
                "name": player.name, "connected": player.socket is not None,
                "ready": player.ready,
            }
        return {
            "type": "state", "version": VERSION, "room": room.code,
            "revision": room.revision, "status": room.status,
            "board": room.board.to_rows(),
            "turn": "black" if room.board.side_to_move == Color.BLACK else "red",
            "ply": room.board.ply,
            "players": {"black": public(room.black), "red": public(room.red)},
            "moves": room.moves, "result": room.result,
            "reconnect_seconds": math.ceil(self.reconnect_seconds),
        }

    async def _broadcast(self, room: Room) -> None:
        payload = self.snapshot(room)
        await asyncio.gather(*(self._send(p.socket, payload)
                               for p in (room.black, room.red)
                               if p is not None and p.socket is not None))

    @staticmethod
    def _changed(room: Room) -> None:
        room.revision += 1
        room.activity = time.monotonic()

    def _finish(self, room: Room, winner: str | None, reason: str) -> None:
        room.status = "finished"
        room.result = {"winner": winner, "reason": reason}
        room.finished_at = time.monotonic()

    async def handle(self, socket) -> None:
        if len(self.connections) >= self.max_connections:
            await self._error(socket, "server_full", "服务器连接已满")
            await socket.close(code=1013, reason="Server full")
            return
        self.connections.add(socket)
        requests: deque[float] = deque()
        deadline = time.monotonic() + self.handshake_seconds
        try:
            while True:
                try:
                    if socket in self.bindings:
                        raw = await socket.recv()
                    else:
                        remaining = max(0, deadline - time.monotonic())
                        raw = await asyncio.wait_for(socket.recv(), remaining)
                except asyncio.TimeoutError:
                    await self._error(socket, "handshake_timeout", "加入房间超时，请重新连接")
                    return
                now = time.monotonic()
                while requests and requests[0] <= now - self.rate_window:
                    requests.popleft()
                if len(requests) >= self.rate_limit:
                    await self._error(socket, "rate_limited", "请求过于频繁，请稍后重新连接")
                    await socket.close(code=1008, reason="Rate limit")
                    return
                requests.append(now)
                try:
                    if not isinstance(raw, str):
                        raise RequestError("invalid_message", "仅支持 JSON 文本消息")
                    try:
                        data = json.loads(raw)
                    except (ValueError, RecursionError):
                        raise RequestError("invalid_message", "消息不是有效 JSON") from None
                    if not isinstance(data, dict) or not isinstance(data.get("type"), str):
                        raise RequestError("invalid_message", "消息缺少有效类型")
                    if socket in self.bindings:
                        await self._bound_request(socket, data)
                    else:
                        await self._bind(socket, data)
                except RequestError as exc:
                    await self._error(socket, exc.code, exc.message)
        except ConnectionClosed:
            pass
        finally:
            self.connections.discard(socket)
            binding = self.bindings.pop(socket, None)
            if binding is not None:
                room, color = binding
                async with room.lock:
                    player = room.player(color)
                    if player is not None and player.socket is socket:
                        player.socket = None
                        player.disconnected_at = time.monotonic()
                        self._changed(room)
                        await self._broadcast(room)

    @staticmethod
    def _name(data: dict) -> str:
        name = data.get("name", "玩家")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 20:
            raise RequestError("invalid_name", "昵称须为 1 至 20 个字符")
        if any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF
               for char in name):
            raise RequestError("invalid_name", "昵称不能包含控制字符")
        return name.strip()

    async def _bind(self, socket, data: dict) -> None:
        kind = data["type"]
        if kind not in {"create", "join", "resume"}:
            raise RequestError("not_joined", "请先创建或加入房间")
        if type(data.get("version")) is not int or data["version"] != VERSION:
            raise RequestError("version_mismatch", "客户端协议版本不兼容")
        if kind == "create":
            name = self._name(data)
            if len(self.rooms) >= self.max_rooms:
                raise RequestError("server_full", "服务器房间已满，请稍后重试")
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            while code in self.rooms:
                code = "".join(secrets.choice(alphabet) for _ in range(6))
            room = Room(code, Player(name))
            self.rooms[code] = room
            color, player = "black", room.black
        else:
            code = data.get("room")
            if not isinstance(code, str) or len(code) > 16:
                raise RequestError("invalid_room", "房间号无效")
            room = self.rooms.get(code.strip().upper())
            if room is None:
                raise RequestError("room_not_found", "房间不存在或已过期")
            color, player = "", None
        async with room.lock:
            if self.rooms.get(room.code) is not room:
                raise RequestError("room_not_found", "房间不存在或已过期")
            if self._expire_disconnect(room, time.monotonic()):
                self._changed(room)
                await self._broadcast(room)
            if kind == "join":
                if room.status != "waiting" or room.red is not None:
                    raise RequestError("room_full", "房间已满或对局已结束")
                player = Player(self._name(data))
                room.red, color = player, "red"
            elif kind == "resume":
                token = data.get("token")
                if not isinstance(token, str) or len(token) > 128 or not token.isascii():
                    raise RequestError("invalid_token", "重连凭证无效")
                for candidate in ("black", "red"):
                    seat = room.player(candidate)
                    if seat is not None and secrets.compare_digest(seat.token, token):
                        player, color = seat, candidate
                        break
                if player is None:
                    raise RequestError("invalid_token", "重连凭证无效")
                if player.socket is not None:
                    raise RequestError("seat_connected", "该席位仍在线，请稍后重连")
                if (player.disconnected_at is None or
                        time.monotonic() - player.disconnected_at >= self.reconnect_seconds):
                    raise RequestError("resume_expired", "重连时间已过")
            player.socket, player.disconnected_at = socket, None
            if (room.status == "waiting" and room.red is not None and
                    room.black.ready and room.red.ready and
                    room.black.socket is not None and room.red.socket is not None):
                room.status = "playing"
            self.bindings[socket] = room, color
            self._changed(room)
            await self._send(socket, {"type": "welcome", "version": VERSION,
                                     "room": room.code, "color": color, "token": player.token})
            await self._broadcast(room)

    async def _bound_request(self, socket, data: dict) -> None:
        room, color = self.bindings[socket]
        async with room.lock:
            # A deadline takes effect before the next command, even if the
            # cleanup task hasn't visited this room yet.
            if self._expire_disconnect(room, time.monotonic()):
                self._changed(room)
                await self._broadcast(room)
            player = room.player(color)
            kind = data["type"]
            if kind == "sync":
                await self._send(socket, self.snapshot(room))
                return
            if kind == "leave":
                if room.status != "finished":
                    other = "red" if color == "black" else "black"
                    self._finish(room, other if room.player(other) else None, "leave")
                player.token = secrets.token_urlsafe(32)  # Invalidate explicit departure's token.
                player.socket = None
                player.disconnected_at = time.monotonic()
                self.bindings.pop(socket, None)
                self._changed(room)
                await self._send(socket, self.snapshot(room))
                await self._broadcast(room)
                await socket.close(code=1000, reason="Left room")
                return
            if kind not in {"ready", "move", "resign"}:
                raise RequestError("unknown_type", "该请求不适用于已加入的房间")
            if room.status == "finished":
                raise RequestError("game_finished", "对局已结束")
            if kind == "resign":
                other = "red" if color == "black" else "black"
                self._finish(room, other if room.player(other) else None, "resign")
            elif kind == "ready":
                if player.ready:
                    await self._send(socket, self.snapshot(room))
                    return
                player.ready = True
                if (room.red is not None and room.black.ready and room.red.ready and
                        room.black.socket is not None and room.red.socket is not None):
                    room.status = "playing"
            else:
                revision = data.get("revision")
                if type(revision) is not int:
                    raise RequestError("invalid_revision", "落子缺少有效局面版本")
                if revision != room.revision:
                    await self._error(socket, "stale_revision", "局面已更新，请按最新棋盘落子")
                    await self._send(socket, self.snapshot(room))
                    return
                self._move(room, color, data)
            self._changed(room)
            await self._broadcast(room)

    @staticmethod
    def _coordinate(value) -> tuple[int, int]:
        if (not isinstance(value, list) or len(value) != 2 or
                any(type(n) is not int or not 0 <= n < 6 for n in value)):
            raise RequestError("invalid_coordinate", "棋盘坐标须为 0 至 5 的整数")
        return tuple(value)

    def _move(self, room: Room, color: str, data: dict) -> None:
        if room.status != "playing":
            raise RequestError("not_ready", "双方准备完成后才能落子")
        if room.red is None or any(p.socket is None for p in (room.black, room.red)):
            raise RequestError("opponent_disconnected", "对方已断线，对局暂停")
        if room.board.side_to_move != COLORS[color]:
            raise RequestError("wrong_turn", "尚未轮到你落子")
        start, end = self._coordinate(data.get("start")), self._coordinate(data.get("end"))
        move = next((m for m in room.board.legal_moves() if m.start == start and m.end == end), None)
        if move is None:
            raise RequestError("illegal_move", "该走法不符合规则")
        room.board = room.board.apply(move)
        room.no_capture = 0 if move.is_capture else room.no_capture + 1
        text = (f"{'B' if color == 'black' else 'R'}{start[0]+1}{chr(65+start[1])}"
                f"-{end[0]+1}{chr(65+end[1])}")
        room.moves.append({"start": list(start), "end": list(end), "color": color,
                           "capture": move.is_capture, "text": text})
        position = room.board.cells, room.board.side_to_move
        room.positions[position] += 1
        if room.board.count(opponent(COLORS[color])) == 0:
            self._finish(room, color, "no_pieces")
        elif not room.board.legal_moves():
            self._finish(room, color, "no_legal_moves")
        elif room.positions[position] >= 3:
            self._finish(room, None, "threefold_repetition")
        elif room.no_capture >= 80:
            self._finish(room, None, "no_capture_80")

    def _expire_disconnect(self, room: Room, now: float) -> bool:
        """Enforce grace deadlines on access as well as during periodic cleanup."""
        if room.status == "finished":
            return False
        players = [p for p in (room.black, room.red) if p is not None]
        if not any(p.socket is None and p.disconnected_at is not None and
                   now - p.disconnected_at >= self.reconnect_seconds for p in players):
            return False
        connected = [c for c in ("black", "red")
                     if room.player(c) and room.player(c).socket is not None]
        winner = connected[0] if len(connected) == 1 and len(players) == 2 else None
        self._finish(room, winner, "disconnect_timeout" if winner else "abandoned")
        return True

    async def _cleanup(self) -> None:
        while True:
            await asyncio.sleep(self.cleanup_interval)
            for room in list(self.rooms.values()):
                async with room.lock:
                    now = time.monotonic()
                    players = [p for p in (room.black, room.red) if p is not None]
                    if self._expire_disconnect(room, now):
                        self._changed(room)
                        await self._broadcast(room)
                    if room.status != "finished" and now - room.activity >= self.idle_seconds:
                        self._finish(room, None, "idle_timeout")
                        self._changed(room)
                        await self._broadcast(room)
                    if room.finished_at is not None and now - room.finished_at >= self.finished_seconds:
                        self.rooms.pop(room.code, None)
                        for p in players:
                            if p.socket is not None:
                                self.bindings.pop(p.socket, None)
                                await p.socket.close(code=1000, reason="Room expired")


class EmbeddedServer:
    """Run RoomService in a daemon thread; start waits for bind or raises its error."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765, **options):
        self.host, self.port, self.options = host, port, options
        self._thread = None
        self._ready = threading.Event()
        self._stop_requested = threading.Event()
        self._loop = None
        self._stop_event = None
        self._error = None

    def start(self) -> EmbeddedServer:
        if self._thread is not None:
            raise RuntimeError("Embedded server already started")
        self._thread = threading.Thread(target=self._worker, name="surakarta-room-server", daemon=True)
        self._thread.start()
        if not self._ready.wait(10):
            self.stop()
            raise TimeoutError("Room server startup timed out")
        if self._error is not None:
            raise self._error
        return self

    def _worker(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:
            self._error = exc
        finally:
            self._ready.set()

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        service = RoomService(**self.options)
        try:
            await service.start(self.host, self.port)
            self.port = service.port
            self._ready.set()
            if not self._stop_requested.is_set():
                await self._stop_event.wait()
        finally:
            await service.close()

    def stop(self) -> None:
        self._stop_requested.set()
        if self._loop is not None and self._stop_event is not None:
            try:
                self._loop.call_soon_threadsafe(self._stop_event.set)
            except RuntimeError:
                pass  # Already stopped.
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=10)
            if self._thread.is_alive():
                raise TimeoutError("Room server did not stop in time")
