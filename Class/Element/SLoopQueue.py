from math import inf

# 循环队列类（顺序队列）
class SLoopQueue:
    def __init__(self, maxsize:int = inf):
        '''
            初始化循环队列
            maxsize：队列最大容量，默认为inf无穷大，即顺序队列
        '''

        # 链接属性
        self.maxsize = maxsize

        self.elements = [None for i in range(maxsize)]  # 队列本体
        self.front = self.rear = 0  # 队首、队尾
        self.is_full = False

    def length(self):
        '''
            求当前队列长度
        '''

        return (self.rear - self.front + self.maxsize) % self.maxsize

    def isEmpty(self):
        '''
            判断队列是否为空
        '''

        return self.front == self.rear == 0 and not self.is_full

    def isFull(self):
        '''
            判断队列是否已满
        '''

        return self.is_full

    def enQueue(self, element):
        '''
            入队
            element：入队元素
        '''

        if self.isFull():
            print('队列已满')
        else:
            self.elements[self.rear] = element
            if self.rear == self.maxsize - 1:
                self.is_full = True
            self.rear = (self.rear + 1) % self.maxsize

    def deQueue(self):
        '''
            出队
        '''

        if self.isEmpty():
            print("队列为空")
        else:
            element = self.elements[self.front]
            self.front = (self.front + 1) % self.maxsize
            self.is_full = False
            return element

    def head(self):
        '''
            取队首元素
        '''

        return self.elements[self.front]

    def isBothInQueue(self, e1, e2):
        '''
            判断两个元素是否都在队列中
            e1，e2：两个待判断元素
        '''

        return e1 in self.elements and e2 in self.elements

    def traverseBackwards(self, start_index:int):
        '''
            从给定索引处开始向后遍历，返回以该索引元素为首元素的列表
            start_index：开始索引
        '''

        ans = []
        index = start_index
        while len(ans) < self.maxsize:
            ans.append(self.elements[index])
            index = (index + 1) % self.maxsize
        return ans

    def traverseForwards(self, start_index:int):
        '''
            从给定索引处开始向前遍历，返回以该索引元素为首元素的列表
            start_index：开始索引
        '''

        ans = []
        index = start_index
        while len(ans) < self.maxsize:
            ans.append(self.elements[index])
            index = (index - 1) % self.maxsize
        return ans