from __future__ import annotations

from dataclasses import replace

import pygame
from pygame import Rect, Surface

from Class import Theme, I18n
from Class.Settings import (
    AISettings,
    CLOCK_OPTIONS_MS,
    DEPTH_OPTIONS,
    PROFILE_OPTIONS,
    TIME_OPTIONS_MS,
)


class SettingsPanel:
    """A compact modal sheet for settings that affect the next AI turn."""

    def __init__(self, settings: AISettings):
        self.visible = False
        self.settings = settings.normalized()
        self.hovered: str | None = None
        self.card = Rect(360, 40, 680, 620)
        self.close_rect = Rect(self.card.right - 66, self.card.top + 18, 44, 44)
        self.apply_rect = Rect(self.card.right - 188, self.card.bottom - 64, 148, 44)
        self.cancel_rect = Rect(self.card.right - 352, self.card.bottom - 64, 148, 44)
        self.depth_minus = Rect(self.card.left + 430, self.card.top + 158, 44, 44)
        self.depth_plus = Rect(self.card.left + 592, self.card.top + 158, 44, 44)
        self.time_minus = Rect(self.card.left + 430, self.card.top + 258, 44, 44)
        self.time_plus = Rect(self.card.left + 592, self.card.top + 258, 44, 44)
        self.clock_rects = {
            0: Rect(self.card.left + 358, self.card.top + 358, 112, 44),
            900_000: Rect(self.card.left + 522, self.card.top + 358, 70, 44),
        }
        self.clock_minus = Rect(self.card.left + 478, self.card.top + 358, 36, 44)
        self.clock_plus = Rect(self.card.left + 598, self.card.top + 358, 36, 44)
        self.profile_rects = {
            profile: Rect(self.card.left + 200 + index * 112, self.card.top + 438, 104, 42)
            for index, profile in enumerate(PROFILE_OPTIONS)
        }
        self._fonts = {}
        self._layout_language = 'zh'
        self._sync_layout()

    def _sync_layout(self):
        if self._layout_language == I18n.language():
            return
        names = ('close_rect', 'apply_rect', 'cancel_rect', 'depth_minus', 'depth_plus',
                 'time_minus', 'time_plus', 'clock_minus', 'clock_plus')
        for rect in [*(getattr(self, name) for name in names), *self.clock_rects.values(), *self.profile_rects.values()]:
            rect.left = self.card.left + self.card.right - rect.right
        self._layout_language = I18n.language()

    def open(self, settings: AISettings) -> None:
        self.settings = settings.normalized()
        self.visible = True
        self.hovered = None

    def close(self) -> None:
        self.visible = False
        self.hovered = None

    def handle_event(self, event: pygame.event.Event) -> str | None:
        self._sync_layout()
        if not self.visible:
            return None
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close()
            return "cancel"
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self._control_at(event.pos)
            return None
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None

        control = self._control_at(event.pos)
        if control in {"close", "cancel"}:
            self.close()
            return "cancel"
        if control == "apply":
            self.close()
            return "apply"
        if control == "depth_minus":
            self.settings = replace(self.settings, depth=self._step(self.settings.depth, DEPTH_OPTIONS, -1))
        elif control == "depth_plus":
            self.settings = replace(self.settings, depth=self._step(self.settings.depth, DEPTH_OPTIONS, 1))
        elif control == "time_minus":
            self.settings = replace(self.settings, time_ms=self._step(self.settings.time_ms, TIME_OPTIONS_MS, -1))
        elif control == "time_plus":
            self.settings = replace(self.settings, time_ms=self._step(self.settings.time_ms, TIME_OPTIONS_MS, 1))
        elif control == "clock_off":
            self.settings = replace(self.settings, total_time_ms=CLOCK_OPTIONS_MS[0])
        elif control == "clock_on":
            self.settings = replace(self.settings, total_time_ms=self.settings.total_time_ms or 900_000)
        elif control == "clock_minus":
            self.settings = replace(self.settings, total_time_ms=self._step(self.settings.total_time_ms, CLOCK_OPTIONS_MS, -1))
        elif control == "clock_plus":
            self.settings = replace(self.settings, total_time_ms=self._step(self.settings.total_time_ms, CLOCK_OPTIONS_MS, 1))
        elif control in PROFILE_OPTIONS:
            self.settings = replace(self.settings, eval_profile=control)
        return None

    def draw(self, screen: Surface) -> None:
        if not self.visible:
            return
        self._sync_layout()
        scrim = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        scrim.fill((20, 22, 28, 122))
        screen.blit(scrim, (0, 0))

        pygame.draw.rect(screen, Theme.SURFACE, self.card, border_radius=Theme.CORNER_RADIUS)
        pygame.draw.rect(screen, Theme.SEPARATOR, self.card, 1, border_radius=Theme.CORNER_RADIUS)
        self._text(screen, "设置", (self.card.left + 32, self.card.top + 26), 26, Theme.TEXT_PRIMARY, bold=True)
        self._text(screen, "按下“应用”后，设置将用于人工智能", (self.card.left + 32, self.card.top + 62), 14, Theme.TEXT_SECONDARY)
        self._button(screen, self.close_rect, "×", "close", compact=True)

        self._label(screen, "搜索深度", "深度越高，棋力越强，但思考时间越长", self.card.top + 126)
        self._stepper(screen, self.depth_minus, self.depth_plus, str(self.settings.depth), "depth_minus", "depth_plus")

        self._label(screen, "单步思考", "每步思考上限；总时钟仍然有效", self.card.top + 226)
        self._stepper(screen, self.time_minus, self.time_plus, self._format_ms(self.settings.time_ms), "time_minus", "time_plus")

        self._label(screen, "AI总思考时长", "按裁判要求设置；限时口径尚需确认", self.card.top + 326)
        self._choice(screen, self.clock_rects[0], "关闭", "clock_off", self.settings.total_time_ms == 0)
        value = self.settings.total_time_ms or 900_000
        self._button(screen, self.clock_minus, "-", "clock_minus", compact=True)
        self._choice(screen, self.clock_rects[900_000], f"{value // 60_000}:00", "clock_on", self.settings.total_time_ms > 0)
        self._button(screen, self.clock_plus, "+", "clock_plus", compact=True)

        self._label(screen, "评估方案", "论文方案仅供试验", self.card.top + 406)
        for profile, rect in self.profile_rects.items():
            label = {"baseline": "基准", "candidate_016": "候选", "solid": "稳健", "paper_2022": "论文试验"}[profile]
            self._choice(screen, rect, label, profile, self.settings.eval_profile == profile, compact=True)

        pygame.draw.line(
            screen,
            Theme.SEPARATOR,
            (self.card.left + 24, self.card.bottom - 88),
            (self.card.right - 24, self.card.bottom - 88),
        )
        self._button(screen, self.cancel_rect, "取消", "cancel")
        self._button(screen, self.apply_rect, "应用", "apply", primary=True)

    def _label(self, screen: Surface, title: str, helper: str, top: int) -> None:
        self._text(screen, title, (self.card.left + 32, top), 17, Theme.TEXT_PRIMARY, bold=True)
        self._text(screen, helper, (self.card.left + 32, top + 27), 13, Theme.TEXT_SECONDARY)

    def _stepper(self, screen: Surface, minus: Rect, plus: Rect, value: str, minus_key: str, plus_key: str) -> None:
        self._button(screen, minus, "-", minus_key, compact=True)
        left, right = sorted((minus, plus), key=lambda rect: rect.left)
        value_rect = Rect(left.right + 8, left.top, right.left - left.right - 16, left.height)
        pygame.draw.rect(screen, Theme.SURFACE_ALT, value_rect, border_radius=Theme.CORNER_RADIUS)
        pygame.draw.rect(screen, Theme.SEPARATOR, value_rect, 1, border_radius=Theme.CORNER_RADIUS)
        self._text(screen, value, value_rect.center, 16, Theme.TEXT_PRIMARY, bold=True, center=True)
        self._button(screen, plus, "+", plus_key, compact=True)

    def _choice(self, screen: Surface, rect: Rect, label: str, key: str, selected: bool, compact: bool = False) -> None:
        fill = Theme.PRIMARY_SOFT if selected else Theme.SURFACE_ALT
        border = Theme.PRIMARY if selected else Theme.SEPARATOR
        pygame.draw.rect(screen, fill, rect, border_radius=Theme.CORNER_RADIUS)
        pygame.draw.rect(screen, border, rect, 1, border_radius=Theme.CORNER_RADIUS)
        color = Theme.PRIMARY if selected else Theme.TEXT_PRIMARY
        self._text(screen, label, rect.center, 14 if compact else 15, color, bold=selected, center=True)

    def _button(self, screen: Surface, rect: Rect, label: str, key: str, *, primary: bool = False, compact: bool = False) -> None:
        hovered = self.hovered == key
        if primary:
            fill = Theme.PRIMARY_HOVER if hovered else Theme.PRIMARY
            color = (255, 255, 255)
            border = Theme.PRIMARY
        else:
            fill = Theme.PRIMARY_SOFT if hovered else Theme.SURFACE_ALT
            color = Theme.TEXT_PRIMARY
            border = Theme.SEPARATOR
        pygame.draw.rect(screen, fill, rect, border_radius=Theme.CORNER_RADIUS)
        pygame.draw.rect(screen, border, rect, 1, border_radius=Theme.CORNER_RADIUS)
        self._text(screen, label, rect.center, 17 if compact else 15, color, bold=primary, center=True)

    def _control_at(self, pos: tuple[int, int]) -> str | None:
        if self.clock_minus.collidepoint(pos):
            return "clock_minus"
        if self.clock_plus.collidepoint(pos):
            return "clock_plus"
        if self.close_rect.collidepoint(pos):
            return "close"
        if self.cancel_rect.collidepoint(pos):
            return "cancel"
        if self.apply_rect.collidepoint(pos):
            return "apply"
        if self.depth_minus.collidepoint(pos):
            return "depth_minus"
        if self.depth_plus.collidepoint(pos):
            return "depth_plus"
        if self.time_minus.collidepoint(pos):
            return "time_minus"
        if self.time_plus.collidepoint(pos):
            return "time_plus"
        for clock, rect in self.clock_rects.items():
            if rect.collidepoint(pos):
                return "clock_on" if clock else "clock_off"
        for profile, rect in self.profile_rects.items():
            if rect.collidepoint(pos):
                return profile
        return None

    @staticmethod
    def _step(value: int, options: tuple[int, ...], direction: int) -> int:
        current = min(options, key=lambda option: abs(option - value))
        index = options.index(current)
        return options[max(0, min(len(options) - 1, index + direction))]

    @staticmethod
    def _format_ms(value: int) -> str:
        if value >= 1_000:
            return f"{value // 1_000}s"
        return f"{value}ms"

    def _text(self, screen: Surface, content: str, position: tuple[int, int], size: int, color: tuple[int, ...], *, bold: bool = False, center: bool = False) -> None:
        font_path = Theme.FONT_BOLD if bold else Theme.FONT_REGULAR
        limit = 330 if not center and position[1] >= self.card.top + 100 else self.card.width - 80
        text = I18n.render_text(content, font_path, size, color, max_width=limit, cache=self._fonts)
        if not center:
            position = I18n.mirrored_anchor(position, self.card)
        rect = (text.get_rect(center=position) if center else
                text.get_rect(topright=position) if I18n.is_rtl() else text.get_rect(topleft=position))
        screen.blit(text, rect)
