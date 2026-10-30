import sys
import time
from pathlib import Path

# 导入pygame库
import pygame
from pygame import Color, freetype
from pygame.locals import QUIT, KEYDOWN, MOUSEBUTTONDOWN, MOUSEMOTION  # 导入常用关键字常量

from Class import Theme, I18n
from Class.Globals import Globals
from Class.Settings import AISettings
from Class.MatchRecord import GameRecorder, load_match_info
from Class.Assembly.ChessBoard import ChessBoard
from Class.Assembly.ChessManual import ChessManual
from Class.Assembly.MyMenu import MyMenu
from Class.Assembly.UserPanel import UserPanel
from Class.Element.SettingsPanel import SettingsPanel
from Class.NetworkSession import NetworkSession

chess = None
RECORDS_DIR = Path(__file__).resolve().parents[1] / "棋谱"
MATCH_INFO_PATH = Path(__file__).resolve().parents[1] / "比赛信息.json"

#游戏管理总类
class GameManage:
    #初始化
    def __init__(self):
        '''
            初始化游戏
        '''
        if getattr(self, "network", None) is not None:
            self.network.shutdown()
        pygame.init()  # 初始化pygame
        pygame.freetype.init()  # 初始化自由字体模块

        # 连接属性
        self.width = 1400  # 窗口宽度
        self.height = 700  # 窗口高度
        self.screen = pygame.display.set_mode((self.width, self.height))  # 获取对显示系统的访问，并创建一个窗口screen，大小为1400*700
        pygame.display.set_caption('سوراكارتا' if I18n.is_rtl() else 'Surakarta AI')
        self.screen_color = Theme.APP_BG
        self.screen.fill(self.screen_color)  # 填充画布颜色
        self.chess_board = ChessBoard(0, self.height, 0, self.height)  # 棋盘（位于界面左侧的边长为700的正方形区域内）
        self.ai_settings = AISettings.load()
        self.chess_board.apply_ai_settings(self.ai_settings)
        self.chess_board.draw(self.screen)
        self.chess_manual = ChessManual(0, self.height, self.chess_board.right, self.chess_board.right + 200, Theme.SURFACE)
        self.chess_manual.draw(self.screen)
        # # self.chess_manual.gameStart(self.screen)
        # # self.chess_manual.addRecord(self.screen,"123")
        self.user_panel = UserPanel(0, self.height, self.chess_manual.right, self.chess_manual.right + 300)
        self.user_panel.draw(self.screen)
        self.menu = MyMenu(self.height, self.user_panel.right, self.width)
        self.settings_panel = SettingsPanel(self.ai_settings)
        self.menu.draw(self.screen)
        pygame.display.flip()
        self.recorder = None
        self.record_error = ""
        self._record_finished = False
        self.network = NetworkSession(self)
        #
        # Globals.update_game_start(False)

    def updateUserPanel(self):
        '''
            更新用户面板
        '''

        # 落子前为黑方走子
        if Globals.is_black:
            self.user_panel.updateState(self.screen, '红方正在思考…')  # 更新状态
            self.user_panel.stopTimer(1)  # 黑方计时器暂停

            self.user_panel.activate(self.screen, 0)  # 红方控制面板激活
            self.user_panel.startTimer(self.screen, 0)  # 红方计时器继续
        # 落子前为红方走子
        else:
            self.user_panel.updateState(self.screen, '黑方正在思考…')  # 更新状态
            self.user_panel.stopTimer(0)  # 红方计时器暂停

            self.user_panel.activate(self.screen, 1)  # 黑方控制面板激活
            self.user_panel.startTimer(self.screen, 1)  # 黑方计时器继续

        Globals.update_is_black(not Globals.is_black)  # 更新落子方

    def updateAIDiagnostics(self):
        self.user_panel.updateAIDiagnostics(self.screen, self.chess_board.last_ai)

    def _finish_move(self):
        """Codex review of Gemini audit: end a material win before switching turns."""
        self.chess_manual.addRecord(self.screen, Globals.step_record)
        if Globals.red == 0 or Globals.black == 0:
            self.game_over()
        else:
            self.updateUserPanel()
            self._save_record("move")

    def _start_recording(self):
        try:
            metadata = load_match_info(MATCH_INFO_PATH)
            rows = self.chess_board.ai_black.to_engine_board(self.chess_board).to_rows()
            self.recorder = GameRecorder(RECORDS_DIR, settings=self.ai_settings.to_dict(), metadata=metadata, initial_rows=rows)
            self._record_finished = False
            self._save_record("start")
        except (OSError, ValueError) as error:
            self.record_error = str(error)
            self.user_panel.updateState(self.screen, "保存失败，请查权限/信息")

    def _save_record(self, operation):
        if getattr(self, "recorder", None) is None:
            return None
        try:
            rows = self.chess_board.ai_black.to_engine_board(self.chess_board).to_rows()
            result = any(line.startswith("#") for line in self.chess_manual.record)
            status = "finished" if result else "ended_without_result" if self._record_finished else "interrupted" if operation in {"exit", "restart"} else "in_progress"
            return self.recorder.save(records=self.chess_manual.record, board_rows=rows, status=status,
                                      operation=operation, settings=(self.network.record_settings if self.network.state is not None else self.ai_settings.to_dict()), elapsed_ms={
                                          "black": self.user_panel.control_up.timer.miliseconds,
                                          "red": self.user_panel.control_down.timer.miliseconds})
        except (OSError, ValueError) as error:
            self.record_error = str(error)
            self.user_panel.updateState(self.screen, "保存失败，请截图备份")
            return None

    def export_record(self):
        if self._save_record("export") is None:
            return None
        try:
            path = self.recorder.export()
            self.user_panel.updateState(self.screen, "已保存至“棋谱”目录")
            return path
        except (OSError, ValueError) as error:
            self.record_error = str(error)
            self.user_panel.updateState(self.screen, "导出失败，请检查权限")
            return None

    def _play_ai_turn(self):
        """Codex-assisted: advance the UI only after an actual AI move."""
        if self.network.active or not Globals.game_start or Globals.game_stop:
            return False
        if Globals.red == 0 or Globals.black == 0:
            self.game_over()
            return False
        previous_step = Globals.step
        ai = self.chess_board.ai_move(self.screen)
        self.updateAIDiagnostics()
        if ai is not None and getattr(ai, "time_forfeit", False):
            winner = "红方" if Globals.is_black else "黑方"
            loser = "黑方" if Globals.is_black else "红方"
            self.game_over(result=f"# {winner}获胜（{loser}超时）")
            return False
        if Globals.step == previous_step:
            return False
        self._finish_move()
        return True

    def _draw_scene(self):
        """Redraw the stable scene before repainting a modal overlay."""
        self.screen.fill(self.screen_color)
        self.chess_board.draw(self.screen)
        self.chess_board.drawChess(self.screen)
        self.chess_manual.draw(self.screen)
        self.user_panel.draw(self.screen)
        self.menu.draw(self.screen)
        self.settings_panel.draw(self.screen)

    def toggle_language(self):
        """Refresh labels in place without resetting a local or online match."""
        warning = ''
        try:
            I18n.set_language('zh' if I18n.is_rtl() else 'ar', persist=True)
        except OSError:
            warning = '语言设置未保存，下次启动需重选'
        pygame.display.set_caption('سوراكارتا' if I18n.is_rtl() else 'Surakarta AI')
        self.network.redraw()
        self.settings_panel.draw(self.screen)
        self.network.panel.draw(self.screen)
        if warning:
            self.user_panel.updateState(self.screen, warning)
        pygame.display.update()

    def check_event(self):
        '''
            获取事件并响应
        '''

        for event in pygame.event.get():
            language_key = event.type == KEYDOWN and getattr(event, 'key', None) == pygame.K_F2
            language_click = (event.type == MOUSEBUTTONDOWN and getattr(event, 'button', 1) == 1
                              and not self.settings_panel.visible and not self.network.panel.visible
                              and self.menu.language_button.rect.collidepoint(event.pos))
            if language_key or language_click:
                self.toggle_language()
                continue
            # 如果鼠标点击右上角关闭按钮，则关闭，退出程序
            if event.type is QUIT:
                self._save_record("exit")
                self.network.shutdown()
                pygame.quit()
                sys.exit()

            if event.type == KEYDOWN and getattr(event, "key", None) == pygame.K_s and getattr(event, "mod", 0) & pygame.KMOD_CTRL:
                self.export_record()
                continue

            if self.network.handle_event(event):
                continue

            if self.settings_panel.visible:
                action = self.settings_panel.handle_event(event)
                if action == "apply":
                    if Globals.game_start:
                        self._draw_scene()
                        self.user_panel.updateState(self.screen, "对局中参数已锁定")
                        continue
                    self.ai_settings = self.settings_panel.settings.normalized()
                    self.ai_settings.save()
                    self.chess_board.apply_ai_settings(self.ai_settings)
                elif action == "cancel":
                    pass
                self._draw_scene()
                if event.type in (MOUSEBUTTONDOWN, MOUSEMOTION, KEYDOWN):
                    continue
            # 如果鼠标点击
            if event.type == MOUSEBUTTONDOWN:
                print("mouse clicked")

                # 游戏开始并且游戏未暂停并且鼠标在棋盘范围内点击
                if Globals.game_start and not Globals.game_stop and self.chess_board.rect.collidepoint(event.pos):
                    # 人类行棋
                    if not self.isAIStep():
                        global chess  # 声明此处的chess为全局变量

                        # 选择棋子
                        chess, chess_index = self.chess_board.chooseChess(event.pos)

                        # 当前有选中棋子
                        if chess:
                            # 有被选中的棋子，该棋子不被点击并更新被选中的棋子
                            if Globals.chosen_chess:
                                Globals.chosen_chess.unclicked(self.screen)

                            chess.clicked(self.screen)  # 选中棋子被点击
                            Globals.update_chosen_chess(chess)  # 更新被选中的棋子
                            Globals.update_chosen_chess_index(chess_index)  # 更新被选中的棋子坐标
                            self.chess_board.set_selected_position(chess_index)
                            self.chess_board.draw(self.screen)
                            self.chess_board.drawChess(self.screen)
                            print("choose chess", chess.pos)
                        # 当前没选中棋子并且有被选中的棋子（有选中的棋子才有移动/吃子的意义）
                        elif Globals.chosen_chess:
                            Globals.chosen_chess.unclicked(self.screen)
                            loc_index = self.chess_board.chooseLoc(event.pos) # 选择移动位置

                            # loc_index有值
                            if loc_index:
                                self.chess_board.clear_selection()
                                print("choose loc", loc_index)

                                # 移动棋子成功
                                if self.chess_board.moveChess(self.screen, Globals.chosen_chess_index, loc_index):
                                    self._finish_move()
                                else:
                                    self.chess_board.draw(self.screen)
                                    self.chess_board.drawChess(self.screen)

                                Globals.update_chosen_chess(None)  # 更新被选中的棋子
                                Globals.update_chosen_chess_index(None)  # 更新被选中的棋子坐标

                    # 如果黑方AI启用，且轮到黑方行棋
                    if self.chess_board.ai_black.is_start and Globals.is_black:
                        # self.chess_board.ai_black.getChessLosc(self.chess_board)
                        self._play_ai_turn()

                    # 如果红方AI启用，且轮到红方行棋
                    elif self.chess_board.ai_red.is_start and not Globals.is_black:
                        # self.chess_board.ai_red.getChessLosc(self.chess_board)
                        self._play_ai_turn()


                # 鼠标在用户面板内点击
                elif self.user_panel.rect.collidepoint(event.pos):
                    control_button_index = self.user_panel.mouseClick(event.pos)  # 控制面板按钮索引

                    # “人类”（上）按钮
                    if control_button_index == 0:
                        self.user_panel.updateName(self.screen, '人类', 1)  # 更新黑方姓名
                        self.chess_board.stopAI(1)  # 停用黑方人机
                    # ”人机“（上）按钮
                    elif control_button_index == 1:
                        self.user_panel.updateName(self.screen, '人机', 1)  # 更新黑方姓名
                        self.chess_board.startAI(1)  # 启用黑方人机
                        print('启用黑方人机')
                    # “暂停”（上）按钮
                    elif control_button_index == 2:
                        self.user_panel.stopTimer(1)  # 暂停黑方计时器
                        Globals.update_game_stop(True)  # 置game_stop为真
                    # ”继续“（上）按钮
                    elif control_button_index == 3:
                        self.user_panel.startTimer(self.screen, 1)  # 启用黑方计时器
                        Globals.update_game_stop(False)  # 置game_stop为假
                    # “人类”（下）按钮
                    elif control_button_index == 4:
                        self.user_panel.updateName(self.screen, '人类', 0)  # 更新红方姓名
                        self.chess_board.stopAI(0)  # 停用红方人机
                    # ”人机“（下）按钮
                    elif control_button_index == 5:
                        self.user_panel.updateName(self.screen, '人机', 0)  # 更新红方姓名
                        self.chess_board.startAI(0)  # 启用红方人机
                        print('启用红方人机')
                    # “暂停”（下）按钮
                    elif control_button_index == 6:
                        self.user_panel.stopTimer(0)  # 暂停红方计时器
                        Globals.update_game_stop(True)  # 置game_stop为真
                    # ”继续“（下）按钮
                    elif control_button_index == 7:
                        self.user_panel.startTimer(self.screen, 0)  # 启用红方计时器
                        Globals.update_game_stop(False)  # 置game_stop为假
                # 鼠标在菜单内点击
                elif self.menu.rect.collidepoint(event.pos):
                    menu_button_index = self.menu.mouseClick(event.pos)  # 菜单按钮索引

                    # “开始”按钮
                    if menu_button_index == 0:
                        Globals.update_game_start(True)  # 置game_start为真

                        self.chess_board.drawChess(self.screen)  # 初始化棋盘棋子，绘制棋子
                        self.chess_manual.gameStart(self.screen)  # 棋谱转为开始游戏后的状态
                        self.user_panel.updateState(self.screen, "黑方正在思考…")  # 更新状态
                        self.user_panel.stopTimer(0)  # 停用红方计时器
                        self.user_panel.startTimer(self.screen, 1)  # 启用黑方计时器
                        self.user_panel.activate(self.screen, 1)  # 激活黑方控制面板
                        self.menu.gameStart(self.screen)  # 菜单转为游戏开始后的状态
                        pygame.display.update()
                        self._start_recording()
                        # self.chess_board.moveChess(self.screen,(0,4),(0,3))
                    # “重来”按钮
                    elif menu_button_index == 1:
                        self._save_record("restart")
                        Globals.reset()  # 项目全局变量重置
                        self.__init__()  # 重新初始化
                    # ”打谱“按钮
                    elif menu_button_index == 2:
                        if self.export_record() is not None:
                            self.menu.output(self.screen)

                    # ”退出“按钮
                    elif menu_button_index == 3:
                        self._save_record("exit")
                        self.network.shutdown()
                        pygame.quit()
                        sys.exit()  # 程序退出
                    elif menu_button_index == 4:
                        self.settings_panel.open(self.ai_settings)
                        self._draw_scene()

            # 鼠标移动
            if event.type == MOUSEMOTION:
                # print(event.pos)
                self.user_panel.mouseOver_Leave(self.screen, event.pos)  # 控制面板按钮响应
                self.menu.mouseOver_Leave(self.screen, event.pos)  # 菜单按钮响应
                # self.chess_board.mouseOver_Leave(self.screen, event.pos)

    def game_over(self, *, result=None):
        """Finish a material win or an explicitly adjudicated AI forfeit."""
        if result is None:
            if Globals.black == 0:
                result = "# 红方获胜"
            elif Globals.red == 0:
                result = "# 黑方获胜"
        if result is not None:
            self.chess_manual.addResult(self.screen, result)
            self.user_panel.updateState(self.screen, result.removeprefix("# "))
        # Codex-assisted: freeze both visible timers on every game end.
        self.user_panel.stopTimer(1)
        self.user_panel.stopTimer(0)
        self.menu.gameOver(self.screen)
        self.user_panel.gameOver(self.screen)
        Globals.update_game_start(False)
        self._record_finished = True
        self._save_record("finish")

    def isAIStep(self):
        '''
            判断是否是AI落子
        '''

        # Check the current side explicitly; both AI players may be enabled.
        if Globals.is_black:
            return self.chess_board.ai_black.is_start
        return self.chess_board.ai_red.is_start

    #运行
    def run(self):
        '''
            运行游戏
        '''

        frame_clock = pygame.time.Clock()
        while True:
            self.network.poll()
            self.check_event()
            if Globals.game_start and not self.network.active and not self.settings_panel.visible:
                if not Globals.game_stop:
                    if Globals.is_black:
                        self.user_panel.runTimer(self.screen,1)
                    else:
                        self.user_panel.runTimer(self.screen, 0)
                if Globals.red == 0 or Globals.black == 0:
                    self.game_over()
                    Globals.update_game_start(False)
                if self.chess_board.ai_black.is_start and self.isAIStep() and Globals.step == 0:
                    pygame.time.delay(50)
                    print('黑方AI走棋')
                    # self.chess_board.ai_black.getChessLosc(self.chess_board)
                    # print(self.chess_board.ai_black.generateMoves())
                    self._play_ai_turn()

            self.network.draw()
            pygame.display.update()  # 刷新显示
            frame_clock.tick(60)
