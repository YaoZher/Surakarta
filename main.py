import os
os.environ.setdefault("SURAKARTA_PAPER_OPENING_ORDERING", "1")

import pygame
from Class.GameManager import GameManage

def main():
    gm = GameManage()
    pygame.display.set_caption("苏拉卡尔塔棋 - 论文策略试验版")
    gm.run()

if __name__ == "__main__":
    main()
