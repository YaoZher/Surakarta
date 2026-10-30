"""Arabic rendering and language switching exercise the actual Pygame UI."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
from Class import I18n, Theme
from Class.Element.TextBox import TextBox
from Class.Element.NetworkPanel import NetworkPanel
from Class.Element.SettingsPanel import SettingsPanel
from Class.Settings import AISettings
from Class.Globals import Globals
from Class.GameManager import GameManage

ROOT = Path(__file__).resolve().parents[1]

class ArabicInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.previous_language = I18n.language()
        self.previous_cwd = Path.cwd()
        os.chdir(ROOT)
        self.temporary = tempfile.TemporaryDirectory()
        self.language_path = Path(self.temporary.name) / 'language.json'
        self.settings_patch = patch.object(I18n, 'LANGUAGE_PATH', self.language_path)
        self.settings_patch.start()
        I18n.set_language('ar')
        pygame.init()
        self.screen = pygame.display.set_mode((1400,700))
        self.game = None

    def tearDown(self):
        if self.game:
            self.game.network.shutdown()
        self.settings_patch.stop()
        self.temporary.cleanup()
        I18n.set_language(self.previous_language)
        pygame.quit()
        os.chdir(self.previous_cwd)

    def test_connected_glyphs_bidi_and_font_coverage(self):
        logical = 'الإعدادات 123 AB12CD'
        visual = I18n.visual_text(logical, localize=False)
        self.assertNotEqual(visual, logical)
        self.assertIn('AB12CD',visual)
        self.assertIn('123',visual)
        font = pygame.font.Font(str(I18n.ARABIC_FONT),20)
        self.assertTrue(all(metric is not None for metric in font.metrics(visual)))

    def test_persistence_and_invalid_language(self):
        I18n.set_language('ar',persist=True)
        self.assertEqual(json.loads(self.language_path.read_text())['language'],'ar')
        with self.assertRaises(ValueError):
            I18n.set_language('xx')
        self.assertEqual(I18n.language(),'ar')

    def test_text_fits_rtl_and_chinese_switch_restores_label(self):
        box = TextBox(20,54,20,280,'黑方正在思考…',Theme.FONT_REGULAR,20,
                      Theme.TEXT_PRIMARY,Theme.SURFACE,False)
        box.draw(self.screen)
        self.assertEqual(box.rendered_content,'الأسود يفكر…')
        self.assertTrue(box.rect.contains(box.text_rect))
        I18n.set_language('zh')
        box.draw(self.screen)
        self.assertEqual(box.rendered_content,'黑方正在思考…')
        self.assertTrue(box.rect.contains(box.text_rect))

    def test_mixed_names_and_dynamic_diagnostics(self):
        surface = I18n.render_text('玩家：中文Nasr',Theme.FONT_REGULAR,17,Theme.TEXT_PRIMARY)
        self.assertGreater(surface.get_width(),30)
        self.assertEqual(I18n.visual_text('B2E-3D',localize=False),'B2E-3D')
        self.assertIn('02:03',I18n.translate('用时：02:03'))
        diagnostic = I18n.translate('AI 深度5 | 2031毫秒 | 14,219节点 | 剩余 14:57')
        self.assertNotIn('毫秒',diagnostic)
        self.assertIn('14:57',I18n.visual_text(diagnostic,localize=False))

    def test_settings_controls_are_mirrored_and_still_work(self):
        panel=SettingsPanel(AISettings())
        panel.open(AISettings())
        self.assertLess(panel.depth_plus.left,panel.depth_minus.left)
        before=panel.settings.depth
        panel.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=panel.depth_plus.center))
        self.assertGreater(panel.settings.depth,before)
        panel.draw(self.screen)
        I18n.set_language('zh')
        panel.draw(self.screen)
        self.assertGreater(panel.depth_plus.left,panel.depth_minus.left)

    def test_arabic_nickname_and_ltr_address_are_sent_unchanged(self):
        panel=NetworkPanel();panel.open()
        self.assertEqual(panel.values['name'],'لاعب')
        self.assertGreater(panel.field_rects['name'].left,panel.field_rects['port'].left)
        panel.values['name']='ناصر 12'
        panel.cursor=len(panel.values['name'])
        panel._insert(' أ')
        panel._key(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_BACKSPACE,mod=0))
        self.assertEqual(panel.values['name'],'ناصر 12 ')
        panel.mode='online';panel.values['online_address']='ws://127.0.0.1:8765'
        panel.values['room']='AB12CD'
        action=panel._activate('join')
        self.assertEqual(action['name'],'ناصر 12')
        self.assertEqual(action['url'],'ws://127.0.0.1:8765')
        self.assertEqual(action['room'],'AB12CD')
        panel.draw(self.screen)
        I18n.set_language('zh')
        self.assertEqual(NetworkPanel().values['name'],'玩家')

    def test_f2_switch_preserves_game_settings_and_network_object(self):
        Globals.reset()
        self.game=GameManage()
        g=self.game
        before=(g.ai_settings,g.chess_board,g.chess_manual,g.network,Globals.step)
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_F2,mod=0))
        g.check_event()
        self.assertEqual(I18n.language(),'zh')
        self.assertEqual(before,(g.ai_settings,g.chess_board,g.chess_manual,g.network,Globals.step))
        self.assertEqual(json.loads(self.language_path.read_text())['language'],'zh')
        self.assertEqual(g.menu.language_button.textbox.content,'العربية')

    def test_switch_during_match_keeps_board_history_and_timers(self):
        import Class.GameManager as manager
        Globals.reset();self.game=GameManage();g=self.game
        with patch.object(manager,'RECORDS_DIR',Path(self.temporary.name)/'records'):
            pygame.event.clear()
            pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=g.menu.buttons[0].rect.center))
            g.check_event()
        self.assertTrue(Globals.game_start)
        before=(g.chess_board.ai_black.to_engine_board(g.chess_board).to_rows(),
                list(g.chess_manual.record),g.user_panel.control_up.timer.is_stop,
                g.user_panel.control_up.timer.miliseconds,Globals.is_black)
        g.toggle_language()
        after=(g.chess_board.ai_black.to_engine_board(g.chess_board).to_rows(),
               list(g.chess_manual.record),g.user_panel.control_up.timer.is_stop,
               g.user_panel.control_up.timer.miliseconds,Globals.is_black)
        self.assertEqual(before,after)
        self.assertTrue(Globals.game_start)

    def test_language_button_and_modal_shortcut(self):
        Globals.reset();self.game=GameManage();g=self.game
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=g.menu.language_button.rect.center))
        g.check_event()
        self.assertEqual(I18n.language(),'zh')
        g.settings_panel.open(g.ai_settings)
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_F2,mod=0))
        g.check_event()
        self.assertEqual(I18n.language(),'ar')
        self.assertTrue(g.settings_panel.visible)
        self.assertEqual(g.settings_panel.settings,g.ai_settings)

if __name__=='__main__':
    unittest.main()
