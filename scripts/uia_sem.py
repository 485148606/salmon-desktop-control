# -*- coding: utf-8 -*-
"""
uia_sem.py — 三文鱼 v1.6.0 语义读取通道（UI Automation / 无障碍树）

一句话：Windows 要求每个软件把自己界面的按钮/文字/坐标登记进系统"控件清单"
（原本给盲人读屏软件用）。本模块去查这张清单，把"看图猜按钮"换成"按名字点按钮"。

三个 op（svc.py HANDLERS 里注册为 uia-list / uia-click / uia-read）：
  uia-list  --win <标题关键词> | --hwnd <句柄> [--max 80] [--depth 7]
              [--text <过滤>] [--region x,y,w,h]
              → 返回 [{type,name,x,y,w,h}]，全部是物理像素屏幕坐标
  uia-click --name <名字> [--win|--hwnd] [--index n] [--mode auto|invoke|click]
              → 优先 Invoke 模式（程序化触发，不动鼠标、被遮挡也能点、不抢前台）；
                控件不支持 Invoke 时回退物理点击（点前做 WindowFromPoint 遮挡校验）
  uia-read  --name <名字> [--win|--hwnd]
              → 读控件的值（ValuePattern），用于核对输入框/状态文字

实测基线（2026-10-12，本机）：记事本 29 元素 60ms 全量读出，零截图零 OCR。
已知边界（详见 SKILL.md §16）：
  - Electron/Chromium 应用默认不开无障碍树，读之前先发 WM_GETOBJECT(OBJID_CLIENT)
    敲门 + 重试两次；仍只有根节点 = 该应用没上报，走看图通道
  - 游戏/自绘 canvas 没有清单，永远看图
  - comtypes 的 IUIAutomationElementArray 取值方法叫 GetElement（不是 GetItem）
  - UIA 的 COM 调用必须每线程 CoInitialize（svc 是 ThreadingHTTPServer）
"""
import ctypes
import threading
import time
from ctypes import wintypes

_TL = threading.local()   # 每线程缓存 CUIAutomation（COM 单元模型要求）

WM_GETOBJECT = 0x003D
OBJID_CLIENT = 0xFFFFFFFC
PATTERN_INVOKE = 10000
PATTERN_VALUE = 10002
PATTERN_TEXT = 10014
TreeScope_Children = 2

TYPE_NAMES = {
    50000: "按钮", 50001: "日历", 50002: "单选钮", 50003: "复选框", 50004: "输入框",
    50005: "超链接", 50006: "图像", 50007: "列表项", 50008: "列表", 50009: "栏",
    50010: "图标", 50011: "菜单项", 50012: "菜单", 50013: "进度条", 50014: "滚动条块",
    50015: "滑块", 50016: "微调框", 50017: "状态提示", 50018: "分栏", 50019: "状态栏",
    50020: "文本", 50021: "标题栏", 50022: "分隔条", 50023: "树项", 50024: "树",
    50025: "标签页", 50026: "标签项", 50028: "工具提示", 50029: "工具栏",
    50030: "文档", 50032: "下拉框", 50033: "表格", 50036: "滚动条", 50037: "面板",
}


def _get_uia():
    """取（或创建）本线程的 IUIAutomation。每线程必须 CoInitialize。"""
    import comtypes
    import comtypes.client
    try:
        comtypes.CoInitialize()
    except Exception:
        pass  # 已初始化 / 单元模式不同：都能用
    uia = getattr(_TL, "uia", None)
    if uia is None:
        comtypes.client.GetModule("UIAutomationCore.dll")
        import comtypes.gen.UIAutomationClient as UIAC
        uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=UIAC.IUIAutomation)
        _TL.uia = uia
        _TL.UIAC = UIAC
    return uia, _TL.UIAC


def _enum_windows(keyword):
    """可见窗口枚举，标题含关键词（区分大小写，与 win-list 行为一致）。"""
    user32 = ctypes.windll.user32
    hits = []

    def cb(h, _):
        if not user32.IsWindowVisible(h):
            return True
        n = user32.GetWindowTextLengthW(h)
        if n <= 0 or n > 400:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, buf, n + 1)
        if keyword and keyword in buf.value:
            hits.append((h, buf.value))
        return True

    CMPFUNC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPVOID)
    user32.EnumWindows(CMPFUNC(cb), None)
    return hits[0] if hits else None


