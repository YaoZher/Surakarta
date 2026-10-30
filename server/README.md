# 联网房间服务

此服务只运行房间和规则，无需 Pygame、显示器、字体或账号。局域网内置建房和独立在线服务复用 `networking/server.py`。

在仓库根目录使用 Python 3.10 或更新版本：

```console
python -m pip install -r server/requirements.txt
python -m server --host 0.0.0.0 --port 8765
```

客户端连接 `ws://服务器地址:8765`。防火墙需放行所选 TCP 端口。`PORT` 环境变量可设置默认端口，命令行参数优先。`--max-rooms`、`--max-connections` 分别默认为 128、256，`--reconnect-seconds` 默认为 60。

Docker 构建上下文必须是仓库根目录：

```console
docker build -f server/Dockerfile -t surakarta-server .
docker run --rm -p 8765:8765 surakarta-server
```

公网部署建议由反向代理提供 TLS，客户端使用 `wss://你的域名`。代理必须转发 WebSocket Upgrade 请求，空闲超时大于 60 秒。服务本身只监听 WebSocket，未集成证书管理、账户、匹配、持久化或多节点共享；请保持单个服务实例。重启服务会清空所有房间。房间号与重连令牌具有不同用途：房间号供第二位玩家加入，重连令牌只留在客户端内存中，不应公开。

创建者为黑方，加入者为红方。双方准备后开始；服务器检查回合、版本和规则。断线后暂停落子，60 秒内可凭令牌续接并同步完整状态；超时后在线对手获胜，双方均离线则结束为放弃。主动离开或认输结束当前房间，不支持房间内重赛。

房间规则：棋子全部被吃或轮到的一方无合法走法判负；含行棋方的完整局面出现三次、连续 80 个半回合无吃子判和。这些是此房间服务明确采用的规则，不代表赛事裁判规则。

资源限制：入站消息 4 KiB，每连接默认每 10 秒 40 条请求，未加入房间的连接 15 秒关闭；无实际状态变化 30 分钟的房间结束，结束后保留 5 分钟再清理。仅接受无 Origin 头的桌面客户端，浏览器来源默认拒绝。服务不记录令牌。公网流量限制和证书由部署环境管理。

在完整游戏仓库中检查真实 WebSocket 的房间交互（独立部署包不包含测试文件）：

```console
python -m unittest discover -s tests -p test_network_server.py -v
```
