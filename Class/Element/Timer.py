#导入pygame库
import pygame
from pygame import Color, Surface

from Class.Element.TextBox import TextBox

# 计时器类
class Timer:
    def __init__(self, textbox:TextBox):
        '''
            初始化计时器
            textbox：文本框
        '''

        # 连接属性
        self.textbox = textbox

        self.clock = pygame.time.Clock()  # 计时器
        self.miliseconds = 0  # 计时器时间（毫秒数）
        self.is_stop = True  # 是否暂停
        self._screen = None

    def draw_text(self, screen:Surface):
        '''
            绘制文本内容
            screen：窗口
        '''

        self.textbox.draw(screen)

    def run(self,screen:Surface):
        '''
            运行计时器
            screen：窗口
        '''

        # 如果计时器没暂停
        if not self.is_stop:
            self.clock.tick()  # 调用tick方法
            self.miliseconds += self.clock.get_time()  # 获取前两次调用 Clock.tick()之间传递的毫秒数
            self._screen = screen
            self._refresh_text(screen)

    def _refresh_text(self, screen):
        seconds = self.miliseconds // 1000
        minutes = seconds // 60
        self.textbox.updateContent(screen, f"用时：{minutes % 60:02d}:{seconds % 60:02d}")

    def stop(self):
        '''
            暂停计时器
        '''

        # 如果计时器正在运行
        if not self.is_stop:
            self.is_stop = True  # 暂停
            self.clock.tick()  # 更新两次tick()的时间间隔
            # Codex-assisted: retain the last segment of this turn.
            self.miliseconds += self.clock.get_time()
            if self._screen is not None:
                self._refresh_text(self._screen)

    def start(self,screen:Surface):
        '''
            开始运行计时器
            screen：窗口
        '''

        # 如果计时器暂停
        if self.is_stop:
            self.is_stop = False  # 不暂停
            self.clock.tick()  # 更新两次tick()的时间间隔
            self.run(screen)  # 执行运行

    def reset(self,screen:Surface):
        '''
            重置计时器
            screen：窗口
        '''

        self.__init__(self.textbox)  # 重新初始化
        self.draw_text(screen)  # 重新绘制
