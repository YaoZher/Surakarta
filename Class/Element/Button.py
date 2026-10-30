#导入pygame库
import pygame
from pygame import Color, Surface
from pygame.locals import SYSTEM_CURSOR_HAND, SYSTEM_CURSOR_ARROW

from Class import Theme
from Class.Element.TextBox import TextBox

class Button:
    def __init__(self, textbox:TextBox, bdcolor:Color, bgcolor:Color, active_color:Color, is_abled:bool):
        '''
            初始化按钮
            textbox：文本框
            bdcolor：边框颜色
            bgcolor：按钮所处区域背景色
            active_color：按钮响应颜色
            is_abled：是否可用
        '''

        # 链接属性
        self.textbox = textbox
        self.bdcolor = bdcolor
        self.bgcolor = bgcolor
        self.active_color = active_color
        self.is_abled = is_abled

        self.button_bgcolor = textbox.bgcolor  # 按钮背景色
        self.button_textcolor = textbox.ftcolor
        self.rect = self.textbox.rect

    def abled(self):
        '''
            按钮可用，改变按钮颜色为按钮原本颜色
        '''

        self.textbox.bgcolor = self.button_bgcolor
        self.textbox.ftcolor = self.button_textcolor
        self.textbox.refresh_text()

    def disabled(self):
        '''
            按钮不可用，改变按钮颜色为背景色
        '''

        self.textbox.bgcolor = Theme.DISABLED_FILL
        self.textbox.ftcolor = Theme.DISABLED_TEXT
        self.textbox.refresh_text()

    def activate(self):
        '''
            按钮响应，改变按钮颜色为响应颜色
        '''

        self.textbox.bgcolor = self.active_color

    def draw(self, screen:Surface):
        '''
            绘制按钮
            screen：窗口
        '''

        pygame.draw.rect(screen, self.textbox.bgcolor, self.rect, border_radius=Theme.CORNER_RADIUS)
        pygame.draw.rect(screen, self.bdcolor, self.rect, 1, border_radius=Theme.CORNER_RADIUS)
        self.textbox.draw_text(screen)

    def is_inside(self, pos:tuple):
        '''
            判断鼠标执行操作时的位置在按钮内
            pos：鼠标执行操作时的坐标
        '''

        return self.rect.collidepoint(pos)

    def mouseOver(self):
        '''
            鼠标经过
        '''

        self.activate()  # 按钮颜色变为响应颜色
        pygame.mouse.set_system_cursor(SYSTEM_CURSOR_HAND)  # 鼠标形状变为手型

    def mouseLeave(self):
        '''
            鼠标离开
        '''

        self.abled()  # 按钮颜色还原
        pygame.mouse.set_system_cursor(SYSTEM_CURSOR_ARROW)  # 鼠标形状还原

    def Clicked(self, pos):
        '''
            按钮被点击
            pos：鼠标点击时的坐标
        '''

        if self.is_inside(pos):
            print("button clicked")
