class Globals:
    game_start = False  # 游戏是否开始
    game_stop = False # 游戏是否暂停
    step_record = None  # 棋谱的单步记录
    chosen_chess = False    # 被选中的棋子
    chosen_chess_index = None   # 被选中的棋子的坐标
    is_black = True     # 当前是否为黑方走子
    black, red = 12, 12 # 黑棋和红棋初始数量
    step = 0    # 当前对局步数

    @classmethod
    def reset(cls):
        '''
            重置全局变量
        '''

        cls.game_start = False
        cls.game_stop = False
        cls.step_record = None
        cls.chosen_chess = False
        cls.is_black = True
        cls.black, cls.red = 12, 12
        cls.step = 0

    @classmethod
    def update_game_start(cls, new_val:bool) -> None:
        '''
            更新game_start
            new_val：要更新的值
        '''

        cls.game_start = new_val

    @classmethod
    def update_game_stop(cls, new_val:bool) -> None:
        '''
            更新game_stop
            new_val：要更新的值
        '''

        cls.game_stop = new_val

    @classmethod
    def update_step_record(cls, new_val:str) -> None:
        '''
            更新step_record
            new_val：要更新的值
        '''

        cls.step_record = new_val

    @classmethod
    def update_chosen_chess(cls, new_val:bool) -> None:
        '''
            更新chosen_chess
            new_val：要更新的值
        '''

        cls.chosen_chess = new_val

    @classmethod
    def update_chosen_chess_index(cls, new_val:bool) -> None:
        '''
            更新chosen_chess_index
            new_val：要更新的值
        '''

        cls.chosen_chess_index = new_val

    @classmethod
    def update_is_black(cls, new_val:bool) -> None:
        '''
            更新is_black
            new_val：要更新的值
        '''

        cls.is_black = new_val

    @classmethod
    def update_black(cls) -> None:
        '''
            更新black
            new_val：要更新的值
        '''

        cls.black -= 1

    @classmethod
    def update_red(cls) -> None:
        '''
            更新red
            new_val：要更新的值
        '''

        cls.red -= 1

    @classmethod
    def update_step(cls) -> None:
        '''
            更新step
            new_val：要更新的值
        '''

        cls.step += 1
        print('now step:', cls.step)