# 三文鱼大模型 · salmon-desktop-control

**给 AI agent 用的 Windows 桌面操控技能。它看见的不是「一张屏幕截图」，而是任何一个窗口自己的画面。**

> 本文件是**给 AI 读的安装说明书**。人只要把整个文件夹丢进技能目录即可；
> 如果你是被用户要求「照着这份说明装好并跑通」，请严格按下面 §2 的步骤执行，并在最后执行 §4 的自检，把真实输出贴给用户看。

---

## 0. 这是什么 / 适合谁

主流桌面自动化只有两条路：抓整块屏幕、读 UIA 语义树。这两条在真实桌面上会同时失效——

- 目标被别的窗口盖住时，你抓到的是**别人的画面**；
- 目标是自绘 UI / 游戏 / GPU 渲染时，语义树里**什么都没有**。

本技能专为这两种失败而做：三种捕获形态（屏幕合成 / PrintWindow / Windows 图形捕获 WGC）、
像素级找图找色找字、把输入直接投给目标句柄（**不抢前台、不动鼠标**），
外加一条本地反射回路——模型只下发策略，逐帧判断与出手跑在本地进程里。

**一句话立场：语义树管「正常的软件」，三文鱼管「不正常的那一半」。**

> ⚠️ 只支持 **Windows** 真实桌面会话。需要图形界面；无头/纯服务端环境跑不了。

---

## 1. 环境要求（先自查）

| 项目 | 要求 | 说明 |
|---|---|---|
| 操作系统 | **Windows 10 / 11**（64 位） | 依赖 Win32 API 与 Windows Graphics Capture |
| Python | **3.10 ~ 3.13**（64 位） | 32 位 Python 不行，`windows-capture` 需要 64 位 |
| 网络 | 首次装依赖需要 | 之后完全离线可用，**不联网、不上传任何数据** |
| 权限 | 普通用户即可 | 但**目标程序以管理员运行时，你的进程也必须提权**，否则系统层面禁止操作它（UIPI） |
| 磁盘 | 约 300 MB | 其中依赖约占 250 MB（opencv + onnxruntime + 模型） |

---

## 2. 安装（照抄即可）

### 2.1 把技能目录放到客户端的技能位置

解压后应得到这样的结构（**`salmon-desktop-control/` 这一层必须完整保留**）：

```
salmon-desktop-control/
├── SKILL.md              ← 全部说明书（AI 读这个）
├── requirements.txt
├── README.md             ← 本文件
├── docs/                 ← 实战附录，按场景拆分，命中才读
│   ├── README.md
│   ├── 场景-banner操作横幅/
│   ├── 场景-安装器与提权窗口/
│   ├── 场景-微信开发者工具与小程序/
│   ├── 场景-桌面客户端与文件对话框/
│   ├── 场景-沙箱里启动GUI/
│   ├── 场景-网页表单与输入法/
│   ├── 场景-色彩取值与通道顺序/
│   └── 场景-长跑闭环与OCR校验/
└── scripts/
    ├── svc.py            ← 常驻服务（127.0.0.1:8765）
    ├── mc.py             ← 唯一命令行入口，40+ 个 op
    ├── uia_sem.py        ← v1.6.0 语义读取通道（UIA）
    ├── ocr_worker.py     ← OCR 独立进程
    ├── wgc_worker.py     ← WGC 抓帧独立进程
    ├── banner.py         ← 屏幕顶部操作横幅
    └── common.py
```

把**整个 `salmon-desktop-control/` 文件夹**放进你的 agent 客户端的技能目录。常见位置：

- DeepSeek Harness：`~/.dsh/skills/salmon-desktop-control/`
- WorkBuddy：`~/.workbuddy/skills/salmon-desktop-control/`
- Qoder：`~/.qoder-cn/skills/salmon-desktop-control/`
- Codex / 其他支持 skills 的客户端：`~/.<客户端>/skills/salmon-desktop-control/`

> **不要只拷贝 `scripts/` 或只拷贝 `SKILL.md`。** 缺 `docs/` 会导致 SKILL.md 里 8 处场景索引指向空文件；缺 `scripts/` 则任何命令都跑不了。

### 2.2 装 Python 依赖

```bash
cd salmon-desktop-control
pip install -r requirements.txt
```

依赖清单（7 个）：

```
pyautogui>=0.9.54
mss>=9.0.1
opencv-python-headless>=4.8
numpy>=1.24
Pillow>=10.0
rapidocr-onnxruntime>=1.3
windows-capture>=2.0.1
```

**两个常见坑：**

1. **`windows-capture` 装不上** → 检查是不是 32 位 Python（`python -c "import struct;print(struct.calcsize('P')*8)"` 必须输出 `64`）。
2. **国内网络慢** → 换镜像：`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`
3. 如果只想用前两种捕获形态（不需要 WGC），可以不装 `windows-capture`；
   `--form wgc` 会自动回退到 `pw`，**不会报错**，只是拿不到满分辨率/被遮挡的图。

### 2.3 启动常驻服务

```bash
python scripts/svc.py start
```

首次启动会加载 OCR 模型，**约 10 秒**；之后常驻内存，每次命令都是毫秒级。
服务只监听 `127.0.0.1:8765`，不对外网开放。

