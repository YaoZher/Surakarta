import pygame
from pygame import Color, Surface, Rect

from Class import Theme
from Class.Element.TextBox import TextBox
from Class.Element.Timer import Timer
from Class.Element.Button import Button

# 控制面板类
class ControlPanel:
    def __init__(self, up: int, down: int, left: int, right: int, info: str, name: str):
        '''
            初始化控制面板
            up：上边界纵坐标
            down：下边界纵坐标
            left：左边界横坐标
            right：右边界横坐标
            info：用户信息
            name：用户姓名
        '''

        # 链接属性
        self.up = up
        self.down = down
        self.left = left
        self.right = right
        self.info = info
        self.name = name

        self.width = right - left  # 控制面板界面宽度（300）
        self.height = down - up  # 控制面板界面宽度（300）
        self.rect = Rect(left, up, self.width, self.height)  # 所在矩形区域
        self.spacing = 12
        self.bgcolor = Theme.SURFACE

        self.text_title = TextBox(up + 14, up + 48, left + 18, right - 18, info, Theme.FONT_BOLD, 22, Theme.TEXT_PRIMARY, self.bgcolor)
        self.text_name = TextBox(up + 52, up + 82, left + 18, right - 18, '玩家：' + name, Theme.FONT_REGULAR, 17, Theme.TEXT_SECONDARY, self.bgcolor)
        self.timer = Timer(TextBox(up + 90, up + 126, left + 18, right - 18, '用时  00:00', Theme.FONT_BOLD, 20, Theme.TEXT_PRIMARY, self.bgcolor))
        half = self.width // 2
        self.buttons = [
            Button(TextBox(up + 148, up + 192, left + 18, left + half - 6, '人类', Theme.FONT_REGULAR, 17, Theme.PRIMARY, Theme.SURFACE_ALT), Theme.SEPARATOR, self.bgcolor, Theme.PRIMARY_SOFT, 1),
            Button(TextBox(up + 148, up + 192, left + half + 6, right - 18, 'AI', Theme.FONT_REGULAR, 17, Theme.PRIMARY, Theme.SURFACE_ALT), Theme.SEPARATOR, self.bgcolor, Theme.PRIMARY_SOFT, 1),
            Button(TextBox(up + 212, up + 256, left + 18, left + half - 6, '暂停', Theme.FONT_REGULAR, 17, Theme.TEXT_PRIMARY, Theme.SURFACE_ALT), Theme.SEPARATOR, self.bgcolor, Theme.PRIMARY_SOFT, 0),
            Button(TextBox(up + 212, up + 256, left + half + 6, right - 18, '继续', Theme.FONT_REGULAR, 17, Theme.TEXT_PRIMARY, Theme.SURFACE_ALT), Theme.SEPARATOR, self.bgcolor, Theme.PRIMARY_SOFT, 0)
        ]

    def drawButton(self, screen:Surface):
        '''
            绘制按钮
            screen：窗口
        '''

        for button in self.buttons:
            # 按钮可用，直接绘制
            if button.is_abled:
                button.abled()
                button.draw(screen)
            # 按钮不可用，改变按钮背景色再绘制
            else:
                button.disabled()
                button.draw(screen)

    def draw(self, screen: Surface):
        '''
            绘制控制面板
            screen：窗口
        '''

        card = self.rect.inflate(-12, -4)
        pygame.draw.rect(screen, self.bgcolor, card, border_radius=Theme.CORNER_RADIUS)
        pygame.draw.rect(screen, Theme.SEPARATOR, card, 1, border_radius=Theme.CORNER_RADIUS)

        # 绘制元件
        self.text_title.draw(screen)
        self.text_name.draw(screen)
        self.timer.draw_text(screen)
        self.drawButton(screen)


    def is_outside_buttons(self, pos:tuple):
        '''
            判断鼠标执行操作时的位置在界面内且在所有按钮外
            pos：鼠标执行操作时的坐标
        '''

        if self.rect.collidepoint(pos):
            for button in self.buttons:
                if button.is_inside(pos):
                    return False
            return True
        return False

    def mouseOver_Leave(self, screen: Surface, pos: tuple):
        '''
            鼠标悬浮及离开
            screen：窗口
            pos：鼠标位置
        '''

        # 位置满足一定范围（菜单范围）才判定
        if self.left <= pos[0] <= self.right and self.up <= pos[1] <= self.down:
            for button in self.buttons:
                # 按钮可用且鼠标位置在按钮内，按钮背景色变为响应色，鼠标变手型
                if button.is_abled and button.is_inside(pos):
                    button.mouseOver()
                    button.draw(screen)
                    break
                # 按钮可用且鼠标位置不在按钮内，复原
                elif button.is_abled and self.is_outside_buttons(pos):
                    button.mouseLeave()
                    button.draw(screen)

    def activate(self, screen: Surface):
        '''
            激活面板（主要指计时器按钮）
            screen：窗口
        '''

        self.buttons[0].is_abled = False  # “人类”按钮不可用
        self.buttons[1].is_abled = False  # “人机”按钮不可用
        self.buttons[2].is_abled = True  # “暂停”按钮可用
        self.buttons[3].is_abled = True  # “继续”按钮可用

        self.drawButton(screen)

    def deactivate(self, screen: Surface):
        '''
            停用面板（主要指计时器按钮）
            screen：窗口
        '''

        for button in self.buttons:
            button.is_abled = False

        self.drawButton(screen)

    def gameOver(self, screen: Surface):
        '''
            游戏结束相关变化
            screen：窗口
        '''

        self.buttons[2].is_abled = False  # “暂停”按钮不可用
        self.buttons[3].is_abled = False  # “继续”按钮不可用
        self.draw(screen)
