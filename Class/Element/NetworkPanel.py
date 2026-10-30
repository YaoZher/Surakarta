"""Room setup and session controls. Networking belongs to GameManage."""
from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

import pygame

from Class import Theme, I18n


class NetworkPanel:
    MODES = (("host", "局域网建房"), ("join_lan", "局域网加入"), ("online", "在线房间"))
    LIMITS = {"name": 20, "port": 5, "lan_address": 512, "online_address": 512, "room": 16}
    STATUS_LABELS = {
        "waiting": "等待双方准备", "playing": "对局进行中", "finished": "对局已结束",
        "connecting": "正在连接…", "connected": "已连接", "disconnected": "连接已断开，请尝试重连",
        "error": "连接失败，请查看下方提示",
    }

    def __init__(self):
        self.visible = False
        self.active = False
        self.mode = "host"
        self.message = ""
        self.room = self.color = self.status = self.address = ""
        self.values = {"name": I18n.translate("玩家"), "port": "8765", "lan_address": "127.0.0.1:8765",
                       "online_address": "", "room": ""}
        self.focus: str | None = None
        self.cursor = 0
        self.select_all = False
        self.composition = ""
        self.hovered: str | None = None
        self._error = False
        self._fonts = {}
        self.card = pygame.Rect(250, 50, 900, 600)
        self.close_rect = pygame.Rect(1080, 68, 44, 44)
        self.tab_rects = {key: pygame.Rect(282 + index * 280, 142, 276, 42)
                          for index, (key, _) in enumerate(self.MODES)}
        self.field_rects = {
            "name": pygame.Rect(282, 231, 410, 44),
            "port": pygame.Rect(708, 231, 410, 44),
            "room": pygame.Rect(708, 231, 410, 44),
            "lan_address": pygame.Rect(282, 322, 836, 44),
            "online_address": pygame.Rect(282, 322, 836, 44),
        }
        self.action_rects = {
            "host": pygame.Rect(922, 574, 196, 44),
            "join_lan": pygame.Rect(922, 574, 196, 44),
            "create": pygame.Rect(710, 574, 196, 44),
            "join": pygame.Rect(922, 574, 196, 44),
            "ready": pygame.Rect(282, 574, 196, 44),
            "reconnect": pygame.Rect(496, 574, 196, 44),
            "resign": pygame.Rect(708, 574, 196, 44),
            "leave": pygame.Rect(922, 574, 196, 44),
            "copy_room": pygame.Rect(930, 186, 188, 40),
            "copy_address": pygame.Rect(982, 294, 136, 44),
        }
        self._layout_language = 'zh'
        self._sync_layout()

    def _sync_layout(self):
        if self._layout_language == I18n.language():
            return
        for rect in [self.close_rect, *self.tab_rects.values(), *self.field_rects.values(), *self.action_rects.values()]:
            rect.left = self.card.left + self.card.right - rect.right
        self._layout_language = I18n.language()

    def _rect(self, rect):
        return I18n.mirror_rect(rect, self.card)

    def open(self, active=False, room="", color="", status="", address="") -> None:
        self._sync_layout()
        self.visible = True
        self.hovered = None
        self.message = ""
        self._error = False
        self.set_session(room=room, color=color, status=status, address=address, active=active)
        self._focus(None if active else "name")

    def set_session(self, room="", color="", status="", address="", active=True) -> None:
        self.active = bool(active)
        self.room, self.color, self.status, self.address = str(room), str(color), str(status), str(address)
        if self.active:
            self._focus(None)

    def close(self) -> None:
        self.visible = False
        self.hovered = None
        self._focus(None)

    def _fields(self) -> tuple[str, ...]:
        if self.active:
            return ()
        if self.mode == "host":
            return ("name", "port")
        return ("name", "room", "lan_address" if self.mode == "join_lan" else "online_address")

    def _actions(self) -> tuple[str, ...]:
        if self.active:
            return ("ready", "reconnect", "resign", "leave", "copy_room", "copy_address")
        return ("create", "join") if self.mode == "online" else (self.mode,)

    def _enabled(self, action: str) -> bool:
        if action == "ready":
            return self.status in {"waiting", "connected"}
        if action == "reconnect":
            return self.status in {"disconnected", "error"}
        if action == "resign":
            return self.status == "playing"
        if action == "copy_room":
            return bool(self.room)
        if action == "copy_address":
            return bool(self.address)
        return True

    def _focus(self, field: str | None) -> None:
        self.focus = field
        self.cursor = len(self.values[field]) if field else 0
        self.select_all = False
        self.composition = ""
        if pygame.display.get_init():
            if field and self.visible:
                pygame.key.start_text_input()
                pygame.key.set_text_input_rect(self.field_rects[field])
            else:
                pygame.key.stop_text_input()

    def _control_at(self, pos) -> str | None:
        if self.close_rect.collidepoint(pos):
            return "close"
        if not self.active:
            for key, rect in self.tab_rects.items():
                if rect.collidepoint(pos):
                    return "tab:" + key
            for key in self._fields():
                if self.field_rects[key].collidepoint(pos):
                    return "field:" + key
        for key in self._actions():
            if self.action_rects[key].collidepoint(pos) and self._enabled(key):
                return key
        return None

    def handle_event(self, event) -> dict | None:
        self._sync_layout()
        if not self.visible:
            return None
        if event.type == pygame.KEYDOWN:
            return self._key(event)
        if event.type == pygame.TEXTINPUT and self.focus:
            self.composition = ""
            self._insert(event.text)
        elif event.type == pygame.TEXTEDITING and self.focus:
            self.composition = event.text[:self.LIMITS[self.focus]]
        elif event.type == pygame.MOUSEMOTION:
            self.hovered = self._control_at(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            control = self._control_at(event.pos)
            if control == "close":
                self.close()
                return {"action": "close"}
            if control and control.startswith("field:"):
                self._focus(control.split(":", 1)[1])
            elif control and control.startswith("tab:"):
                self.mode = control.split(":", 1)[1]
                self.message = ""
                self._error = False
                self._focus("name")
            else:
                self._focus(None)
                if control:
                    return self._activate(control)
        return None

    def _key(self, event) -> dict | None:
        key, mod = event.key, getattr(event, "mod", 0)
        if key == pygame.K_ESCAPE:
            if self.composition:
                self.composition = ""
                return None
            self.close()
            return {"action": "close"}
        if key == pygame.K_TAB and not self.active:
            fields = self._fields()
            step = -1 if mod & pygame.KMOD_SHIFT else 1
            index = fields.index(self.focus) if self.focus in fields else (-1 if step > 0 else 0)
            self._focus(fields[(index + step) % len(fields)])
            return None
        if self.active or not self.focus:
            return None
        field = self.focus
        value = self.values[field]
        if mod & (pygame.KMOD_CTRL | pygame.KMOD_META):
            if key == pygame.K_a:
                self.select_all = True
            elif key == pygame.K_v:
                try:
                    self._insert(self._clipboard_read())
                except (pygame.error, UnicodeError, OSError):
                    self._fail("无法读取剪贴板，请手动输入。")
            elif key == pygame.K_c:
                if self.select_all:
                    self._copy(value, "已复制输入内容")
            return None
        if self.composition:
            return None
        if key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            if self.select_all:
                value, self.cursor = "", 0
            elif key == pygame.K_BACKSPACE and self.cursor:
                value = value[:self.cursor - 1] + value[self.cursor:]
                self.cursor -= 1
            elif key == pygame.K_DELETE:
                value = value[:self.cursor] + value[self.cursor + 1:]
            self.values[field] = value
            self.select_all = False
            self._clear_error()
        elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_HOME, pygame.K_END):
            if key == pygame.K_HOME or (self.select_all and key == pygame.K_LEFT):
                self.cursor = 0
            elif key == pygame.K_END or (self.select_all and key == pygame.K_RIGHT):
                self.cursor = len(value)
            else:
                direction = -1 if key == pygame.K_LEFT else 1
                if field == 'name' and I18n.is_rtl() and I18n.contains_arabic(value):
                    direction = -direction
                self.cursor = max(0, min(len(value), self.cursor + direction))
            self.select_all = False
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.mode == "online":
                return self._activate("join" if self.values["room"].strip() else "create")
            return self._activate(self.mode)
        return None

    def _insert(self, content: str) -> None:
        if not self.focus or self.active:
            return
        field = self.focus
        content = "".join(char for char in str(content) if char.isprintable())
        if field in {"room", "port"}:
            allowed = r"[A-Za-z0-9]" if field == "room" else r"[0-9]"
            content = "".join(char for char in content if re.fullmatch(allowed, char))
        if field == "room":
            content = content.upper()
        if not content:
            return
        value = "" if self.select_all else self.values[field]
        cursor = 0 if self.select_all else self.cursor
        content = content[:max(0, self.LIMITS[field] - len(value))]
        self.values[field] = value[:cursor] + content + value[cursor:]
        self.cursor = cursor + len(content)
        self.select_all = False
        self._clear_error()

    def _clear_error(self) -> None:
        if self._error:
            self.message = ""
            self._error = False

    def _fail(self, message: str) -> None:
        self.message, self._error = message, True

    def _activate(self, action: str) -> dict | None:
        if action not in self._actions() or not self._enabled(action):
            return None
        if action in {"copy_room", "copy_address"}:
            self._copy(self.room if action == "copy_room" else self.address,
                       "已复制房间码" if action == "copy_room" else "已复制地址")
            return None
        if self.active:
            return {"action": action}
        name = self.values["name"].strip()
        if not name or len(name) > self.LIMITS["name"] or not name.isprintable():
            self._fail("请输入 1–20 个字符的昵称。")
            return None
        if action == "host":
            port = self.values["port"].strip()
            if not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= 65535:
                self._fail("端口请输入 1–65535 之间的数字。")
                return None
            self._clear_error()
            return {"action": "host", "name": name, "port": int(port)}
        room = self.values["room"].strip().upper()
        if action != "create" and not re.fullmatch(r"[A-Z0-9]{1,16}", room):
            self._fail("请输入对方提供的房间码（字母或数字）。")
            return None
        try:
            url = self._url(self.values["lan_address" if action == "join_lan" else "online_address"],
                            lan=action == "join_lan")
        except ValueError as error:
            self._fail(str(error))
            return None
        self._clear_error()
        return {"action": "connect", "name": name, "url": url,
                "mode": "create" if action == "create" else "join", "room": "" if action == "create" else room}

    @staticmethod
    def _url(value: str, *, lan: bool) -> str:
        value = value.strip()
        hint = "请输入主机的局域网 IP 和端口，例如 192.168.1.8:8765。" if lan else "请输入以 ws:// 或 wss:// 开头的房间服务地址。"
        if not value or len(value) > 512 or any(char.isspace() or not char.isprintable() for char in value):
            raise ValueError(hint)
        if lan and "://" not in value:
            value = "ws://" + value
        try:
            parsed = urlsplit(value)
            port = parsed.port
            if not parsed.hostname or parsed.scheme not in ({"ws"} if lan else {"ws", "wss"}):
                raise ValueError
            if parsed.username is not None or parsed.password is not None or parsed.fragment or parsed.netloc.endswith(":"):
                raise ValueError
            if port is not None and not 1 <= port <= 65535:
                raise ValueError
            if lan and (parsed.path not in {"", "/"} or parsed.query):
                raise ValueError
        except ValueError:
            raise ValueError(hint) from None
        if lan and port is None:
            parsed = parsed._replace(netloc=parsed.netloc + ":8765")
        return urlunsplit(parsed)

    @staticmethod
    def _clipboard_read() -> str:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        raw = pygame.scrap.get(pygame.SCRAP_TEXT)
        if not raw:
            return ""
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16").rstrip("\x00")
        if len(raw) >= 2 and raw[1] == 0:
            return raw.decode("utf-16-le").rstrip("\x00")
        try:
            return raw.rstrip(b"\x00").decode("utf-8")
        except UnicodeDecodeError:
            if len(raw) % 2 == 0 and raw.endswith(b"\x00\x00"):
                return raw.decode("utf-16-le").rstrip("\x00")
            raise

    def _copy(self, value: str, message: str) -> None:
        try:
            if not pygame.scrap.get_init():
                pygame.scrap.init()
            pygame.scrap.put(pygame.SCRAP_TEXT, value.encode("utf-8") + b"\x00")
        except (pygame.error, UnicodeError, OSError):
            self._fail("无法使用剪贴板，请手动记录房间信息。")
        else:
            self.message, self._error = message, False

    def draw(self, screen) -> None:
        if not self.visible:
            return
        self._sync_layout()
        scrim = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        scrim.fill((20, 22, 28, 122))
        screen.blit(scrim, (0, 0))
        pygame.draw.rect(screen, Theme.SURFACE, self.card, border_radius=12)
        pygame.draw.rect(screen, Theme.SEPARATOR, self.card, 1, border_radius=12)
        self._text(screen, "联网对局", (282, 76), 26, bold=True)
        self._text(screen, "邀请一位朋友，执黑与执红面对面较量", (282, 112), 14, color=Theme.TEXT_SECONDARY)
        self._button(screen, self.close_rect, "×", "close")
        if self.active:
            self._draw_session(screen)
        else:
            self._draw_setup(screen)
        pygame.draw.line(screen, Theme.SEPARATOR, (282, 558), (1118, 558))
        if self.message:
            self._wrapped(screen, self.message, pygame.Rect(282, 484, 836, 62), 15,
                          Theme.DANGER if self._error else Theme.TEXT_SECONDARY)

    def _draw_setup(self, screen) -> None:
        for key, label in self.MODES:
            self._button(screen, self.tab_rects[key], label, "tab:" + key, selected=self.mode == key)
        self._text(screen, "你的昵称", (282, 204), 15, bold=True)
        self._text(screen, "端口" if self.mode == "host" else "房间码（加入时填写）", (708, 204), 15, bold=True)
        self._field(screen, "name", "最多 20 个字符")
        self._field(screen, "port" if self.mode == "host" else "room", "例如 AB12CD")
        if self.mode == "host":
            self._text(screen, "同一网络中的朋友可直接加入", (282, 301), 19, bold=True)
            self._text(screen, "建房后，将本机的局域网 IP、端口和房间码发给对方。", (282, 339), 15, color=Theme.TEXT_SECONDARY)
            instructions = ("双方连接同一个 Wi-Fi 或局域网；请保持建房程序运行。",
                            "如果无法连接，请检查地址与端口，并允许程序通过系统防火墙。")
        else:
            field = "lan_address" if self.mode == "join_lan" else "online_address"
            self._text(screen, "主机地址" if self.mode == "join_lan" else "房间服务地址", (282, 295), 15, bold=True)
            self._field(screen, field, "192.168.1.8:8765" if self.mode == "join_lan" else "wss://你的房间服务地址")
            instructions = (("请向建房的朋友索取地址与房间码。", "双方需连接同一个 Wi-Fi 或局域网。") if self.mode == "join_lan" else
                            ("双方填写同一个可用的房间服务地址，可跨网络对局。", "先创建房间并分享房间码，另一位玩家再填写房间码加入。"))
        helper = pygame.Rect(282, 389, 836, 76)
        pygame.draw.rect(screen, Theme.SURFACE_ALT, self._rect(helper), border_radius=8)
        for index, text in enumerate(instructions):
            self._text(screen, text, (298, 402 + index * 27), 14, color=Theme.TEXT_SECONDARY)
        self._text(screen, "建房者执黑先行，加入者执红；双方准备后开始。", (282, 589), 13, color=Theme.TEXT_SECONDARY, max_width=405)
        if self.mode == "online":
            self._button(screen, self.action_rects["create"], "创建房间", "create")
            self._button(screen, self.action_rects["join"], "加入房间", "join", primary=True)
        else:
            self._button(screen, self.action_rects[self.mode], "创建房间" if self.mode == "host" else "加入房间", self.mode, primary=True)

    def _draw_session(self, screen) -> None:
        pygame.draw.rect(screen, Theme.PRIMARY_SOFT, self._rect(pygame.Rect(282, 150, 836, 104)), border_radius=8)
        self._text(screen, "房间码", (300, 165), 14, color=Theme.TEXT_SECONDARY)
        self._text(screen, self.room or "正在获取…", (300, 191), 28, bold=True, max_width=330)
        seat = {"black": "黑方 · 先手", "red": "红方 · 后手"}.get(self.color, "正在分配座位")
        self._text(screen, seat, (668, 182), 18, bold=True, max_width=240)
        self._text(screen, self.values["name"], (668, 214), 14, color=Theme.TEXT_SECONDARY, max_width=240, localize=False)
        self._button(screen, self.action_rects["copy_room"], "复制房间码", "copy_room")
        self._text(screen, "连接地址", (282, 267), 15, bold=True)
        pygame.draw.rect(screen, Theme.SURFACE_ALT, self._rect(pygame.Rect(282, 294, 684, 44)), border_radius=8)
        self._text(screen, self.address or "正在连接…", (296, 306), 15, max_width=655)
        self._button(screen, self.action_rects["copy_address"], "复制地址", "copy_address")
        pygame.draw.rect(screen, Theme.SURFACE_ALT, self._rect(pygame.Rect(282, 363, 836, 82)), border_radius=8)
        label = self.STATUS_LABELS.get(self.status, self.status or "正在连接…")
        self._text(screen, label, (300, 378), 19, bold=True, max_width=800)
        self._text(screen, "双方准备后即可开始；掉线时暂停行棋，恢复连接后再继续。", (300, 414), 14,
                   color=Theme.TEXT_SECONDARY, max_width=800)
        self._text(screen, "关闭此面板会保留连接。离开正在进行的对局会结束本局。", (282, 458), 14, color=Theme.TEXT_SECONDARY)
        labels = {"ready": "准备", "reconnect": "重新连接", "resign": "认输", "leave": "离开房间"}
        for key, label in labels.items():
            self._button(screen, self.action_rects[key], label, key, primary=key == "ready", danger=key == "resign")

    def _font(self, size: int, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            path = Path(__file__).resolve().parents[2] / (Theme.FONT_BOLD if bold else Theme.FONT_REGULAR)
            self._fonts[key] = pygame.font.Font(str(path), size)
        return self._fonts[key]

    def _text(self, screen, content, position, size, color=None, *, bold=False, center=False, max_width=None, localize=True):
        fallback = Theme.FONT_BOLD if bold else Theme.FONT_REGULAR
        if max_width is None and not center:
            max_width = max(24, self.card.right - 32 - position[0])
        surface = I18n.render_text(str(content), fallback, size, color or Theme.TEXT_PRIMARY,
                                   localize=localize, max_width=max_width, cache=self._fonts)
        if not center:
            position = I18n.mirrored_anchor(position, self.card)
        rect = (surface.get_rect(center=position) if center else
                surface.get_rect(topright=position) if I18n.is_rtl() else surface.get_rect(topleft=position))
        screen.blit(surface, rect)

    def _wrapped(self, screen, content, rect, size, color):
        content = I18n.translate(str(content))
        lines, current = [], ""
        for char in content[:1500]:
            measured = I18n.render_text(current + char, Theme.FONT_REGULAR, size, color,
                                        localize=False, cache=self._fonts).get_width()
            if char == "\n" or measured > rect.width:
                lines.append(current)
                current = "" if char == "\n" else char
            else:
                current += char
        lines.append(current)
        height = size + 7
        for index, line in enumerate(lines[:rect.height // height]):
            if index == rect.height // height - 1 and len(lines) > rect.height // height:
                line += "…"
            self._text(screen, line, (rect.left, rect.top + index * height), size, color, max_width=rect.width)

    def _button(self, screen, rect, label, key, *, primary=False, selected=False, danger=False):
        enabled = self._enabled(key)
        fill = Theme.SURFACE_ALT
        color, border = Theme.TEXT_PRIMARY, Theme.SEPARATOR
        if not enabled:
            fill, color = Theme.DISABLED_FILL, Theme.DISABLED_TEXT
        elif primary:
            fill = Theme.PRIMARY_HOVER if self.hovered == key else Theme.PRIMARY
            color, border = (255, 255, 255), Theme.PRIMARY
        elif selected or self.hovered == key:
            fill, color, border = Theme.PRIMARY_SOFT, Theme.PRIMARY, Theme.PRIMARY
        elif danger:
            fill, color, border = Theme.DANGER_SOFT, Theme.DANGER, Theme.DANGER_SOFT
        pygame.draw.rect(screen, fill, rect, border_radius=8)
        pygame.draw.rect(screen, border, rect, 1, border_radius=8)
        self._text(screen, label, rect.center, 16, color, bold=primary or selected, center=True, max_width=rect.width-16)

    def _field(self, screen, key, placeholder):
        rect = self.field_rects[key]
        active = self.focus == key
        pygame.draw.rect(screen, Theme.SURFACE, rect, border_radius=8)
        pygame.draw.rect(screen, Theme.PRIMARY if active else Theme.SEPARATOR, rect, 2 if active else 1, border_radius=8)
        inner = rect.inflate(-24, -12)
        prior_clip = screen.get_clip()
        screen.set_clip(inner)
        value = self.values[key]
        def rendered(text, color=Theme.TEXT_PRIMARY, localize=False):
            return I18n.render_text(text, Theme.FONT_REGULAR, 17, color, localize=localize, cache=self._fonts)
        visible_value = value[:self.cursor] + self.composition + value[self.cursor:] if active else value
        rtl_input = key == 'name' and I18n.contains_arabic(visible_value)
        if not value and not self.composition:
            text = rendered(placeholder, Theme.TEXT_TERTIARY, localize=True)
            anchor = text.get_rect(topright=(inner.right,inner.top+2)) if I18n.is_rtl() else text.get_rect(topleft=(inner.left,inner.top+2))
            screen.blit(text,anchor)
        else:
            text = rendered(visible_value)
            caret = rendered(value[:self.cursor] + self.composition).get_width()
            offset = max(0, caret - inner.width + 3) if active else 0
            x = inner.right - text.get_width() if rtl_input else inner.left - offset
            if active and self.select_all:
                pygame.draw.rect(screen, Theme.PRIMARY_SOFT, pygame.Rect(x, inner.top, text.get_width(), inner.height))
            screen.blit(text,(x,inner.top+2))
            if active and self.composition:
                start_x = inner.right - rendered(value[:self.cursor]).get_width() if rtl_input else x + rendered(value[:self.cursor]).get_width()
                end_x = inner.right - caret if rtl_input else x + caret
                pygame.draw.line(screen, Theme.PRIMARY, (start_x, inner.bottom - 2), (end_x, inner.bottom - 2))
        if active and not self.select_all and pygame.time.get_ticks() % 1000 < 600:
            caret_width = rendered(value[:self.cursor] + self.composition).get_width()
            caret_x = inner.right - min(caret_width, inner.width-3) if rtl_input else inner.left + min(caret_width, inner.width - 3)
            pygame.draw.line(screen, Theme.PRIMARY, (caret_x, inner.top + 3), (caret_x, inner.bottom - 3), 1)
        screen.set_clip(prior_clip)
