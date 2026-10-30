"""Chinese/Arabic presentation only: keep game state, protocol and records unchanged."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

import pygame
import arabic_reshaper
from bidi.algorithm import get_display

ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_PATH = ROOT / 'output' / 'language.json'
ARABIC_FONT = ROOT / 'Resource' / 'NotoSansArabic.ttf'
SUPPORTED = ('zh', 'ar')
CATALOG = json.loads((Path(__file__).parent / 'locales' / 'ar.json').read_text(encoding='utf-8'))
_arabic = re.compile(r'[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]')
_cjk = re.compile(r'[\u3400-\u9fff]')

def _load_language() -> str:
    requested = os.getenv('SURAKARTA_LANGUAGE')
    if requested is None:
        try:
            payload = json.loads(LANGUAGE_PATH.read_text(encoding='utf-8'))
            requested = payload.get('language', 'zh') if isinstance(payload, dict) else 'zh'
        except (OSError, ValueError):
            requested = 'zh'
    return requested if requested in SUPPORTED else 'zh'

_language = _load_language()

def language() -> str:
    return _language

def is_rtl() -> bool:
    return _language == 'ar'

def contains_arabic(text: str) -> bool:
    return bool(_arabic.search(str(text)))

def set_language(value: str, *, persist: bool = False, path: Path | None = None) -> None:
    global _language
    if value not in SUPPORTED:
        raise ValueError('Unsupported language: ' + str(value))
    _language = value
    if persist:
        target = LANGUAGE_PATH if path is None else Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({'language': value}) + '\n', encoding='utf-8')

def translate(content: str) -> str:
    text = str(content)
    if not is_rtl():
        return text
    if text in CATALOG:
        return CATALOG[text]
    if text.startswith('玩家：'):
        name = text[3:]
        return 'اللاعب: ' + CATALOG.get(name, name)
    match = re.fullmatch(r'用时[： ]+(\d+:\d+)', text)
    if match:
        return 'الوقت: ' + match[1]
    if text.startswith('# '):
        return '# ' + translate(text[2:])
    match = re.fullmatch(r'(黑方|红方)获胜（(黑方|红方)超时）', text)
    if match:
        return f'فاز {CATALOG[match[1]]} (انتهى وقت {CATALOG[match[2]]})'
    if text.startswith('AI 深度'):
        return (text.replace('AI 深度', 'عمق ').replace('毫秒', 'ms')
                .replace('节点', 'عقدة').replace('剩余 ', 'باقي ')
                .replace('超时判负', 'خسارة بالوقت').replace('已启用兜底', 'نقلة احتياطية'))
    match = re.fullmatch(r'房间 (.*?) · (黑方|红方) · 不限时', text)
    if match:
        return f'غرفة {match[1]} · {CATALOG[match[2]]} · دون توقيت'
    # Network result text joins a winner and one of the stable reason labels.
    for winner in ('黑方获胜', '红方获胜', '和棋'):
        if text.startswith(winner):
            tail = text[len(winner):]
            for source, target in sorted(CATALOG.items(), key=lambda item: len(item[0]), reverse=True):
                if source in tail:
                    tail = tail.replace(source, target)
            return CATALOG[winner] + tail
    return text

def visual_text(content: str, *, localize: bool = True) -> str:
    logical = translate(content) if localize else str(content)
    if not contains_arabic(logical):
        return logical
    return get_display(arabic_reshaper.reshape(logical), base_dir='R' if is_rtl() else None)

def font_path(text: str, fallback: str | Path) -> str:
    if contains_arabic(text):
        if ARABIC_FONT.is_file():
            return str(ARABIC_FONT)
        candidate = pygame.font.match_font('arial,dejavusans,tahoma')
        if candidate:
            return candidate
        raise FileNotFoundError('Arabic font missing: Resource/NotoSansArabic.ttf')
    fallback = Path(fallback)
    return str(fallback if fallback.is_absolute() else ROOT / fallback)

def _render_visual(visual: str, fallback, size: int, color, cache: dict | None):
    def font(path):
        key = (str(path), size)
        if cache is not None:
            if key not in cache:
                cache[key] = pygame.font.Font(str(path), size)
            return cache[key]
        return pygame.font.Font(str(path), size)
    primary = font(font_path(visual, fallback))
    if contains_arabic(visual) and _cjk.search(visual):
        # Player names may contain Chinese even in the Arabic UI.
        groups = re.findall(r'[\u3400-\u9fff]+|[^\u3400-\u9fff]+', visual)
        fonts = [font(font_path(group, fallback)) if _cjk.search(group) else primary for group in groups]
        ascent = max(f.get_ascent() for f in fonts)
        height = ascent + max(-f.get_descent() for f in fonts)
        surfaces = [f.render(group, True, color) for group, f in zip(groups, fonts)]
        surface = pygame.Surface((sum(s.get_width() for s in surfaces), height), pygame.SRCALPHA)
        x = 0
        for s, f in zip(surfaces, fonts):
            surface.blit(s, (x, ascent - f.get_ascent())); x += s.get_width()
    else:
        surface = primary.render(visual, True, color)
    bounds = surface.get_bounding_rect()
    if bounds.width and bounds.height:
        # Crop vertical font padding, but retain spaces for input caret metrics.
        surface = surface.subsurface(pygame.Rect(0,bounds.y,surface.get_width(),bounds.height)).copy()
    return surface

def render_text(content: str, fallback, size: int, color, *, localize=True,
                max_width=None, max_height=None, cache=None):
    logical = translate(content) if localize else str(content)
    point_size = int(size)
    while True:
        visual = visual_text(logical, localize=False)
        surface = _render_visual(visual, fallback, point_size, color, cache)
        fits = ((max_width is None or surface.get_width() <= max_width) and
                (max_height is None or surface.get_height() <= max_height))
        if fits or point_size <= min(11, size):
            break
        point_size -= 1
    if max_width is not None:
        while logical and surface.get_width() > max_width:
            logical = logical[:-1]
            surface = _render_visual(visual_text(logical + '…', localize=False), fallback, point_size, color, cache)
    return surface

def mirror_rect(rect: pygame.Rect, container: pygame.Rect) -> pygame.Rect:
    result = rect.copy()
    if is_rtl():
        result.left = container.left + container.right - rect.right
    return result

def mirrored_anchor(position, container):
    return (container.left + container.right - position[0], position[1]) if is_rtl() else position
