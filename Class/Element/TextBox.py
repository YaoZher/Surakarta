#导入pygame库
import pygame
from pygame import Color, Surface, Rect
from Class import I18n

# 文本框类
class TextBox:
    def __init__(self, up:int, down:int, left:int, right:int, content:str, ftname:str, ftsize:int, ftcolor:Color, bgcolor:Color, is_center:bool = True):
        '''
            初始化文本框
            up：上边界纵坐标
            down：下边界纵坐标
            left：左边界横坐标
            right：右边界横坐标
            content：文本框内容
            ftname：字体类型名
            ftsize：字体大小
            ftcolor：字体颜色
            bgcolor：背景色
            is_center：是否居中
        '''

        # 链接属性
        self.up = up
        self.down = down
        self.left = left
        self.right = right
        self.content = content
        self.ftname = ftname
        self.ftsize = ftsize
        self.ftcolor = ftcolor
        self.bgcolor = bgcolor
        self.is_center = is_center

        self.width = right - left  # 文本框界面宽度
        self.height = down - up  # 文本框界面宽度
        self.rect = Rect(left, up, self.width, self.height)
        self._fonts = {}
        self._render_signature = None
        self.refresh_text()

    def refresh_text(self, force=False):
        signature = (I18n.language(), self.content, tuple(self.ftcolor), self.ftsize)
        if not force and signature == self._render_signature:
            return
        self.rendered_content = I18n.translate(self.content)
        self.text = I18n.render_text(self.content, self.ftname, self.ftsize, self.ftcolor,
                                    max_width=max(1, self.width - 12), max_height=max(1, self.height - 4), cache=self._fonts)
        self._render_signature = signature
        self._position_text()

    def _position_text(self):
        if self.is_center:
            self.text_rect = self.text.get_rect(center=(self.left + self.width // 2, self.up + self.height // 2))
        elif I18n.is_rtl() and I18n.contains_arabic(self.rendered_content):
            self.text_rect = self.text.get_rect(midright=(self.right - 6, self.up + self.height // 2))
        else:
            self.text_rect = self.text.get_rect(midleft=(self.left + 10, self.up + self.height // 2))

    def draw(self, screen:Surface):
        '''
            绘制文本框
            screen：窗口
        '''

        pygame.draw.rect(screen, self.bgcolor, self.rect)
        self.draw_text(screen)

    def draw_text(self, screen: Surface):
        self.refresh_text()
        screen.blit(self.text, self.text_rect)

    def clear(self, screen:Surface):
        '''
            清空文本框
            screen：窗口
        '''

        pygame.draw.rect(screen, self.bgcolor, self.rect)

    def updateContent(self, screen:Surface, new_content:str):
        '''
            更新文本框内容
            screen：窗口
            content：更新的内容
        '''

        self.content = new_content  # 更新文本内容
        self.refresh_text()
        self.draw(screen)
