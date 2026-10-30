# 圆域类
class CircleArea:
    def __init__(self, pos:tuple, radius: int):
        '''
            初始化圆域
            x,y：圆心横、纵坐标
            radius：圆域半径
        '''

        # 连接属性
        self.pos = pos
        self.radius = radius

        self.x = pos[0]  # 圆心横坐标
        self.y = pos[1]  # 圆心纵坐标

    def collidepoint(self, pos:tuple) -> bool:
        '''
            判断点是否在圆域内
            pos：点的坐标
        '''

        x = pos[0]
        y = pos[1]
        return (x - self.x) ** 2 + (y - self.y) ** 2 <= self.radius ** 2
