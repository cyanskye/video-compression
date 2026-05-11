# 本地视频压缩 Agent

一个本地运行的视频压缩工具：先分析视频目录，给出智能压缩建议和真实预览，再批量压缩到 `compressed/`。视频不会上传，所有分析、抽帧、压缩都在你的电脑上完成。

适合课程视频、小鹅通素材、短视频批量交付前的体积优化。

## 核心能力

- 扫描 `.mp4` / `.mov` / `.mkv` / `.m4v`
- 自动排除 `compressed/`，避免循环压缩
- 基于分辨率、码率、时长、文件大小、字幕/文字风险给出本地智能推荐
- 浏览器本地 Agent：目录概览、推荐理由、风险提示、真实 CRF 预览、实时进度
- 压缩结果保持子目录结构，输出到 `<视频目录>/compressed/`
- 生成 `compressed/课程视频清单.md`
- 保留旧 Shell 入口：`compress-renew.sh` 仍然可用

## 使用方式（CLI first）

### 1) 一键检查依赖

```bash
./compress-renew.sh --doctor
```

### 2) 先预检（不执行压缩）

```bash
./compress-renew.sh --dry-run /路径/到/视频目录
```

### 3) 执行压缩（默认会确认）

```bash
./compress-renew.sh /路径/到/视频目录
./compress-renew.sh --crf 20 /路径/到/视频目录
```

### 4) 自动化批处理（跳过确认）

```bash
./compress-renew.sh --crf 23 --yes /路径/到/视频目录
```

> 输出目录固定为：`<视频目录>/compressed/`

## 高级命令（可选）

```bash
python3 video_agent.py analyze /路径/到/视频目录
python3 video_agent.py compress /路径/到/视频目录 --crf 23 --no-confirm
python3 video_agent.py app /路径/到/视频目录
python3 compress-gui.py /路径/到/视频目录
```

## 压缩档位

| 档位 | CRF | 适合场景 |
|---|---:|---|
| 近原画 | 18 | 字幕、课件、录屏、小字号文字较多 |
| 课程清晰 | 20 | 课程视频默认推荐，优先保住文字和人脸 |
| 均衡压缩 | 23 | 普通真人视频，小字少时可用 |
| 强力省空间 | 28 | 明显减小体积，接受压缩感 |

## 环境要求

- macOS / Linux
- Python 3
- ffmpeg / ffprobe

安装 ffmpeg：

```bash
brew install ffmpeg
```

不需要 Flask、Pillow 或 tkinter。

## 隐私边界

- 不上传视频
- 不调用云端 AI
- 不联网即可完成分析和压缩
- 浏览器页面只监听 `127.0.0.1`，用于本机操作

## 给 AI 协作者使用

仓库内提供了 `skills/video-compression-advisor/SKILL.md`。把它安装或复制到 Codex Skills 后，AI 可以稳定执行这套流程：

1. 先分析目录
2. 解释推荐档位
3. 生成预览或启动本地 Agent
4. 用户确认后再压缩
5. 检查报告和失败文件

Skills 适合作为 AI 工作流说明；普通用户仍建议使用 `video_agent.py app`。

## License

MIT
