# 三文鱼大模型 —— 附录归档（退役脚本与考古资料）

> **这个目录不是技能的一部分，正常使用时不需要读、也不需要跑。**
> 只有在**改 bug、追历史行为、要拿老脚本对答案**的时候才来这里读。
> 平时干活只读技能目录里的 `SKILL.md` 就够了。

- 技能本体：`C:\Users\Administrator\.qoder-cn\skills\salmon-desktop-control\SKILL.md`
- 本目录建立于：2026-10-02（三文鱼大模型 v1.3.5 那轮改造）
- 搬出来的原因：`screen.py` / `mouse.py` 是常驻服务 `svc.py` 出现之前的"一次性命令"老骨架，
  功能已被 `svc.py` + `mc.py` 完全覆盖且慢一个数量级（每条命令要重启 Python、重加载
  numpy/cv2/OCR，2~5 秒；走 svc 后单条通常 <100ms）。留着只会让"该用哪个入口"变含糊，
  所以从技能目录撤掉，源码原样归档在这里。

---

## 一、归档清单

| 文件 | 作用 | 字节 |
|---|---|---|
| `screen.py` | 老版"眼睛"：截图 / 找图 / 识字 / 取色 / 显示器列表，一次性 CLI | 11,953 |
| `mouse.py` | 老版"手"：移动 / 点击 / 拖拽 / 滚轮 / 打字 / 快捷键（pyautogui 包装） | 7,313 |
| `common.py` | 两个脚本共同依赖：设 Per-Monitor DPI 感知、解析 region、统一 JSON 输出 | 2,293 |

`common.py` 必须和本目录里另两个文件放在同一层，否则 `import common` 失败——
这三个文件是一个整体，别单独拷走其中一个。

跑法（在本目录下）：

```bat
cd /d <解压后的 salmon-desktop-control\docs 目录>
python screen.py monitors
python mouse.py pos
```

实测归档副本可用（2026-10-02 在本机验证过）：
`screen.py monitors` 返回双 1920×1080、scale 1.75；`mouse.py pos` 返回 `{x:960,y:540}`。

---

## 二、screen.py 支持的命令（照抄源码 docstring）

```
monitors                       列出所有显示器（物理像素，可含负坐标）
shot    [--out path] [--region x,y,w,h] [--monitor N]
                               截屏保存 PNG，返回绝对路径/尺寸
color   --x N --y N            取指定坐标颜色（hex/rgb）
find    --template t.png [--confidence 0.8] [--region ...] [--monitor N]
                               [--scales 0.9,1.0,1.1] [--max 5] [--all]
                               模板匹配找图，返回目标中心坐标（物理像素）
ocr     [--region ...] [--monitor N]   屏幕文字识别（含坐标框）
locate-text --text "xx" [--region ...] [--all] [--exact]
                               OCR 后按文字定位坐标（默认模糊含匹配，忽略空格）
```

结果以**单行 JSON**输出，坐标全是物理像素，可直接喂给 `mouse.py`。

## 三、mouse.py 支持的命令（照抄源码 docstring）

```
pos                              查询当前鼠标坐标
move    --x N --y N [--duration S]   移动鼠标（可加 --rel 做相对移动 dx,dy）
click   [--x N --y N] [--button left|right|middle] [--count N] [--interval S]
drag    --x1 N --y1 N --x2 N --y2 N [--duration S] [--button left]
scroll  --amount N [--x N --y N]    N>0 向上滚，N<0 向下滚
type    --text "内容"               键盘输入（中文/Unicode 走剪贴板方案）
key     --key enter                 按单个键
hotkey  --keys "ctrl,shift,s"       组合键（逗号分隔）
```

`mouse.py` 读环境变量 `A_MOUSE_FAILSAFE=1` 才会打开 pyautogui 的"鼠标甩到左上角急停"，
默认关闭（自动化跑一半被急停更糟）。

---

## 四、老命令 → 现在的等价命令

| 老（本目录） | 现在（技能 `mc.py`，走常驻 svc） |
|---|---|
| `screen.py shot` | `mc.py shot` |
| `screen.py find` | `mc.py find` |
| `screen.py ocr` / `locate-text` | `mc.py ocr` / `mc.py locate-text`（还多了 `--form`/`--hwnd`） |
| `screen.py color` | `mc.py color` |
| `screen.py monitors` | `mc.py monitors` |
| `mouse.py move/click/drag/scroll/key/hotkey/type` | `mc.py` 同名 op，且多了 `key-down`/`key-up`/`key-hold`/`mouse-down`/`mouse-up`/`--via post` |
| —（老脚本没有） | `mc.py shot-pw` / `shot-wgc` / `find-color` / `guard` / `probe` / `win-front` / `batch` |

**结论：这里没有 `svc.py` 覆盖不到的能力。** 唯一"只有这里才有"的东西，是各函数在
一次性进程模式下的独立实现，改 bug 时可以用它对拍，判断某个行为是通路问题还是 svc 本身的问题。

---

## 五、别在这里改代码

改逻辑一律改技能目录里的 `svc.py` / `mc.py` / `uia_sem.py`，并且**四份副本要同步并对 md5**
（历史上这个技能曾被复制到多处导致行为漂移；2026-10-05 重装系统后用户目录已从
Administrator 迁到 月绪，旧文档里的 `C:\Users\Administrator\...` 路径全部作废）：

- `C:\Users\月绪\.workbuddy\skills\salmon-desktop-control\`（WorkBuddy，常作主本）
- `C:\Users\月绪\.qoder-cn\skills\salmon-desktop-control\`（Qoder/千问）
- `C:\Users\月绪\.zcode\skills\salmon-desktop-control\`（ZCode）
- `C:\Users\月绪\.dsh\skills\salmon-desktop-control\`（DeepSeek Harness，v1.6.0 起纳入同步清单）

本目录只是存档，改了也不会被任何入口调用。

---

## 六、版本存档索引

- **v1.6.0（2026-10-12，第 18 轮）语义读取通道**：UIA 无障碍树上线——不截图读控件清单
  （`uia-list`）、按名字点按钮（`uia-click`，Invoke 模式不动鼠标不抢前台、被遮挡也能点）、
  读控件值（`uia-read`，Value→Text Pattern 兜底）。实测：记事本 31 元素 37ms 全量读出、
  Invoke 点菜单 140ms 一发命中。双通道策略：先 uia-list 试读，count<3 回退看图。
  四个 Agent 副本同步 + md5 对齐。逻辑、用法、踩坑详见 SKILL.md §16；
  演示雏形 `E:\zcode\uia_demo.py`。台账第 3 条（OCR 漏字）自此有正解（对上报清单的软件）。
