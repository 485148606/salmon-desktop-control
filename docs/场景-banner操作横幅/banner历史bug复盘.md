<!-- 三文鱼大模型附录：仅在下面这类场景才需要读 -->
**适用场景**：banner 为什么不显示 / alpha 与 visible 的历史 bug 复盘

**来源**：SKILL.md 原文逐字搬出，内容未删改

---

## 🔧 v1.2.3 banner 修复（2026-09-09 小云雀实战，两处真 bug）

**症状**：主代理每次调 `mc.py banner --subtitle` 都返回 `"visible": false`，屏幕上从没出现过横幅，用户看了一整轮才发现。

**根因 ×2（都在 banner.py）**：
1. **`/set` 不传 visible 时保留旧状态**，而 `mc.py banner` 从不传 visible → 只要上一次任务收尾调过 `banner-hide`，之后所有 banner 调用永远隐藏。修复：`/set` 缺省 `visible=True`（本就是文件头注释承诺的"更新并显示"语义）。
2. **v1.2.2 把整窗 alpha 压到 25/255（≈10%）**，肉眼几乎不可见，mss 截图里完全看不出 → 用户视角等于没有横幅。修复：alpha 提到 200（≈78%）。横幅仅占顶部 ~61px，OCR/shot 按约定避开顶部即可。
3. 验证手法（复用）：`EnumWindows` 找 `SalmonBannerWnd` 类窗口查 `IsWindowVisible`+`GetWindowRect`；再 `shot --region 0,0,屏宽,200` 眼见为实。
4. 改 banner.py 后必须 `banner.py stop` → 重新 `mc.py banner`（自动拉起新进程）才生效。
- 备份：`banner.py.bak_20260909`。
- 🚨 **收尾硬纪律（用户 2026-09-09 亲自指出）**：任何自动化结束、交付、报错退出前，**最后一条命令必须是 `mc.py banner-hide`**，并用 `EnumWindows` 查 `SalmonBannerWnd` 的 `IsWindowVisible` 确认 false。忘了关 = 横幅一直挂在用户屏幕上 = 翻车。



**为什么改**：第 1~4 轮做 GUI 自动化时，遇到"目标窗口被 WorkBuddy（或其他杂窗）盖住"，主代理直接把 WorkBuddy `win-hide`（SW_HIDE 整个藏掉）。后果：

1. 用户眼前"一片黑 / 只剩被控软件"，不知道 AI 在干嘛，不敢碰键盘鼠标（怕干扰）
2. AI 进展只能靠 WorkBuddy 会话，但 WorkBuddy 被藏了，用户看不到进度
3. 想接管时 WorkBuddy 不在屏幕上，去任务栏翻也费劲
4. **人机协作完全断裂** = 失败

**怎么改**：不藏 WorkBuddy（改为最小化到任务栏、用户随时点开），改在屏幕顶部挂一条**半透明、置顶、鼠标点击穿透**的横幅——
- 第一行（黄字加粗警示）：「三文鱼大模型正在操控屏幕，请勿触碰」
- 第二行（白字）：**当前正在进行的环节（与 WorkBuddy 会话文字实时同步）**

主代理在每个环节切换时调一次 `mc.py banner --subtitle "..."`，用户看着横幅就知道 AI 走到哪一步、该不该接管、能不能碰鼠标。

**架构**：
- `banner.py` —— 独立常驻进程（自带 HTTP `127.0.0.1:8767`，**不依赖 svc**，沙箱回收 svc 时横幅依旧在）。纯 Win32 自绘（WS_POPUP+WS_EX_TOPMOST|WS_EX_LAYERED|WS_EX_TRANSPARENT|WS_EX_NOACTIVATE + WM_PAINT DrawTextW 双行 + WM_NCHITTEST→HTTRANSPARENT 鼠标穿透）。零第三方 GUI 依赖。
- `mc.py banner` / `banner-hide` —— 直连 8767 自动拉起 banner 进程，更新 / 隐藏。

**重要约束**：
- 横幅高度 ~ 屏幕 5%（约 110 物理 px），会遮挡目标应用顶部 100px 左右。**OCR/shot 区域避开顶部 ~120px**，或临时 `mc.py banner-hide` 再截，或用 `mc.py shot-pw --hwnd <目标>` PrintWindow 抓窗口真实内容。
- 横幅窗口被 mss 抓屏可见（不挡鼠标，但挡像素）—— 与 shot-pw 互补用即可。
- `banner --subtitle` 建议 < 60 字；过长会用 DT_END_ELLIPSIS 自动截断。

```bash
# 开始自动化任务时
"$PY" "$MC" banner --subtitle "启动：检查目标窗口"  # 第一行警示已默认

# 切换环节时实时更新（主代理每推进一步都调一次）
"$PY" "$MC" banner --subtitle "正在打开微信 / 第 1 步"
"$PY" "$MC" banner --subtitle "正在搜索联系人 / 第 2 步"
"$PY" "$MC" banner --subtitle "正在键入消息 / 第 3 步"

# 收尾（用户接管 / 任务完成 / AI 出错前 必调）
"$PY" "$MC" banner-hide
```

详细故障复盘原先写在项目文档 `微信开发者程序的桌面鼠标控制操作流程.md`（第 5 轮章节）——
**该文档现已不在盘上**。要查第 5 轮 banner 的来龙去脉，看上面「v1.2.3 banner 修复」一节 + 文末 §13 缺陷台账。

