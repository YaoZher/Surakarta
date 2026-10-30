# Surakarta · 苏拉卡尔塔棋

基于 Python 和 Pygame 的苏拉卡尔塔棋程序，支持人机对战、同机双人、游戏内置局域网房间，以及通过独立服务端进行在线 PvP。联网首版使用昵称和房间码，无需账号。

联网功能版本：`2026-10-26-network-preview`，包括双方准备、服务器走法校验、断线续接和棋谱导出。

当前版本：`2026-10-24-paper-S5-candidate`。这是**论文策略试验候选版**，版本状态为 `experimental_not_promoted`，尚未通过正式比赛预算的棋力确认。版本信息与核心引擎文件校验值见 [VERSION.json](VERSION.json)。

## 安装与启动

### 中文与阿拉伯语界面

本地扩展版新增中阿切换。点击右侧 `العربية` / `中文` 按钮，或按 **F2**；设置和联网面板打开时也可按 F2。语言偏好单独保存于 `output/language.json`，切换不重开棋局、不改变AI参数、计时、网络连接或棋谱数据。

阿语覆盖主菜单、双方控制面板、状态与计时、AI设置、联网建房/加入/房间面板和连接提示。文字使用字形连接与双向排版，设置及联网表单按RTL调整；棋盘坐标、房间码、IP/URL及导出的原始棋谱保持原顺序。阿语昵称按Unicode保存，文本字段可使用复制粘贴及系统输入法。

Windows 可双击 `run_game_ar.bat` 以阿语启动。也可设置环境变量 `SURAKARTA_LANGUAGE=ar` 或 `zh` 后运行 `main.py`；环境变量优先于保存的语言偏好。

