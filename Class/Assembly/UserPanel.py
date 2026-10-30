import pygame
from pygame import Color, Surface, Rect

from Class import Theme
from Class.Element.ControlPanel import ControlPanel
from Class.Element.TextBox import TextBox


class UserPanel:
    def __init__(self, up:int, down:int, left:int, right:int):
        '''
            初始化UserPanel界面
            up：上边界纵坐标
            down：下边界纵坐标
            left：左边界横坐标
            right：右边界横坐标
        '''

        # 连接属性
        self.up = up
        self.down = down
        self.left = left
        self.right = right

        self.width = right - left  # UserPanel界面宽度（300）
        self.height = down - up  # UserPanel界面高度（700）
        self.rect = Rect(left, up, self.width, self.height)  # 所在矩形区域

        control_width = self.width  # 控制面板宽度（300）
        control_height = self.height // 2 - 50  # 控制面板高度（300）
        state_top = up + control_height + 10
        state_middle = state_top + 36
        state_bottom = down - control_height - 10

        self.control_up = ControlPanel( up + 10, up + control_height + 10, left, right, "黑方", "人类")  # 上控制面板
        self.stateinfo = TextBox(state_top + 8, state_middle, left + 14, left + 86, '状态', Theme.FONT_BOLD, 16, Theme.TEXT_SECONDARY, Theme.SURFACE, False)
        self.state = TextBox(state_top + 8, state_middle, left + 86, right - 14, '等待开始', Theme.FONT_REGULAR, 16, Theme.PRIMARY, Theme.SURFACE, False)
        self.ai_diagnostics = TextBox(state_middle, state_bottom - 6, left + 14, right - 14, '人工智能：等待中', Theme.FONT_REGULAR, 13, Theme.TEXT_TERTIARY, Theme.SURFACE, False)
        self.control_down = ControlPanel(down - control_height - 10, down - 10, right - control_width, right, "红方", "人类")  # 下控制面板

    def draw(self, screen:Surface):
        '''
            绘制UserPanel界面
            screen：窗口
        '''

        pygame.draw.rect(screen, Theme.APP_BG, self.rect)
        self.control_up.draw(screen)
        self.control_down.draw(screen)
        status_card = Rect(self.left + 6, self.stateinfo.up - 6, self.width - 12, self.ai_diagnostics.down - self.stateinfo.up + 12)
        pygame.draw.rect(screen, Theme.SURFACE, status_card, border_radius=Theme.CORNER_RADIUS)
        pygame.draw.rect(screen, Theme.SEPARATOR, status_card, 1, border_radius=Theme.CORNER_RADIUS)
        self.stateinfo.draw(screen)
        self.state.draw(screen)
        self.ai_diagnostics.draw(screen)


    def runTimer(self, screen: Surface, is_up: bool):
        '''
            运行计时器
            screen：窗口
            is_up：是否是上方计时器
        '''

        if is_up:
            self.control_up.timer.run(screen)
        else:
            self.control_down.timer.run(screen)

    def stopTimer(self, is_up: bool):
        '''
            暂停计时器
            is_up：是否是上方计时器
        '''

        if is_up:
            self.control_up.timer.stop()
        else:
            self.control_down.timer.stop()

    # 开始运行计时器
    def startTimer(self, screen:Surface, is_up:bool):
        '''
            开始运行计时器
            screen：窗口
            is_up：是否是上方计时器
        '''

        if is_up:
            self.control_up.timer.start(screen)
        else:
            self.control_down.timer.start(screen)

    # 重置计时器
    def resetTimer(self, screen: Surface, is_up: bool):
        '''
            重置计时器
            screen：窗口
            is_up：是否是上方计时器
        '''

        if is_up:
            self.control_up.timer.reset(screen)
        else:
            self.control_down.timer.reset(screen)

    def getTimer_miliseconds(self, is_up: bool):
        '''
            获取计时器时间
            is_up：是否是上方计时器
        '''

        if is_up:
            return self.control_up.timer.miliseconds
        else:
            return self.control_down.timer.miliseconds

    def mouseOver_Leave(self, screen: Surface, pos: tuple):
        '''
            鼠标悬浮及离开
            screen：窗口
            pos：鼠标位置
        '''

        self.control_up.mouseOver_Leave(screen, pos)
        self.control_down.mouseOver_Leave(screen, pos)

    def mouseClick(self, pos:tuple):
        '''
            鼠标点击
            pos：鼠标点击时的位置
        '''

        # 遍历按钮列表，返回被点击按钮索引（下控制面板索引+4）
        for i in range(len(self.control_up.buttons)):
            if self.control_up.buttons[i].is_abled and self.control_up.buttons[i].is_inside(pos):
                return i
        for i in range(len(self.control_down.buttons)):
            if self.control_down.buttons[i].is_abled and self.control_down.buttons[i].is_inside(pos):
                return i + 4

    def updateName(self, screen:Surface, new_name:str, is_up:bool):
        '''
            更新姓名
            screen：窗口
            new_name：要更新的新名字
            is_up：是否是上方控制面板
        '''

        new_name = "玩家：" + new_name
        if is_up:
            self.control_up.name = new_name
            self.control_up.text_name.updateContent(screen, new_name)
        else:
            self.control_down.name = new_name
            self.control_down.text_name.updateContent(screen, new_name)

    def activate(self, screen:Surface, is_up:bool):
        '''
            激活控制面板
            screen：窗口
            is_up：是否是上方控制面板
        '''

        if is_up:
            self.control_down.deactivate(screen)
            self.control_up.activate(screen)
        else:
            self.control_up.deactivate(screen)
            self.control_down.activate(screen)

    def updateState(self, screen:Surface, new_state:str):
        '''
            更新状态
            screen：窗口
            new_state：要更新的新状态
        '''

        self.state.updateContent(screen, new_state)

    @staticmethod
    def format_ai_diagnostics(ai) -> str:
        if ai is None:
            return "人工智能：等待中"
        data = ai.diagnostics()
        content = (
            f"AI 深度{data['depth']} | {data['elapsed_ms']:.0f}毫秒 | "
            f"{data['nodes']:,}节点"
        )
        remaining = data.get("remaining_ms")
        if remaining is not None:
            seconds = max(0, int(remaining // 1000))
            content += f" | 剩余 {seconds // 60:02d}:{seconds % 60:02d}"
        if data.get("time_forfeit"):
            content += " | 超时判负"
        if data.get("fallback"):
            return f"{content} | 已启用兜底"
        return content

    def updateAIDiagnostics(self, screen: Surface, ai) -> None:
        self.ai_diagnostics.updateContent(screen, self.format_ai_diagnostics(ai))

    def gameOver(self, screen: Surface):
        '''
            游戏结束相关变化
            screen：窗口
        '''

        self.control_up.gameOver(screen)
        self.control_down.gameOver(screen)
