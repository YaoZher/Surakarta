from pygame import Color

from Class.Globals import Globals
from Class.Element.Chess import Chess

from Func.Convert import from_Coordinate_to_Subscript

class AI:
    def __init__(self, chess_color:Color):
        # 链接属性
        self.chess_color = chess_color

        self.is_start = False   # 是否启用

        # 棋盘权值（黑方AI）
        self.board_value = [
            [None for _ in range(10)],
            [None for _ in range(10)],
            [None, None, 10, 10, 20, 20, 20, 5, None, None],
            [None, None, 10, 70, 30, 30, 70, 20, None, None],
            [None, None, 30, 30, 50, 40, 40, 20, None, None],
            [None, None, 50, 50, 40, 40, 30, 20, None, None],
            [None, None, 10, 70, 30, 30, 70, 20, None, None],
            [None, None, 10, 10, 20, 20, 20, 5, None, None],
            [None for _ in range(10)],
            [None for _ in range(10)],
        ]

        # # 棋盘权值（红方AI）
        # self.board_value = [
        #     [None for _ in range(10)],
        #     [None for _ in range(10)],
        #     [None, None, 10, 10, 20, 20, 20, 5, None, None],
        #     [None, None, 10, 70, 30, 30, 70, 20, None, None],
        #     [None, None, 30, 30, 50, 40, 40, 20, None, None],
        #     [None, None, 50, 50, 50, 40, 40, 20, None, None],
        #     [None, None, 30, 70, 10, 40, 70, 25, None, None],
        #     [None, None, 10, 10, 20, 20, 20, 5, None, None],
        #     [None for _ in range(10)],
        #     [None for _ in range(10)],
        # ]

        # 执红
        if chess_color == Color('red'):
            self.my_count = Globals.red     # 我方棋子数
            self.op_count = Globals.black   # 敌方棋子数
        # 执黑
        else:
            self.my_count = Globals.black
            self.op_count = Globals.red

        self.chess_value = 200  # 单个棋子的值
        self.my_chess_locs = [] # 我方棋子位置
        self.op_chess_locs = [] # 敌方棋子位置

    def updateCount(self):
        '''
            更新棋子数
        '''

        if self.chess_color == Color('red'):
            self.my_count = Globals.red
            self.op_count = Globals.black
        else:
            self.my_count = Globals.black
            self.op_count = Globals.red

    def getChessLocs(self, chess_board):
        '''
            获取棋子位置
            chess_board:棋盘
        '''

        # 重置双方棋子位置
        self.my_chess_locs = []
        self.op_chess_locs = []

        for i in range(2, 8):
            for j in range(2, 8):
                chess = chess_board.chess_locs[i][j]
                if chess.color != Color('white'):
                    if chess.color == self.chess_color:
                        self.my_chess_locs.append(chess)
                    else:
                        self.op_chess_locs.append(chess)

    def generateMoves(self,chess_board, start_chess:Chess):
        '''
            生成可移动的所有方法
            chess_board:棋盘
            start_chess:要移动的棋子
        '''

        moves = []  # 该要移动的棋子的所有可移动方法
        for i in range(2, 8):
            for j in range(2, 8):
                chess = chess_board.chess_locs[i][j]

                # 要移动的位置没有我方棋子
                if chess not in self.my_chess_locs:
                    # 如果可以移动棋子，则方法添加该要移动的位置
                    if chess_board.moveChess_AI(start_chess, chess):
                        moves.append(chess)

        for move in moves:
            print(move.pos)
        print('------------')
        return moves

    def ai_move(self, chess_board):
        '''
            AI移动
            chess_board:棋盘
        '''

        best_value = float('-inf')  # 最佳值（起始为-∞）
        best_start_chess = None     # 最佳移动棋子
        best_move = None        # 最佳走法

        # 遍历我方在场棋子
        for chess in self.my_chess_locs:
            moves = self.generateMoves(chess_board, chess)  # 生成棋子的所有可行走法

            # 遍历该棋子的可行走法
            for move in moves:
                chess_i, chess_j = from_Coordinate_to_Subscript(chess.pos)
                move_i, move_j = from_Coordinate_to_Subscript(move.pos)

                # 计算值
                value = self.board_value[move_i][move_j] - self.board_value[chess_i][chess_j]
                # 吃子值+100
                if chess.color != move.color and move.color != Color('white'):
                    value += 100

                # 更新最佳变量
                if value > best_value:
                    best_value = value
                    best_start_chess = chess
                    best_move = move

        return best_start_chess, best_move