def resolve_window(a):
    """--hwnd / --win / 前台窗口 三级解析。返回 (hwnd, title) 或 (None, 错误信息)。"""
    user32 = ctypes.windll.user32
    hwnd = a.get("hwnd")
    if hwnd:
        hwnd = int(hwnd)
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1) if n else ctypes.create_unicode_buffer(2)
        if n:
            user32.GetWindowTextW(hwnd, buf, n + 1)
        return hwnd, buf.value
    keyword = a.get("win") or a.get("keyword")
    if keyword:
        hit = _enum_windows(keyword)
        if not hit:
            return None, "win_not_found: 没找到标题含「%s」的可见窗口（用 win-list 查实际标题）" % keyword
        return hit
    fg = user32.GetForegroundWindow()
    if fg:
        n = user32.GetWindowTextLengthW(fg)
        buf = ctypes.create_unicode_buffer(n + 1) if n else None
        title = buf.value if buf else ""
        return fg, title
    return None, "no_window: 没给 --hwnd/--win，前台也没有可用窗口"


def _walk(el, depth, out, maxdepth, maxout, region, text_lc):
    """递归收集有名字的控件。region=(x,y,w,h) 只留相交的；text_lc 按名字包含过滤。"""
    if depth > maxdepth or len(out) >= maxout:
        return
    uia, UIAC = _get_uia()
    try:
        name = el.CurrentName or ""
    except Exception:
        name = ""
    try:
        t = int(el.CurrentControlType)
    except Exception:
        t = 0
    if name.strip() and t != 50021:  # 跳过无名控件和标题栏自身
        try:
            r = el.CurrentBoundingRectangle
            x, y, w, h = r.left, r.top, r.right - r.left, r.bottom - r.top
        except Exception:
            x = y = w = h = 0
        if region is not None:
            rx, ry, rw, rh = region
            if x + w < rx or y + h < ry or x > rx + rw or y > ry + rh:
                name = None  # 不相交：丢弃但继续往下走（子树可能相交）
        if text_lc is not None and (name is None or text_lc not in str(name).lower()):
            name = None
        if name:
            out.append({"type": TYPE_NAMES.get(t, str(t)), "name": str(name),
                        "x": x, "y": y, "w": w, "h": h})
    if depth >= maxdepth:
        return
    try:
        arr = el.FindAll(TreeScope_Children, uia.CreateTrueCondition())
        for i in range(arr.Length):  # 注意：叫 GetElement，不是 GetItem（comtypes 命名）
            _walk(arr.GetElement(i), depth + 1, out, maxdepth, maxout, region, text_lc)
            if len(out) >= maxout:
                break
    except Exception:
        pass


def collect(hwnd, maxdepth=7, maxout=80, region=None, text=None, attempts=3):
    """读控件清单。Electron 懒加载：每次尝试前发 WM_GETOBJECT 敲门，间隔 1.2s 重试。"""
    uia, UIAC = _get_uia()
    user32 = ctypes.windll.user32
    text_lc = text.lower() if text else None
    out, dt = [], 0.0
    for attempt in range(attempts):
        user32.SendMessageW(int(hwnd), WM_GETOBJECT, 0, wintypes.LPARAM(OBJID_CLIENT))
        out = []
        t0 = time.perf_counter()
        _walk(uia.ElementFromHandle(int(hwnd)), 0, out, maxdepth, maxout, region, text_lc)
        dt = (time.perf_counter() - t0) * 1000
        if len(out) >= 3:
            break
        time.sleep(1.2)
    return out, dt


def _find_named(hwnd, name, contains=True):
    """按名字找元素：精确匹配优先于包含匹配。
    返回 (el, rect, how, matches)；matches 是 [(el, rect), ...]，第一项即默认选中项。"""
    uia, UIAC = _get_uia()
    lc = name.lower()
    exact, partial = [], []

    def rec(el, depth):
        if depth > 9:
            return
        try:
            nm = el.CurrentName or ""
            t = int(el.CurrentControlType)
            r = el.CurrentBoundingRectangle
        except Exception:
            return
        if nm and t != 50021:
            rect = (r.left, r.top, r.right - r.left, r.bottom - r.top)
            if nm == name:
                exact.append((el, rect))
            elif contains and lc in nm.lower():
                partial.append((el, rect))
        try:
            arr = el.FindAll(TreeScope_Children, uia.CreateTrueCondition())
            for i in range(arr.Length):
                rec(arr.GetElement(i), depth + 1)
        except Exception:
            pass

    rec(uia.ElementFromHandle(int(hwnd)), 0)
    if exact:
        return exact[0][0], exact[0][1], "exact", exact
    if partial:
        return partial[0][0], partial[0][1], "contains", partial
    return None, None, None, []


def _invoke(el):
    """Invoke 模式：程序化"点"，不动鼠标、不抢前台、被遮挡也有效。支持则 True。"""
    try:
        uia, UIAC = _get_uia()
        pat = el.GetCurrentPattern(PATTERN_INVOKE)
        if not pat:
            return False
        pat.QueryInterface(UIAC.IUIAutomationInvokePattern).Invoke()
        return True
    except Exception:
        return False


def _window_at(x, y):
    user32 = ctypes.windll.user32

    class PT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    user32.WindowFromPoint.argtypes = [PT]   # POINT 按值传参，x64 下必须显式声明
    user32.WindowFromPoint.restype = wintypes.HWND
    return user32.WindowFromPoint(PT(x, y))


