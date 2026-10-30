def from_Coordinate_to_Subscript(chess_coordinate: tuple):
    '''
        转换坐标为下标函数
        :param chess_coordinate:
        :return:
    '''

    i, j = (chess_coordinate[1] - 200) // 60 + 2, (chess_coordinate[0] - 200) // 60 + 2
    return i, j