新增依赖 `arabic-reshaper==3.0.1`、`python-bidi==0.6.12`，更新后先重新安装 `requirements.txt`。附带 [Noto Sans Arabic](https://github.com/google/fonts/tree/main/ofl/notosansarabic) 字体和其OFL许可。连接字形与双向算法的用法参考 [Arabic Reshaper](https://pypi.org/project/arabic-reshaper/) 和 [python-bidi](https://pypi.org/project/python-bidi/)。

翻译字典为 `Class/locales/ar.json`，入口为 `Class/I18n.py`；显示层翻译不修改服务器协议。此版新增9项界面回归用例，涵盖字体、切换、RTL控件、昵称及对局状态保存；母语术语润色与实际设备输入法验收可由Nasr继续进行。

需要 Python 3.10 或以上；依赖见 `requirements.txt`，包括Pygame、WebSocket和阿语排版库。推荐使用 Python 3.12；Windows 提供启动脚本，其他桌面系统可从项目根目录运行 Python 入口。旧版用户也需重新安装下面的依赖。

```sh
git clone https://github.com/YaoZher/Surakarta.git
cd Surakarta
python -m venv .venv
```

Windows PowerShell 安装依赖并启动：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B main.py
```

安装依赖后也可双击 `run_game.bat`。脚本优先使用项目内的 `.venv`；未创建虚拟环境时使用系统 `python`。

macOS / Linux：

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B main.py
```

请始终从项目根目录启动，以便程序找到 `Resource/` 中的字体文件。启动后，在右侧选择黑、红双方的人类或 AI 模式，按“开始”进入对局；黑方先手。AI 设置需在开局前调整。

## 对局与棋谱

- 棋盘为 6 × 6，双方各 12 枚棋子。普通走子移动至相邻空点；吃子沿环线行进，必须经过弧线且路径无阻挡。
- 界面提供合法走法提示、走子动画、棋谱显示和 AI 搜索信息。
- 开始对局后，每次有效落子都会更新 `棋谱/<对局ID>/` 下的 TXT、JSON 和 `逐步备份.jsonl`。
- 点击“导出棋谱”或按 `Ctrl+S`，生成一份独立的 TXT / JSON 导出；未终局时也可以导出。
- 重来和退出会尝试保存当前对局；保存失败会显示在状态区，请保留人工备份。

人工比赛前，在 [比赛信息.json](比赛信息.json) 填写组别、轮次、局次及黑红方队名。若比赛双方不使用同一联网服务，仍可采用共享屏幕与人工录入对手着法。完整操作流程见 [使用说明.txt](使用说明.txt)。

界面回合用时与 AI 内部搜索余额是不同的计时口径。默认 15 分钟为软件配置，裁判计时规则在版本信息中仍标为 `not_confirmed`；正式比赛限时和结果以双方及裁判确认为准。

## 局域网 PvP（内置）

1. 两台电脑安装相同版本并连接同一局域网。房主在主界面点击“联网对战 → 局域网建房”，输入昵称后创建。
2. 房间面板显示连接地址和房间码，支持复制。另一方点击“局域网加入”，填入房主的 IP、端口和房间码。
3. 双方各点击“准备”，对局开始。创建者执黑先行，加入者执红。关闭房间面板即可操作棋盘。
4. 房间面板中可以认输、手动重连或离开；对局中可用 `Ctrl+S` 导出棋谱。

房主电脑自动运行内置服务，无需另外安装或启动服务端。默认端口为 TCP 8765；系统防火墙询问时需允许当前可信局域网访问。显示的 IP 是自动探测结果，多网卡/VPN 环境请以实际局域网 IPv4 地址为准；来宾 Wi-Fi、AP 隔离或不同网段可能无法互通。此版本使用手动输入地址和房间码，不包含自动发现。

房主必须保持游戏运行。房主退出会关闭内置服务；对局结束后若要再赛，离开并创建新房间。

## 在线 PvP（独立服务端）

服务端可以独立运行，无需 Pygame 或字体。在仓库根目录执行：

```sh
python -m pip install -r server/requirements.txt
python -m server --host 0.0.0.0 --port 8765
```

双方在游戏的“联网对战 → 在线房间”填入同一服务地址（例如 `ws://服务器IP:8765` 或配置 TLS 后的 `wss://你的域名`），一方创建房间，另一方输入房间码加入。公网服务需自行部署并放行相应端口；代码仓库不提供已经上线的公共服务器。

部署、Docker 和连接限制见 [server/README.md](server/README.md)。需要独立源码包时执行 `python -m server.export`，会生成不含界面、字体及虚拟环境的 `output/Surakarta_Server.zip`；解压后可直接安装根目录依赖并启动。

### 首版房间规则与范围

- 服务端持有真实棋局；客户端仅提交起点、终点和局面版本，收到确认才更新棋盘。联网模式关闭本地 AI 切换、暂停和重来操作。
- 双方准备后开局。首版为不限时友谊局，界面计时只供参考。
- 对手断线后暂停落子，默认保留 60 秒重连机会。保持游戏进程，在房间面板点击“重连”可恢复；重启客户端会丢失仅存在内存中的续接凭证。
- 棋子耗尽或轮到的一方无合法走法判负；完整局面（含行棋方）三次重复、连续 80 手未吃子判和；认输、主动离开和断线超时由服务端结束对局。这是明确约定的房间规则，不作为赛事规则认证。
- 房间保存在服务端内存中，服务重启会清空。首版不包含账号、自动匹配、观战、房间内重赛、积分榜或多实例共享。

### 实现结构

`engine/` 是共享规则来源，`networking/server.py` 同时供内置局域网与独立服务器使用。`networking/client.py` 在后台处理网络收发，`Class/NetworkSession.py` 在界面主线程应用已确认的棋局，`NetworkPanel` 只负责输入和展示。两种联网模式共用同一个版本化协议，避免分别维护两套对战规则。

## AI 与参数

引擎使用迭代加深和 Alpha–Beta / Negamax 搜索，并包含置换表、走法排序、静态搜索及重复局面处理。`paper_2022` 估值方案与开局环线排序属于试验功能。

随仓库提供的 [output/ui_settings.json](output/ui_settings.json) 保存以下候选默认值，界面修改后会写回该文件：

| 参数 | 候选默认值 | 界面可选范围 |
| --- | --- | --- |
| 搜索深度 | 5 | 2–7 |
| 单步搜索预算上限 | 5000 ms | 250、500、1000、2000、5000、10000 ms |
| 每方 AI 总思考时长 | 15 分钟 | 关闭，或 1–120 分钟 |
| 估值方案 | `paper_2022` | `baseline`、`candidate_016`、`solid`、`paper_2022` |

启用总思考时长时，实际单步预算还受剩余时间分配约束，可能低于设置的单步上限。总思考时长只扣除 AI 搜索时间。

`run_game.bat` 显式设置深度、时间、估值和策略环境变量。桌面界面初始化时，会用 `output/ui_settings.json` 中的设置配置 AI，因此界面参数应在“设置”中调整；仅修改启动脚本里的深度、时间或估值不一定改变最终界面参数。删除设置文件后，当前代码回退到 `baseline` 估值。

开局排序由 `main.py` 默认启用，只在己方 AI 前三回合影响搜索顺序，不强制选择特定走法。若需关闭，在启动前设置环境变量；例如 PowerShell：

```powershell
$env:SURAKARTA_PAPER_OPENING_ORDERING = "0"
.\.venv\Scripts\python.exe -B main.py
```

此时直接运行 `main.py`；`run_game.bat` 会把该变量重新设为 `1`。切换界面估值方案不会自动关闭开局排序。

## 项目结构

```text
.
├── main.py                 # Pygame 程序入口
├── run_game.bat            # Windows 候选版启动配置
├── requirements.txt        # 界面与联网依赖版本
├── VERSION.json            # 候选版本、状态与引擎校验值
├── Class/                  # 对局管理、界面、AI 适配和棋谱保存
│   ├── Assembly/           # 棋盘、棋谱、菜单与用户面板
│   └── Element/            # AI 适配器和界面组件
├── engine/                 # 独立棋盘、规则、估值、搜索与计时
├── networking/             # 权威房间服务与非阻塞客户端
├── server/                 # 独立服务入口、Docker 和源码包导出
├── tests/                  # 真实双端房间、重连、界面与客户端测试
├── Func/                   # 绘图与坐标辅助函数
├── Resource/               # 界面字体资源
├── output/ui_settings.json # 随仓库提供的候选默认设置
├── 比赛信息.json            # 比赛信息填写模板
├── 使用说明.txt             # 比赛操作与候选策略说明
└── .github/                # 基础检查脚本及 GitHub Actions 配置
```

## 仓库检查

安装依赖后，从项目根目录执行：

```sh
python -B .github/scripts/smoke_check.py --with-ui
python -B -m unittest discover -s tests -v
```

基础检查覆盖 Python 语法、候选引擎校验值、规则与搜索的基本行为，以及无显示窗口的 Pygame 初始化。联网测试通过本机回环地址启动临时服务和两个客户端，检查同步、非法请求、重连、清理及棋谱；它们不向公网服务发起对战。GitHub Actions 在 Windows / Linux、Python 3.10 / 3.12 上运行同一套检查。这些检查不代表完整赛事规则认证、棋力评测或公网负载测试。

`.gitignore` 排除 Python 缓存、虚拟环境、构建产物和生成的棋谱；`output/ui_settings.json` 作为候选默认配置继续纳入版本控制。`比赛信息.json` 是已跟踪的模板，比赛后提交前请检查这两个文件的本地修改。`.gitattributes` 固定文本换行方式，并将字体标记为二进制文件。

## 论文策略来源

按项目原有说明，策略参考李东轩、胡伟、王静文《基于 Alpha-Beta 算法的苏拉卡尔塔棋博弈系统研究》，2022 年，第 12 卷第 2 期，123–125 页。

本项目将论文关键点位置表乘以 2，再与原位置表各占 50% 混合；开局阶段优先搜索疏通环线且没有立即吃子回复的安静走法。这些缩放、混合和排序方式是本项目试验设计，并非论文给出的最优参数。开发说明保留了团队与 Codex 辅助开发的信息。
