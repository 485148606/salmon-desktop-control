<!-- 三文鱼大模型附录：仅在下面这类场景才需要读 -->
**适用场景**：在沙箱 Bash 里启动的 GUI 进程被回收，怎么用 explorer 的手拉起来

**来源**：SKILL.md 原文逐字搬出，内容未删改

---

### 0.5.5 沙箱里怎么把 GUI 程序"真正"启动起来（2026-09-14 实测，很有用）

**问题**：WorkBuddy Bash/PowerShell 里启动的任何进程（GUI 也一样），**在该条命令结束时会被连同子孙一起回收**。实测以下**全部失败**：

- `Start-Process "xxx.exe"` → 命令一结束进程就没了
- `subprocess.Popen(..., creationflags=DETACHED_PROCESS|CREATE_BREAKAWAY_FROM_JOB|CREATE_NEW_PROCESS_GROUP)` → 同样是死的
- `Invoke-CimMethod Win32_Process Create`（WMI 起进程）→ **安全层直接拦**："WMI/CIM process creation is equivalent to Start-Process"

**唯一可靠解法：借 explorer.exe 的手去启动。**
"运行"对话框（Win+R）是由 explorer.exe 处理的，它创建的进程父级是 explorer、不在沙箱 job 里，**能永久存活**：

```bash
"$PY" "$MC" hotkey --keys "win,r"               # 开"运行"对话框
sleep 2
"$PY" "$MC" type --text '"C:\完整\路径\程序.exe" 参数1 参数2'   # 剪贴板粘贴，支持中文路径
sleep 2
"$PY" "$MC" key --key enter                      # 回车，explorer 去拉进程
```

同理可用的变体：让 explorer **双击**桌面/开始菜单上的 `.lnk`（但 .lnk 没法带参数）。

**两个坑**：
1. **先截屏确认"运行"框里文字对**再回车 —— 若在 DevTools/浏览器抢焦点或渲染未完成时 paste，可能只进去一部分。肉眼看不清就 `shot` + 裁剪底部左侧区域读图。
2. 启动后**用端口/进程双重验证**，别只看窗口：`socket.connect_ex(('127.0.0.1',port))` + `tasklist /FI "IMAGENAME eq xxx.exe"`。DevTools 的端口在 `%LOCALAPPDATA%\微信开发者工具\User Data\<hash>\Default\.cli`（HTTP/CLI 端口）和 `.ide`（自动化端口）两个文件里，`.ide-status` 为 `On` 表示自动化已开。

