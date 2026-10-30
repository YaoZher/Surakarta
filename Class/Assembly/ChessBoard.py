# 导入pygame库
import pygame
from pygame import Rect, Color, Surface

from Class import Theme
from Class.Settings import AISettings
from Class.Globals import Globals
from Class.Element.SearchAI import SearchAI
from Class.Element.Animation import interpolate_capture_route, interpolate_line
from Class.Element.Chess import Chess
from Class.Element.SLoopQueue import SLoopQueue

from engine.rules import find_capture_route

from Func.AADraw import drawAAArcs, drawAACircle
from Func.Convert import from_Coordinate_to_Subscript

# 棋盘类
class ChessBoard:
    def __init__(self, up: int, down: int, left: int, right: int):
        '''
            初始化棋盘
            up：上边界纵坐标
            down：下边界纵坐标
            left：左边界横坐标
            right：右边界横坐标
        '''

        margin = 200  # 边距
        spacing = 60  # 线条间距

        # 链接属性
        self.margin = margin
        self.spacing = spacing
        self.up = up
        self.down = down
        self.left = left
        self.right = right

        self.width = right - left  # 棋盘宽度（700）
        self.height = down - up  # 棋盘高度（700）
        self.board_color = Theme.BOARD_BG  # 棋盘颜色
        self.rect = Rect(left, up, self.width, self.height)  # 所在矩形区域
        self.bgcolor = Theme.APP_BG
        self.row_marks = "  123456  "  # 行编号
        self.col_marks = "  ABCDEF  "  # 列编号

        # （扩展）棋盘坐标点坐标列表
        self.board_point_locs = [[(j, i) for j in range(up + margin - 2 * spacing, down - margin + 2 * spacing + 1, spacing)]
                           for i in range(left + margin - 2 * spacing, right - margin + 2 * spacing + 1, spacing)]

        # 棋坐标列表
        self.chess_locs = [[] for _ in range(10)]

        # 环坐标循环队列与吃法列表
        self.green_loop = SLoopQueue(32)
        self.blue_loop = SLoopQueue(32)
        self.eat_methods = []
        self.animation_ms = 240
        self.capture_animation_ms = 700
        self.animation_fps = 60
        self.selected_position = None
        self.move_hints = []

        # AI
        self.ai_black = SearchAI(Color('black'))
        self.ai_red = SearchAI(Color('red'))
        self.last_ai = None

    def apply_ai_settings(self, settings: AISettings) -> None:
        """Apply one shared UI configuration to both colour adapters."""
        value = settings.normalized()
        for ai in (self.ai_black, self.ai_red):
            ai.configure(
                depth=value.depth,
                time_ms=value.time_ms,
                total_time_ms=value.total_time_ms,
                eval_profile=value.eval_profile,
            )

    def drawBoard(self, screen:Surface):
        '''
            绘制棋盘
            screen：窗口
        '''

        pygame.draw.rect(screen, self.bgcolor, self.rect)
        board_surface = self.rect.inflate(-24, -24)
        pygame.draw.rect(screen, self.board_color, board_surface, border_radius=Theme.CORNER_RADIUS)
        pygame.draw.rect(screen, Theme.SEPARATOR, board_surface, 1, border_radius=Theme.CORNER_RADIUS)

    def drawBoardLines(self, screen: Surface):
        '''
            绘制棋盘线
            screen：窗口
        '''

        # 绘制横线与竖线
        for i in range(6):
            # 扩展棋盘起止索引分别为2，7
            pygame.draw.aaline(screen, Theme.BOARD_LINE, self.board_point_locs[2][i + 2], self.board_point_locs[7][i + 2])
            pygame.draw.aaline(screen, Theme.BOARD_LINE, self.board_point_locs[i + 2][2], self.board_point_locs[i + 2][7])

        # 棋盘线四个角的修正坐标
        cornors = [[self.margin - 1, self.up + self.margin - 1], [self.margin - 1, self.down - self.margin + 2],
                   [self.right - self.margin + 2, self.down - self.margin + 2], [self.right - self.margin + 2, self.up + self.margin - 1]]

        # 绘制弧线
        for i in range(4):
            drawAAArcs(screen, cornors[i][0], cornors[i][1], self.spacing, Theme.INNER_LOOP, 0 + 90 * i, 270 + 90 * i, 240, 2)
            drawAAArcs(screen, cornors[i][0], cornors[i][1], 2 * self.spacing, Theme.OUTER_LOOP, 0 + 90 * i, 270 + 90 * i, 360, 2)

    def drawBoardPoint(self, screen:Surface):
        '''
            绘制棋盘坐标点
            screen：窗口
        '''

        for i in range(self.margin, self.right - self.margin + 1, self.spacing):
            for j in range(self.up + self.margin, self.down - self.margin + 1, self.spacing):
                pygame.draw.circle(screen, Theme.BOARD_POINT, (i + 1, j + 1), 3)

    def writeMarks(self, screen:Surface):
        '''
            写棋盘编号
            screen：窗口
        '''

        # 字体设置
        mark_font = pygame.font.Font(Theme.FONT_REGULAR, 16)
        for index, label in enumerate("ABCDEF"):
            point = self.board_point_locs[2][index + 2]
            text = mark_font.render(label, True, Theme.TEXT_SECONDARY)
            screen.blit(text, text.get_rect(center=(point[0], point[1] - 44)))
        for index, label in enumerate("123456"):
            point = self.board_point_locs[index + 2][2]
            text = mark_font.render(label, True, Theme.TEXT_SECONDARY)
            screen.blit(text, text.get_rect(center=(point[0] - 44, point[1])))

    def draw(self, screen:Surface):
        '''
            绘制整个棋盘
            screen：窗口
        '''

        self.drawBoard(screen)
        self.drawBoardLines(screen)
        self.drawBoardPoint(screen)
        self.writeMarks(screen)

    def initChess(self):
        '''
            初始化棋子颜色及位置
        '''

        for i in range(10):
            for j in range(10):
                # 黑棋
                if i in range(2, 4):
                    if j in range(2, 8):
                        self.chess_locs[i].append(Chess(self.board_point_locs[i][j], 22, Color('black'), self.board_color))
                    else:
                        self.chess_locs[i].append(Chess(self.board_point_locs[i][j], 22, Color('white'), self.board_color))
                # 红棋
                elif i in range(6, 8):
                    if j in range(2, 8):
                        self.chess_locs[i].append(Chess(self.board_point_locs[i][j], 22, Color('red'), self.board_color))
                    else:
                        self.chess_locs[i].append(Chess(self.board_point_locs[i][j], 22, Color('white'), self.board_color))
                # 白棋（代表棋盘点为空格）
                else:
                    self.chess_locs[i].append(Chess(self.board_point_locs[i][j], 22, Color('white'), self.board_color))

    def initLoop(self):
        '''
            初始化循环队列
        '''

        # 如果棋子没有初始化，则初始化
        if not self.chess_locs[0]:
            self.initChess()

        # 左侧棋子坐标入队
        for i in range(2, 8):
            self.green_loop.enQueue(self.chess_locs[i][3])
            self.blue_loop.enQueue(self.chess_locs[i][4])
            # print((i + 1, 1 + 1), (i + 1, 2 + 1))

        # 左下角弧整数点（属于扩展棋盘）入队
        self.green_loop.enQueue(self.chess_locs[8][2])
        self.green_loop.enQueue(self.chess_locs[7][1])
        self.blue_loop.enQueue(self.chess_locs[9][2])
        self.blue_loop.enQueue(self.chess_locs[7][0])

        # 下侧棋子坐标入队
        for j in range(2, 8):
            self.green_loop.enQueue(self.chess_locs[6][j])
            self.blue_loop.enQueue(self.chess_locs[5][j])
            # print((4 + 1, j + 1), (3 + 1, j + 1))

        # 右下角弧整数点（属于扩展棋盘）入队
        self.green_loop.enQueue(self.chess_locs[7][8])
        self.green_loop.enQueue(self.chess_locs[8][7])
        self.blue_loop.enQueue(self.chess_locs[7][9])
        self.blue_loop.enQueue(self.chess_locs[9][7])

        # 右侧棋子坐标入队
        for i in range(7, 1, -1):
            self.green_loop.enQueue(self.chess_locs[i][6])
            self.blue_loop.enQueue(self.chess_locs[i][5])
            # print((5 - i + 1, 4 + 1), (5 - i + 1, 3 + 1))

        # 右上角弧整数点（属于扩展棋盘）入队
        self.green_loop.enQueue(self.chess_locs[1][7])
        self.green_loop.enQueue(self.chess_locs[2][8])
        self.blue_loop.enQueue(self.chess_locs[0][7])
        self.blue_loop.enQueue(self.chess_locs[2][9])

        # 上侧棋子坐标入队
        for j in range(7, 1, -1):
            self.green_loop.enQueue(self.chess_locs[3][j])
            self.blue_loop.enQueue(self.chess_locs[4][j])
            # print((1 + 1, 5 - j + 1), (2 + 1, 5 - j + 1))

        # 左上角弧整数点（属于扩展棋盘）入队
        self.green_loop.enQueue(self.chess_locs[2][1])
        self.green_loop.enQueue(self.chess_locs[1][2])
        self.blue_loop.enQueue(self.chess_locs[2][0])
        self.blue_loop.enQueue(self.chess_locs[0][2])

    def updateLoop(self):
        '''
            更新循环队列
        '''

        # 队列元素全部出队
        while not self.green_loop.isEmpty():
            self.green_loop.deQueue()
        while not self.blue_loop.isEmpty():
            self.blue_loop.deQueue()

        self.initLoop()  # 重新初始化

    def drawChess(self, screen:Surface):
        '''
            绘制棋子
            screen：窗口
        '''

        # 如果棋子没有初始化，则初始化
        if not self.chess_locs[0]:
            self.initChess()

        self.updateLoop()  # 更新循环队列

        # 遍历绘制棋子
        for chess_list in self.chess_locs:
            for chess in chess_list:
                # 棋盘点不为空
                if chess.color != Color("white"):
                    chess.draw(screen)
        self.draw_move_hints(screen)

    def legal_move_hints(self, start_pos: tuple) -> list[tuple[tuple[int, int], bool]]:
        if not self.chess_locs[0]:
            self.initChess()
        col, row = start_pos
        if not (2 <= row < 8 and 2 <= col < 8):
            return []
        ai = self.ai_black if Globals.is_black else self.ai_red
        board = ai.to_engine_board(self)
        engine_start = (row - 2, col - 2)
        return [
            ((move.end[1] + 2, move.end[0] + 2), move.is_capture)
            for move in board.legal_moves()
            if move.start == engine_start
        ]

    def set_selected_position(self, start_pos: tuple) -> None:
        self.selected_position = start_pos
        self.move_hints = self.legal_move_hints(start_pos)

    def clear_selection(self) -> None:
        self.selected_position = None
        self.move_hints = []
        for row in self.chess_locs:
            for chess in row:
                chess.selected = False

    def draw_move_hints(self, screen: Surface) -> None:
        if not self.move_hints:
            return
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for (col, row), is_capture in self.move_hints:
            x, y = self.board_point_locs[row][col]
            if is_capture:
                pygame.draw.circle(overlay, Theme.CAPTURE_HINT, (x, y), 29, 4)
                pygame.draw.circle(overlay, Theme.CAPTURE_HINT, (x, y), 4)
            else:
                pygame.draw.circle(overlay, Theme.QUIET_HINT, (x, y), 10)
                pygame.draw.circle(overlay, (255, 255, 255, 220), (x, y), 10, 2)
        screen.blit(overlay, (self.left, self.up))

    def toStr(self, chess:Chess):
        '''
            棋子颜色转化为字符串
            棋子：棋子
        '''

        if chess.color == Color("red"):
            return "R"
        elif chess.color == Color("black"):
            return "B"

    def _animate_move(self, screen: Surface, start_chess: Chess, end_chess: Chess):
        if screen is None or start_chess is None or end_chess is None:
            return

        moving_color = start_chess.color
        start_color = start_chess.color
        end_color = end_chess.color
        is_capture = end_color not in (Color("white"), moving_color)
        duration = self.capture_animation_ms if is_capture else self.animation_ms
        frames = max(2, int(duration / 1000 * self.animation_fps))
        points = self._animation_points(start_chess, end_chess, frames, is_capture)
        clock = pygame.time.Clock()

        self.clear_selection()
        start_chess.color = Color("white")
        try:
            for index, (x, y) in enumerate(points):
                self.draw(screen)
                self.drawChess(screen)
                if is_capture and index > 1:
                    trail = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
                    trail_points = points[max(0, index - 12): index + 1]
                    pygame.draw.lines(
                        trail,
                        Theme.PATH_TRAIL,
                        False,
                        trail_points,
                        3,
                    )
                    pygame.draw.aalines(
                        trail,
                        Theme.PATH_TRAIL,
                        False,
                        trail_points,
                    )
                    screen.blit(trail, (self.left, self.up))
                Chess.draw_piece_at(screen, (x, y), start_chess.radius, moving_color)
                pygame.display.update(self.rect)
                clock.tick(self.animation_fps)
        finally:
            start_chess.color = start_color
            end_chess.color = end_color

    def _animation_points(
        self,
        start_chess: Chess,
        end_chess: Chess,
        frames: int,
        is_capture: bool,
    ) -> list[tuple[int, int]]:
        if not is_capture:
            return interpolate_line(start_chess.pos, end_chess.pos, frames)
        start = self._engine_coord_for_chess(start_chess)
        end = self._engine_coord_for_chess(end_chess)
        if start is None or end is None:
            return interpolate_line(start_chess.pos, end_chess.pos, frames)
        ai = self.ai_black if start_chess.color == Color("black") else self.ai_red
        board = ai.to_engine_board(self)
        route = find_capture_route(board, start, end)
        if route is None:
            return interpolate_line(start_chess.pos, end_chess.pos, frames)
        return interpolate_capture_route(
            route,
            board_origin=self.board_point_locs[2][2],
            spacing=self.spacing,
            frames=frames,
        )

    def _engine_coord_for_chess(self, target: Chess):
        for row in range(2, 8):
            for col in range(2, 8):
                if self.chess_locs[row][col] is target:
                    return row - 2, col - 2
        return None

    def chooseChess(self, pos:tuple):
        '''
            选择要移动的棋子，返回选中的棋子（没选中返回None）
            pos：鼠标点击时的位置
        '''

        for i in range(2, 8):
            for j in range(2, 8):
                chess = self.chess_locs[i][j]
                if ((Globals.is_black and chess.color == Color('black')  or
                    not Globals.is_black and chess.color == Color('red')) and
                        chess.rect.collidepoint(pos)):
                    return chess, (j,i)
        return None, None

    def chooseLoc(self, pos:tuple):
        '''
            选择棋子要移动的位置，返回位置的坐标
            pos：鼠标点击时的位置
        '''

        for i in range(2, 8):
            for j in range(2, 8):
                chess = self.chess_locs[i][j]
                if chess.rect.collidepoint(pos):
                    return (j,i)

    def eatChess(self, screen:Surface, start_pos:tuple, end_pos:tuple):
        '''
            吃子，返回能否成功吃子的布尔值
            screen：窗口
            start_pos, end_pos：始末坐标
        '''

        can_eat = False
        # 始末坐标均不为空
        if start_pos and end_pos:
            row1, row2 = start_pos[1], end_pos[1]  # 数组第二坐标对应横坐标
            col1, col2 = start_pos[0], end_pos[0]  # 数组第一坐标对应纵坐标
            chess1, chess2 = self.chess_locs[row1][col1], self.chess_locs[row2][col2]  # 始末坐标对应下标的棋子

            # 二棋子颜色不同且chess2不为空白
            if chess1.color != chess2.color and chess2.color != Color("white"):
                loops = []  # 新循环轨道列表
                green_special = [self.chess_locs[1][2], self.chess_locs[2][1], self.chess_locs[1][7], self.chess_locs[2][8],
                                 self.chess_locs[7][1], self.chess_locs[8][2], self.chess_locs[7][8], self.chess_locs[8][7]]
                blue_special = [self.chess_locs[0][2], self.chess_locs[2][0], self.chess_locs[0][7], self.chess_locs[2][9],
                                self.chess_locs[7][0], self.chess_locs[9][2], self.chess_locs[7][9], self.chess_locs[9][7]]

                # 两个棋子都在内环轨道（绿色轨道）
                if self.green_loop.isBothInQueue(chess1, chess2):
                    # 计算新循环轨道并添加入存放数组
                    for i in range(2):
                        index1 = self.green_loop.elements.index(chess1)  # 棋子1在原循环轨道索引
                        loops.append(self.green_loop.traverseBackwards(index1))  # 计算以棋子1为首元素向后遍历的新循环轨道并存储
                        loops.append(self.green_loop.traverseForwards(index1))  # 计算以棋子1为首元素向前遍历的新循环轨道并存储
                        self.green_loop.elements.reverse()  # 换向

                # 两个棋子都在外环轨道（蓝色轨道）
                if self.blue_loop.isBothInQueue(chess1, chess2):
                    # 计算新循环轨道并添加入存放数组
                    for i in range(2):
                        index1 = self.blue_loop.elements.index(chess1)  # 棋子1在原循环轨道索引
                        loops.append(self.blue_loop.traverseBackwards(index1))  # 计算以棋子1为首元素向后遍历的新循环轨道并存储
                        loops.append(self.blue_loop.traverseForwards(index1))  # 计算以棋子1为首元素向前遍历的新循环轨道并存储
                        self.blue_loop.elements.reverse()  # 换向

                # 遍历新循环轨道数组
                for loop in loops:
                    index2 = loop.index(chess2)  # 棋子2在新循环轨道中的索引
                    pass_arc = False    # 是否经过弧线

                    # 吃子index2至少为3，<3直接不用考虑
                    if index2 >= 3:
                        # 遍历新循环轨道中的棋子
                        for chess in loop:
                            # 如果能成功到达chess2并且经过弧线，则可以吃子
                            if chess == chess2 and pass_arc:
                                can_eat = True
                                break

                            # chess属于内环特殊点或外环特殊点，说明经过弧线
                            if chess in green_special or chess in blue_special:
                                pass_arc = True

                            # 如果到达chess2的途中有己方或对方的棋子，则无法吃子
                            if chess != chess1 and chess.color != Color('white'):
                                can_eat = False
                                break

                        # 可以吃子，存储吃法轨迹
                        if can_eat:
                            self.eat_methods.append(loop[:index2 + 1])

            # 吃法列表不为空代表成功吃子，输出打印吃法轨迹并返回真
            if self.eat_methods:
                for i in self.eat_methods:
                    for j in i:
                        print(j.pos)
                    print("-------------------")
                self.eat_methods = []  # 重置吃法列表
                if chess1.color == Color('red'):
                    Globals.update_black()
                else:
                    Globals.update_red()

                # 计算记录并写入棋谱
                record = self.toStr(chess1) + self.row_marks[row1] + self.col_marks[col1] + '-' + self.row_marks[row2] + self.col_marks[col2]
                Globals.update_step_record(record)

                # 交换始末坐标棋子颜色
                self._animate_move(screen, chess1, chess2)
                chess2.color = chess1.color
                chess1.color = Color("white")

                # 更新棋盘
                self.draw(screen)
                self.drawChess(screen)

                Globals.update_step()
                return True
            return False
        return False



    def moveChess(self, screen:Surface, start_pos:tuple, end_pos:tuple):
        '''
            移动棋子，返回能否成功移动的布尔值
            screen：窗口
            start_pos, end_pos：始末坐标
        '''

        # 无法吃子，考虑移动棋子
        if not self.eatChess(screen, start_pos, end_pos):
            # 始末坐标均不为空
            if start_pos and end_pos:
                row1, row2 = start_pos[1], end_pos[1]  # 数组第二坐标对应横坐标
                col1, col2 = start_pos[0], end_pos[0]  # 数组第一坐标对应纵坐标
                chess1, chess2 = self.chess_locs[row1][col1], self.chess_locs[row2][col2]  # 始末坐标对应下标的棋子

                # 移动距离为1个单位
                if abs(row2 - row1) <= 1 and abs(col2 - col1) <= 1:
                    # 落点为空
                    if chess2.color == Color('white'):
                        # 计算记录并写入棋谱
                        record = self.toStr(chess1) + self.row_marks[row1] + self.col_marks[col1] + '-' + self.row_marks[row2] + self.col_marks[col2]
                        Globals.update_step_record(record)

                        # 交换始末坐标棋子颜色
                        self._animate_move(screen, chess1, chess2)
                        chess2.color = chess1.color
                        chess1.color = Color("white")

                        # 更新棋盘
                        self.draw(screen)
                        self.drawChess(screen)

                        Globals.update_step()
                        return True
            return False
        return True

    def startAI(self, is_black:bool):
        '''
            启用AI
            is_black: 是否黑方
        '''

        if is_black:
            self.ai_black.is_start = True
        else:
            self.ai_red.is_start = True

    def stopAI(self, is_black:bool):
        '''
            停用AI
            is_black: 是否黑方
        '''

        if is_black:
            self.ai_black.is_start = False
        else:
            self.ai_red.is_start = False

    def eatChess_AI(self, start_chess:Chess, end_chess:Chess):
        '''
            AI吃子
            screen：窗口
            start_chess, end_chess：始末棋子
        '''

        can_eat = False
        # 二棋子颜色不同且end_chess不为空白
        if start_chess.color != end_chess.color and end_chess.color != Color('white'):
            loops = []  # 新循环轨道列表
            green_special = [self.chess_locs[1][2], self.chess_locs[2][1], self.chess_locs[1][7], self.chess_locs[2][8],
                             self.chess_locs[7][1], self.chess_locs[8][2], self.chess_locs[7][8], self.chess_locs[8][7]]
            blue_special = [self.chess_locs[0][2], self.chess_locs[2][0], self.chess_locs[0][7], self.chess_locs[2][9],
                            self.chess_locs[7][0], self.chess_locs[9][2], self.chess_locs[7][9], self.chess_locs[9][7]]

            # 两个棋子都在内环轨道（绿色轨道）
            if self.green_loop.isBothInQueue(start_chess, end_chess):
                # 计算新循环轨道并添加入存放数组
                for i in range(2):
                    index1 = self.green_loop.elements.index(start_chess)  # 开始棋子在原循环轨道索引
                    loops.append(self.green_loop.traverseBackwards(index1))  # 计算以开始棋子为首元素向后遍历的新循环轨道并存储
                    loops.append(self.green_loop.traverseForwards(index1))  # 计算以开始棋子为首元素向前遍历的新循环轨道并存储
                    self.green_loop.elements.reverse()  # 换向

            # 两个棋子都在外环轨道（蓝色轨道）
            if self.blue_loop.isBothInQueue(start_chess, end_chess):
                # 计算新循环轨道并添加入存放数组
                for i in range(2):
                    index1 = self.blue_loop.elements.index(start_chess)  # 开始棋子在原循环轨道索引
                    loops.append(self.blue_loop.traverseBackwards(index1))  # 计算以开始棋子为首元素向后遍历的新循环轨道并存储
                    loops.append(self.blue_loop.traverseForwards(index1))  # 计算以开始棋子为首元素向前遍历的新循环轨道并存储
                    self.blue_loop.elements.reverse()  # 换向

            # 遍历新循环轨道数组
            for loop in loops:
                index2 = loop.index(end_chess)  # 结束棋子在新循环轨道中的索引
                pass_arc = False  # 是否经过弧线

                # 吃子index2至少为3，<3直接不用考虑
                if index2 >= 3:
                    # 遍历新循环轨道中的棋子
                    for chess in loop:
                        # 如果能成功到达end_chess并且经过弧线，则可以吃子
                        if chess == end_chess and pass_arc:
                            can_eat = True
                            break

                        # chess属于内环特殊点或外环特殊点，说明经过弧线
                        if chess in green_special or chess in blue_special:
                            pass_arc = True

                        # 如果到达chess2的途中有己方或对方的棋子，则无法吃子
                        if chess != start_chess and chess.color != Color('white'):
                            can_eat = False
                            break

                    # 可以吃子，存储吃法轨迹
                    if can_eat:
                        self.eat_methods.append(loop[:index2 + 1])

        # 吃法列表不为空代表成功吃子，输出打印吃法轨迹并返回真
        if self.eat_methods:
            for i in self.eat_methods:
                for j in i:
                    print(j.pos)
                print("-------------------")
            self.eat_methods = []  # 重置吃法列表
            print("可以吃子")
            return True
        return False

    def moveChess_AI(self, start_chess:Chess, end_chess:Chess):
        '''
            移动棋子
            screen：窗口
            start_chess, end_chess：始末坐标
        '''

        # 无法吃子，考虑移动棋子
        if not self.eatChess_AI(start_chess, end_chess):
            row1, col1 = from_Coordinate_to_Subscript(start_chess.pos)
            row2, col2 = from_Coordinate_to_Subscript(end_chess.pos)

            # 移动距离为1个单位
            if abs(row2 - row1) <= 1 and abs(col2 - col1) <= 1:
                # 落点为空
                if end_chess.color == Color('white'):
                    return True
            return False
        return True

    def ai_move(self, screen: Surface):
        '''
            执行AI的移动
            screen:窗口
        '''

        ai = None
        self.clear_selection()

        # 如果黑方AI启用且当前是黑方行棋
        if self.ai_black.is_start and Globals.is_black:
            ai = self.ai_black

        # 如果红方AI启用且当前是红方行棋
        elif self.ai_red.is_start and not Globals.is_black:
            ai = self.ai_red

        if ai is None:
            return None

        self.last_ai = ai
        ai.getChessLocs(self)
        chess1, chess2 = ai.ai_move(self)

        # 判断游戏结束，不行棋
        if Globals.red == 0 or Globals.black == 0:
            return ai
        if chess1 is None or chess2 is None:
            return ai

        # 吃子更新场上棋子数
        if chess1.color == Color('red') and chess2.color == Color('black'):
            Globals.update_black()
        elif chess1.color == Color('black') and chess2.color == Color('red'):
            Globals.update_red()

        row1, col1 = from_Coordinate_to_Subscript(chess1.pos)
        row2, col2 = from_Coordinate_to_Subscript(chess2.pos)

        # 计算记录并写入棋谱
        record = self.toStr(chess1) + self.row_marks[row1] + self.col_marks[col1] + '-' + self.row_marks[row2] + self.col_marks[col2]
        Globals.update_step_record(record)

        # 交换始末坐标棋子颜色
        self._animate_move(screen, chess1, chess2)
        chess2.color = chess1.color
        chess1.color = Color("white")

        # 更新棋盘
        self.draw(screen)
        self.drawChess(screen)

        Globals.update_step()
        return ai
