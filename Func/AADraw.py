import math

# 导入pygame库
import pygame
from pygame import Color, Surface

def drawAAArcs(screen:Surface, x:int, y:int, radius:int, color:Color, start_angle:int, end_angle:int, num_points:int = 100, width:int = 1):
    '''
        绘制抗锯齿的圆弧
        x，y：圆心横、纵坐标
        radius：半径
        color：圆弧颜色
        start_angle，end_angle：始末角度（角度制）
        num_points：点的数量（可以根据需要调整点的数量，增加点的数量以模拟更平滑的曲线）
        width：弧线宽度
    '''
    # 圆心位置
    center = [x, y]

    # 圆弧的起始和结束角度（弧度制）
    start_angle = math.radians(start_angle)
    end_angle = math.radians(end_angle)

    # 求解离散点和绘制圆弧
    for i in range(width):
        #求解离散点
        points = []
        for j in range(num_points + 1):  # +1 是为了确保包含起始点和结束点
            angle = start_angle + (end_angle - start_angle) * j / num_points
            x = center[0] + (radius + i) * math.cos(angle)
            y = center[1] - (radius + i) * math.sin(angle)
            points.append((x, y))

        # 绘制圆弧
        pygame.draw.aalines(screen, color, False, points, 1)

def drawAACircle(screen:Surface, x:int, y:int, radius:int, color:Color):
    '''
        绘制抗锯齿的填充圆
        x，y：圆心横、纵坐标
        radius：半径
        color：圆颜色
    '''

    for i in range(radius + 1):  # +1 是为了确保包含起始点和结束点
        drawAAArcs(screen, x, y, i, color, 0, 360)