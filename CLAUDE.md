# CLAUDE.md — 视频压缩工具 技术交接文档

> 供 AI 协作时快速上手，记录关键决策和当前状态。
> 最后更新：2026-04-30

---

## 项目概述

**用途**：批量压缩视频文件，配套清晰度预览 GUI，用于神奇桑桑小鹅通课程视频引流。
**GitHub**：https://github.com/cyanskye/video-compression
**维护者**：神奇桑桑（magicsang666@gmail.com）

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `compress-renew.sh` | 主压缩脚本，CLI 工具，批量处理目录下所有视频 |
| `compress-gui.py` | 浏览器预览 GUI，先看画质差异再决定压哪档 |
| `README.md` | 面向用户的项目说明 |
| `index.md` | GitHub Pages 落地页 |

---

## 使用方式

```bash
# 直接 CLI 压缩（默认 CRF 23）
bash compress-renew.sh /path/to/视频目录

# 指定画质压缩
bash compress-renew.sh --crf 18 /path/to/视频目录   # 高清
bash compress-renew.sh --crf 28 /path/to/视频目录   # 均衡
bash compress-renew.sh --crf 40 /path/to/视频目录   # 省空间

# 跳过确认提示（批量自动化）
bash compress-renew.sh --no-confirm /path/to/视频目录

# GUI 预览选档后压缩（推荐）
python3 compress-gui.py /path/to/视频目录
```

**输出目录**：`<视频目录>/compressed/`（固定，不受 CWD 影响）

---

## compress-renew.sh 关键逻辑

### 参数解析（第 27-40 行）
```bash
NO_CONFIRM=false
CRF=23            # 默认压缩质量
TARGET_PATH=""
NEXT_IS_CRF=false
for arg in "$@"; do
  if [ "$arg" == "--no-confirm" ]; then NO_CONFIRM=true
  elif [ "$arg" == "--crf" ];     then NEXT_IS_CRF=true
  elif [ "$NEXT_IS_CRF" == "true" ]; then CRF="$arg"; NEXT_IS_CRF=false
  elif [ -n "$arg" ];             then TARGET_PATH="$arg"
  fi
done
```

### 输出目录（BASE_DIR 逻辑）
```bash
if [ -d "$TARGET_PATH" ]; then
  BASE_DIR=$(realpath "$TARGET_PATH")
elif [ -f "$TARGET_PATH" ]; then
  BASE_DIR=$(realpath "$(dirname "$TARGET_PATH")")
else
  BASE_DIR=$(realpath ".")
fi
OUTPUT_DIR="$BASE_DIR/compressed"
```

### ffmpeg 压缩参数
```bash
-c:v libx264 -preset veryfast -crf $CRF -threads 0
-c:a aac -b:a 128k
```

### 进度时间计算（关键修复）
```bash
# 必须把 HH:MM:SS 转成总秒数，不能只取秒字段
current_sec=$((10#$h * 3600 + 10#$m * 60 + 10#$s))
```

---

## compress-gui.py 关键逻辑

### 整体流程
1. 扫描视频目录，取第一个视频作为预览源
2. 随机抽 2-3 个时间戳（避开首尾 5%）
3. 每个时间戳：提取原版帧 + CRF 18/28/40 三档压缩帧（各 3 秒样本取中间帧）
4. 用实测比特率推算整个目录压缩后大小
5. 生成 HTML，内嵌 base64 图片，启动本地 HTTP server
6. 浏览器打开预览页，用户选档后 fetch `/start?crf=XX`
7. Python 用 `os.execv` 移交给 `compress-renew.sh` 执行

### CRF 预览档位
| 档位 | CRF | 用户名称 | 说明 |
|------|-----|---------|------|
| 🟢 高清 | 18 | 画质优先 | 接近无损 |
| 🟡 标准 | 28 | 均衡 | 默认推荐 |
| 🔴 省空间 | 40 | 体积优先 | 明显压缩感，用于对比 |

**注意**：预览用 18/28/40 三档是为了让差异肉眼可见。实际压缩 CRF 40 太低，建议用户选 18 或 28。

### 为什么用浏览器而不是 tkinter
macOS 26 (beta) 上系统 Python 3.9 的 tkinter 会 SIGABRT 崩溃（`macOS 26 (2603) or later required`），Homebrew Python 3.14 也没有 `_tkinter` 模块。改用 `http.server + webbrowser.open()` 方案，零依赖。

### 预览帧分辨率
```python
PREVIEW_W = 1920
PREVIEW_H = 1080
```
与视频原始分辨率一致，base64 内嵌 HTML，文件较大（正常）。

---

## 技术决策记录

| 决策 | 原因 |
|------|------|
| `-preset veryfast` | 比 medium 快 3-4x，画质损失可接受 |
| 输出到 `<视频目录>/compressed/` | 避免压缩产物出现在代码仓库目录 |
| CRF 预览用 18/28/40 | 18→23→28 静帧差异太小，肉眼看不出来 |
| 浏览器 GUI | tkinter 在 macOS 26 上崩溃，无法使用 |
| 预览帧 1920×1080 | 低分辨率（原来 320×180）放大显示模糊 |
| os.execv 移交压缩 | GUI 关闭后 CLI 接管，保持终端进度输出体验 |

---

## 已知问题 / 待办

- [ ] compress-renew（无扩展名旧版二进制）遗留在目录，可删除
- [ ] GUI 预览生成较慢（每帧需压 3 秒样本），考虑并行化
- [ ] CRF 40 太激进，下次可考虑改成 35

---

## 仓库结构

```
video-compression/
├── compress-renew.sh     # 主脚本（核心）
├── compress-gui.py       # 预览 GUI（核心）
├── README.md             # 用户文档
├── index.md              # GitHub Pages
├── CLAUDE.md             # 本文件（技术交接）
├── .gitignore
└── LICENSE
```

不在 Git 中（.gitignore 忽略）：
- `compressed/` — 压缩产物
- `compress_log_*.txt` — 运行日志
- `compress_progress.txt` — 进度文件
- 营销文稿（promotion-*.md、seo-*.md 等）
