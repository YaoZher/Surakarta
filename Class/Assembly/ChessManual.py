#导入pygame库
import pygame
from pygame import Color, Surface, Rect

from Class import Theme
from Class.Element.TextBox import TextBox

# 棋谱类
class ChessManual:
    def __init__(self, up:int, down:int, left:int, right:int, bgcolor:Color):
        '''
            初始化棋谱
            up：上边界纵坐标
            down：下边界纵坐标
            left：左边界横坐标
            right：右边界横坐标
            bgcolor：背景颜色
        '''

        # 连接属性
        self.up = up
        self.down = down
        self.left = left
        self.right = right
        self.bgcolor = Theme.SURFACE

        self.width = right - left - 20  # 棋谱宽度（180）
        self.height = down - up  # 棋谱高度（690）
        self.rect = Rect(left, up, right - left, self.height)
        self.spacing = 24
        self.content_top = self.up + 64
        self.max_rows = 25
        self.title = TextBox(self.up + 18, self.up + 52, self.left + 14, self.right - 14, '对局记录', Theme.FONT_BOLD, 20, Theme.TEXT_PRIMARY, self.bgcolor, False)
        self.textboxes = []  # 文本框列表
        self.index_now = 0  # 文本框列表已输出索引
        self.record = []  # 记录列表

    def draw(self, screen:Surface):
        '''
            绘制棋谱
            screen：窗口
        '''

        pygame.draw.rect(screen, self.bgcolor, self.rect)  # 绘制矩形区域
        pygame.draw.line(screen, Theme.SEPARATOR, self.rect.topleft, self.rect.bottomleft)
        self.title.draw(screen)  # 绘制标题文本框

    def gameStart(self, screen:Surface):
        '''
            游戏开始输出初始棋谱
            screen：窗口
        '''

        contents = ['!BBBBBB', '!BBBBBB', '!000000', '!000000', '!RRRRRR', '!RRRRRR', ] # 棋谱初始化信息

        # 遍历棋谱初始化信息并添加记录和文本框
        for i in range(len(contents)):
            index = self.index_now + i
            self.record.append(contents[i])
            self.textboxes.append(
                TextBox(self.content_top + index * self.spacing, self.content_top + (index + 1) * self.spacing, self.left + 14, self.right - 10,
                        contents[i], Theme.FONT_REGULAR, 15, Theme.TEXT_SECONDARY, self.bgcolor, False))

        # 遍历未输出文本框并绘制
        for text in self.textboxes[self.index_now:]:
            text.draw(screen)
            self.index_now += 1  # index_now递增

    def refresh(self, screen:Surface):
        '''
            输出信息超出22行上限时刷新
            screen：窗口
        '''

        self.draw(screen)  # 重新绘制覆盖实现刷新

    def addRecord(self, screen:Surface, new_record:str):
        '''
            添加记录
            screen：窗口
            new_record：新记录
        '''

        # 判断刷新
        if self.index_now % self.max_rows == 0:
            self.refresh(screen)

        index = self.index_now
        self.record.append(new_record)  # 添加记录

        # 添加文本框并绘制
        up = self.content_top + (index % self.max_rows) * self.spacing
        down = up + self.spacing
        self.textboxes.append(TextBox(up, down, self.left + 14, self.right - 10, f"{self.index_now - 5:<4d}" + new_record, Theme.FONT_REGULAR, 15, Theme.TEXT_PRIMARY, self.bgcolor, False))
        self.textboxes[-1].draw(screen)

        self.index_now += 1  # index_now递增

    def addResult(self, screen:Surface, result:str):
        '''
            添加结果
            screen：窗口
            result：结果
        '''

        # 判断刷新
        if self.index_now % self.max_rows == 0:
            self.refresh(screen)

        index = self.index_now
        self.record.append(result)  # 添加记录

        # 添加文本框并绘制
        up = self.content_top + (index % self.max_rows) * self.spacing
        down = up + self.spacing
        self.textboxes.append(TextBox(up, down, self.left + 14, self.right - 10, result, Theme.FONT_BOLD, 15, Theme.DANGER, self.bgcolor, False))
        self.textboxes[-1].draw(screen)

        self.index_now += 1  # index_now递增
