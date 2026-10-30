# 导入pygame库
import pygame
from pygame import Color, Surface, Rect

from Class import Theme, I18n
from Class.Element.Button import Button
from Class.Element.TextBox import TextBox


class MyMenu:
    def __init__(self, height: int, left: int, right: int):
        '''
            初始化菜单
            height：菜单高度
            left：菜单左边界横坐标
            right：菜单右边界横坐标
        '''

        # 连接属性
        self.height = height
        self.left = left
        self.right = right

        self.width = right - left  # 菜单宽度（200）
        self.bgcolor = Theme.SURFACE
        self.rect = Rect(self.left, 0, self.width, self.height)  # 所在矩形区域
        self.title = TextBox(24, 64, self.left + 16, self.right - 16, '操作', Theme.FONT_BOLD, 22, Theme.TEXT_PRIMARY, self.bgcolor, False)
        self.button_contents = ['开始', '重来','导出棋谱','退出']  # 按钮内容
        self.buttons = []
        for index, content in enumerate(self.button_contents):
            top = 92 + index * 76
            primary = index == 0
            text_color = (255, 255, 255) if primary else (Theme.DANGER if index == 3 else Theme.TEXT_PRIMARY)
            fill = Theme.PRIMARY if primary else Theme.SURFACE_ALT
            active = Theme.PRIMARY_HOVER if primary else Theme.PRIMARY_SOFT
            self.buttons.append(
                Button(
                    TextBox(top, top + 52, self.left + 16, self.right - 16, content, Theme.FONT_REGULAR, 19, text_color, fill),
                    Theme.PRIMARY if primary else Theme.SEPARATOR,
                    self.bgcolor,
                    active,
                    1,
                )
            )

        # 初始“重来”和“打谱”按钮不可用
        self.buttons.append(
            Button(
                TextBox(396, 448, self.left + 16, self.right - 16, "设置", Theme.FONT_REGULAR, 17, Theme.TEXT_PRIMARY, Theme.SURFACE_ALT),
                Theme.SEPARATOR,
                self.bgcolor,
                Theme.PRIMARY_SOFT,
                1,
            )
        )
        self.buttons[1].is_abled = False
        self.buttons[2].is_abled = False
        self.buttons.append(
            Button(
                TextBox(472, 524, self.left + 16, self.right - 16, "联网对战", Theme.FONT_REGULAR, 17, Theme.TEXT_PRIMARY, Theme.SURFACE_ALT),
                Theme.SEPARATOR, self.bgcolor, Theme.PRIMARY_SOFT, 1,
            )
        )
        self.language_button = Button(
            TextBox(548, 600, self.left + 16, self.right - 16, 'العربية', Theme.FONT_REGULAR, 19,
                    Theme.PRIMARY, Theme.PRIMARY_SOFT),
            Theme.SEPARATOR, self.bgcolor, Theme.PRIMARY_SOFT, 1,
        )
        self.buttons.append(self.language_button)

    def draw(self, screen: Surface):
        '''
            绘制菜单
            screen：窗口
        '''

        self.language_button.textbox.content = '中文' if I18n.is_rtl() else 'العربية'
        pygame.draw.rect(screen, self.bgcolor, self.rect)
        pygame.draw.line(screen, Theme.SEPARATOR, self.rect.topleft, self.rect.bottomleft)
        self.title.draw(screen)

        # 绘制按钮
        for button in self.buttons:
            # 按钮可用，直接绘制
            if button.is_abled:
                button.abled()  # 恢复先前禁用状态的文字与底色
                button.draw(screen)
            # 按钮不可用，改变按钮背景色再绘制
            else:
                button.disabled()
                button.draw(screen)

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
        if self.left <= pos[0] <= self.right:
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


    def mouseClick(self, pos: tuple):
        '''
            鼠标点击
            pos：鼠标点击时的位置
        '''

        # 遍历按钮列表，返回被点击按钮索引
        for i in range(len(self.buttons)):
            if self.buttons[i].is_abled and self.buttons[i].is_inside(pos):
                return i

    def gameStart(self, screen: Surface):
        '''
            游戏开始相关变化
            screen：窗口
        '''

        self.buttons[0].is_abled = False  # “开始”按钮不可用
        self.buttons[1].is_abled = True  # “重来”按钮可用
        self.buttons[2].is_abled = True
        self.buttons[4].is_abled = False  # 避免对局中重置AI时钟与历史
        self.buttons[5].is_abled = False
        self.draw(screen)

    def gameOver(self, screen: Surface):
        '''
            游戏结束相关变化
            screen：窗口
        '''

        self.buttons[2].is_abled = True  # “打谱”按钮可用
        self.buttons[4].is_abled = True
        self.buttons[5].is_abled = True
        self.draw(screen)

    def output(self, screen: Surface):
        '''
            打谱完相关变化
            screen：窗口
        '''

        self.buttons[2].is_abled = True  # 同一局可再次导出独立文件
        self.draw(screen)