def _root_ancestor(hwnd):
    return ctypes.windll.user32.GetAncestor(int(hwnd), 2)  # GA_ROOT


# ---------------------------------------------------------------- op 入口 ----

def op_uia_list(a):
    hwnd, title = resolve_window(a)
    if hwnd is None:
        return {"ok": False, "error": title}
    region = None
    if a.get("region"):
        rx, ry, rw, rh = [int(v) for v in str(a["region"]).split(",")]
        region = (rx, ry, rw, rh)
    out, dt = collect(hwnd,
                      maxdepth=int(a.get("depth", 7)),
                      maxout=int(a.get("max", 80)),
                      region=region,
                      text=a.get("text"))
    res = {"ok": True, "hwnd": hwnd, "title": title, "count": len(out),
           "elapsed_ms": round(dt), "elements": out}
    if len(out) < 3:
        res["hint"] = ("该窗口几乎读不到控件（count<3）：多半是 Electron 关着无障碍树或自绘界面，"
                       "走看图通道（shot/locate-text）；Electron 可尝试让应用内开 accessibility")
    return res


def op_uia_click(a):
    name = a.get("name")
    if not name:
        return {"ok": False, "error": "missing_name: 需要 --name（控件名字，先 uia-list 看）"}
    hwnd, title = resolve_window(a)
    if hwnd is None:
        return {"ok": False, "error": title}
    # 先把树捂热（Electron 懒加载），也顺便让 name_not_found 更可信
    collect(hwnd, maxdepth=7, maxout=30, attempts=2)
    el, rect, how, matches = _find_named(hwnd, str(name), contains=True)
    if el is None:
        return {"ok": False, "error": "name_not_found: 清单里没有「%s」" % name,
                "hint": "先 uia-list 看实际名字（注意全角/半角、空格）；读不到清单则走看图通道"}
    idx = a.get("index")
    if len(matches) > 1 and idx is None:
        return {"ok": False, "error": "ambiguous: 「%s」匹配到 %d 个控件" % (name, len(matches)),
                "matches": [{"x": r[0], "y": r[1], "w": r[2], "h": r[3]} for _, r in matches[:10]],
                "hint": "加 --index 0..n 指定第几个，或用更长的 --name"}
    if idx is not None and len(matches) > 1:
        el, rect = matches[max(0, min(int(idx), len(matches) - 1))]
    cx, cy = rect[0] + rect[2] // 2, rect[1] + rect[3] // 2
    mode = str(a.get("mode", "auto")).lower()
    if mode in ("auto", "invoke") and _invoke(el):
        return {"ok": True, "name": str(name), "method": "invoke", "hwnd": hwnd,
                "title": title, "x": cx, "y": cy, "w": rect[2], "h": rect[3], "match": how}
    # 物理点击回退：清单坐标是元素的，但屏幕上那个点可能被别人盖着——点前必须校验落点归属
    if _root_ancestor(_window_at(cx, cy)) != _root_ancestor(hwnd):
        return {"ok": False, "error": "occluded: 控件在(%d,%d)但落点被别的窗口盖住" % (cx, cy),
                "hint": "先 win-front --hwnd %d 再重试；支持 Invoke 的控件保持默认 mode 即可后台点" % hwnd}
    import pyautogui
    pyautogui.click(cx, cy)
    return {"ok": True, "name": str(name), "method": "click", "hwnd": hwnd, "title": title,
            "x": cx, "y": cy, "w": rect[2], "h": rect[3], "match": how}


def op_uia_read(a):
    name = a.get("name")
    if not name:
        return {"ok": False, "error": "missing_name: 需要 --name"}
    hwnd, title = resolve_window(a)
    if hwnd is None:
        return {"ok": False, "error": title}
    collect(hwnd, maxdepth=7, maxout=30, attempts=2)
    el, rect, how, matches = _find_named(hwnd, str(name), contains=True)
    if el is None:
        return {"ok": False, "error": "name_not_found: 清单里没有「%s」" % name}
    value = None
    try:
        uia, UIAC = _get_uia()
        pat = el.GetCurrentPattern(PATTERN_VALUE)
        if pat:
            value = pat.QueryInterface(UIAC.IUIAutomationValuePattern).CurrentValue
    except Exception:
        value = None
    if not value:
        # 输入框用 ValuePattern；文档类（记事本编辑区等）只挂 TextPattern——兜一层
        try:
            uia, UIAC = _get_uia()
            pat = el.GetCurrentPattern(PATTERN_TEXT)
            if pat:
                value = pat.QueryInterface(UIAC.IUIAutomationTextPattern).GetText(-1)
        except Exception:
            pass
    return {"ok": True, "name": str(name), "value": value, "match": how, "title": title,
            "x": rect[0], "y": rect[1], "w": rect[2], "h": rect[3]}