---

## 3. 三十秒上手

```bash
python scripts/mc.py ping                                   # 健康检查 → {"ok":true,"pong":true,...}
python scripts/mc.py shot --out shot.png                    # 整屏截图
python scripts/mc.py shot-wgc --hwnd <窗口句柄> --out w.png  # 被遮挡也拿到该窗口满分辨率原图
python scripts/mc.py locate-text --text 确定                 # 按文字定位，返回坐标
python scripts/mc.py click --x 500 --y 400                  # 点击
python scripts/mc.py uia-list --hwnd <句柄>                  # 读控件清单（不截图）
python scripts/mc.py uia-click --hwnd <句柄> --name 保存     # 按名字点按钮（不动鼠标）
python scripts/mc.py find-icon --region 950,60,147,80       # 无模板找图标候选（v1.6.1）
python scripts/mc.py icon-click --region 950,60,147,80 --verify   # 找+点+自动验证（v1.6.1）
python scripts/mc.py banner --title "AI 正在操控屏幕"        # 顶部操作横幅
```

完整 40+ 个 op 见 `SKILL.md`（**它是唯一完整手册，没有别的文档**）。

---

## 4. 装完请跑这个自检（把输出贴给用户）

```bash
python scripts/svc.py start
python scripts/mc.py ping
python scripts/mc.py shot --out verify.png
```

**三项全过 = 装好了**：

| 命令 | 期望输出 | 失败怎么办 |
|---|---|---|
| `svc.py start` | 无报错，进程常驻 | 看报错缺哪个包 → 回到 §2.2 |
| `mc.py ping` | `{"ok": true, "pong": true, ...}` | 服务没起来：`svc.py start` 的前 20 行日志 |
| `mc.py shot --out verify.png` | 生成一个 **大于 100 KB** 的 PNG | 空/黑图 → 确认不是远程桌面最小化、不是锁屏 |

收尾：

```bash
python scripts/mc.py shutdown      # 关掉常驻服务
```

---

## 5. 版本与新增能力

| 版本 | 新增 |
|---|---|
| **v1.6.1** | **图标记通道**：`find-icon`（无模板按几何+对比度找图标）、`icon-click`（找+点一步，含 `--dry-run` / `--verify`）、`diff`（截图差异量化，回答「这一点到底生效没有」）。解决「看得见、点不到」的纯图形按钮 |
| v1.6.0 | **语义读取通道（UIA）**：`uia-list` / `uia-click` / `uia-read`。不截图不 OCR，直接读控件登记表；按名字点按钮，Invoke 模式不动鼠标不抢前台、被遮挡也能点 |
| v1.5.0 | **WGC 捕获**：被遮挡 / DPI 缩放的窗口都能满分辨率实时取帧；游戏级操控（`move-rel` / `mouse-hold`）；`guard` 本地反射回路 |
| v1.3.6 | 首个公开版 |

---

## 6. 隐私与安全

- **完全本地运行**：不联网、不调用任何在线 API、不上传截图或文字。OCR 用的是随包安装的本地模型（rapidocr / onnxruntime）。
- **只监听回环地址** `127.0.0.1:8765`，局域网其它设备访问不到。
- 常驻服务在你执行 `shutdown` 或注销前会一直在后台；不需要时请关掉。
- 本技能**能控制你的鼠标键盘**。在它运行期间不要让它无人值守地操作敏感程序（网银、密码管理器等）。

---

## 7. 排错

| 现象 | 原因 / 处理 |
|---|---|
| `svc.py start` 报 `No module named xxx` | 依赖没装全 → `pip install -r requirements.txt` |
| `mc.py` 报连接失败 / `Connection refused` | 常驻服务没起 → 先 `python scripts/svc.py start` |
| 截图是黑的 / 只有桌面壁纸 | 目标是 DPI 缩放或 GPU 渲染 → 改用 `shot-wgc`；或先 `win-activate` 把窗口切前台 |
| 点不动某个按钮 | 目标以管理员权限运行 → 你的 Python 也要以管理员启动（UIPI 边界） |
| 按钮明明是图形却点不到 | 用 v1.6.1 的 `find-icon` / `icon-click --verify` |
| OCR 认不出字 | `locate-text` 对字体/背景敏感，先 `shot` 看一眼实际渲染效果 |
| 中文用户名下截图失败 | v1.5.0 已修（cv2.imwrite 在非 ASCII 路径的问题）；若仍失败，设环境变量 `SALMON_TMP` 指向纯英文目录 |

更细的实战复盘在 `docs/` 里，按场景拆分（banner、安装器与提权、微信开发者工具、文件对话框、
沙箱启动 GUI、网页表单与输入法、色彩通道、长跑闭环）。**撞到墙了再去翻，没撞到不用读。**

---

## 8. 目录约定

`SKILL.md` 是唯一完整手册。它内部引用附录时用的是**相对路径** `docs/xxx`，
相对于 `SKILL.md` 所在目录解析——所以整个文件夹必须保持现在的结构，不要拆开。

---

## 9. 许可

见 `LICENSE`（若包内未附带，则本技能按原仓库授权方式使用）。
