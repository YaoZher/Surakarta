import pygame.draw
import pygame.gfxdraw
from pygame import Color, Surface, Rect

from Class import Theme
from Class.Element.CircleArea import CircleArea

# 棋类
class Chess:
    def __init__(self, pos:tuple, radius:int, color:Color, bgcolor:Color):
        '''
            初始化棋类
            pos:圆心坐标
            radius：棋的半径
            color：棋的颜色
            bgcolor：背景色（即棋盘颜色）
        '''

        # 链接属性
        self.pos = pos
        self.radius = radius
        self.color = color
        self.bgcolor = bgcolor

        self.x = pos[0]  # 圆心横坐标
        self.y = pos[1]  # 圆心纵坐标
        self.circle = CircleArea(pos, radius)  # 棋子所在圆域
        self.rect = Rect(0, 0, 50, 50)  # 棋子响应矩形域大小
        self.rect.center = pos  # 调整矩形域位置以棋子圆心为中心
        self.selected = False
        # self.is_visible = False  # 棋子是否可见（棋盘点上都含有棋子，棋子不可见则对应坐标点没有棋子）

    def draw(self, screen:Surface):
        '''
            绘制棋子
            screen:窗口
        '''

        self.draw_piece_at(screen, self.pos, self.radius, self.color, self.selected)

    @staticmethod
    def draw_piece_at(screen: Surface, pos: tuple, radius: int, color: Color, selected: bool = False):
        x, y = round(pos[0]), round(pos[1])
        fill = Theme.BLACK_PIECE if color == Color("black") else Theme.RED_PIECE
        pygame.gfxdraw.filled_circle(screen, x, y + 2, radius, Theme.PIECE_SHADOW)
        pygame.gfxdraw.filled_circle(screen, x, y, radius, fill)
        pygame.gfxdraw.aacircle(screen, x, y, radius, Theme.PIECE_BORDER)
        if selected:
            pygame.draw.circle(screen, Theme.PRIMARY, (x, y), radius + 6, 3)

    def clear(self, screen:Surface):
        '''
            消除棋子（即用背景色绘制棋子）
            screen:窗口
        '''

        pygame.draw.circle(screen, self.bgcolor, self.pos, self.radius + 7)

    def clicked(self, screen:Surface):
        '''
            棋子被点击
            screen:窗口
        '''

        self.selected = True
        self.draw(screen)

    def unclicked(self, screen:Surface):
        '''
            棋子没被点击
            screen:窗口
        '''

        self.selected = False
