<!-- 三文鱼大模型附录：仅在下面这类场景才需要读 -->
**适用场景**：取色对不上、PNG 存出来 R/B 反了、模板匹配分数长期偏低

**来源**：SKILL.md 原文逐字搬出，内容未删改

---

## 🔧 v1.22.2 修 R/B 通道互换（2026-09-15，第 9 轮）

**症状**：同一块屏幕，`mc.py color` 报的颜色和肉眼/PIL 抓的**对不上**。实测（微信开发者工具模拟器）：
- `.rent-bar` 样式表里明确写 `#2b7cff`（蓝），`mc.py color` 却报 `#FF802F`（橙）；
- 白底附近报 `#FFDB8C`（黄）；`#f4f7fc` 报成 `#FCF7F4`。
- 用 PIL `ImageGrab` 独立抓同一像素：`#2F80FF` / `#F4F7FC` —— **与样式表完全吻合**。
- 规律：`(R,G,B) → (B,G,R)`，**正好是 R 与 B 互换，G 不动**。

**根因（一行写错）**：`_grab()`（svc.py）从 mss 拿到的 `np.array(shot)` 是 **BGRA**，
`[:, :, :3]` 已得 **BGR**（cv2 原生顺序，全项目下游都按 BGR 预期），
但代码又多加了一步 `[:, :, ::-1]` 把它反成了 **RGB**。于是：
- `op_color` 把通道 0 当 B 读 → 报出的 R/B 是反的（症状①）；
- `op_shot` 保存时再 `img[:, :, ::-1]`（BGR→RGB）→ 二次反相 → 存出来的 PNG R/B 互换（症状②）；
- `find` 用 `cv2.matchTemplate(screen_RGB, tpl_from_imread_BGR)` → **色彩通道错位，匹配分数长期偏低**，属长期静默劣化。
- `screen.py` 的 `_grab_region` 是同一个错（docstring 写着 BGR，代码给 RGB）。

**修法**：两处都删掉多余的 `[:, :, ::-1]`，让 `grab` 老实返回 **BGR**，全链自洽：
```python
# svc.py::_grab / screen.py::_grab_region
return np.array(shot)[:, :, :3].copy(), left, top      # BGRA -> BGR（不要 ::-1）
```
备份：`scripts/svc.py.bak_before_bgr_fix_20260915`、`scripts/screen.py.bak_before_bgr_fix_20260915`。（这两份 .bak 后来在技能迁移时被排除、现已不在盘上，此处仅作历史记录；`screen.py` 本身也已于 v1.3.5 退役，见「已退役」节。）
改完 `svc.py stop` 后下一条 `mc.py` 会自动拉起新进程。

**验证手法（推荐固化为"取色自检"）**：改完立即拿一个**样式已知**的像素对拍——用
`mc.py color` 与 PIL `ImageGrab.grab().getpixel(...)` 各取一次，两者一致才算过：
```bash
"$PY" "$MC" color --x 2200 --y 620          # 期望 #2F80FF
"$PY" -u -c "from PIL import ImageGrab; print(ImageGrab.grab().getpixel((2200,620)))"
```
PIL 那条是**独立通道**（不经 svc/mss 封装），拿它当"真值"最靠谱。

**教训**：**光看截图判色会翻车**。凡是"颜色对不对"的判断（主题色、涨跌红绿、状态灯），
一律先用 `mc.py color` + PIL 对拍确认通道顺序，再下结论；别拿一张可能反相的 PNG 当依据。

