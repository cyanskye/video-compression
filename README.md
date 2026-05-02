# compress-renew.sh

一个用于 **批量压缩视频文件** 的 Shell 脚本 + 浏览器 GUI 预览工具，支持文件夹内所有视频的自动压缩和转码，适用于 Mac / Linux 环境。

由 [神奇桑桑](https://github.com/cyanskye) 开发，适用于短视频工作者、内容创作者、团队协作等多种场景。

---

## 🧰 核心功能

- 批量压缩 `.mp4` / `.mov` / `.mkv` 视频文件
- 压缩文件保存到 `视频目录/compressed/` 子文件夹，原文件不动
- 支持 `--crf` 参数调节压缩质量（数值越大文件越小）
- 浏览器 GUI 预览三档压缩效果，选完直接开压

---

## 🚀 使用方式

### 方式一：CLI 直接压缩

```bash
# 下载脚本
curl -O https://raw.githubusercontent.com/cyanskye/video-compression/main/compress-renew.sh
chmod +x compress-renew.sh

# 默认质量（CRF 23）压缩
bash compress-renew.sh /路径/到/你的视频文件夹

# 指定 CRF 质量
bash compress-renew.sh --crf 28 /路径/到/你的视频文件夹

# 跳过确认提示（批处理用）
bash compress-renew.sh --crf 28 --no-confirm /路径/到/你的视频文件夹
```

压缩完成后，文件保存在 `/路径/到/你的视频文件夹/compressed/` 目录内，文件名不变。

### 方式二：GUI 预览选档后压缩

```bash
# 安装依赖（仅需一次）
pip3 install flask pillow

# 启动 GUI
python3 compress-gui.py /路径/到/你的视频文件夹
```

浏览器自动打开，展示四档对比（原版 / 画质优先 / 均衡 / 体积优先），点击图片可全屏查看，选好后点击"开始压缩"。

### CRF 参数参考

| 档位 | CRF 值 | 说明 |
|------|--------|------|
| 画质优先 | 18 | 最清晰，文件较大 |
| 均衡（默认） | 23 | 画质与体积平衡 |
| 体积优先 | 28 | 文件较小，画质略降 |

---

## 🖥️ 环境要求

- bash
- ffmpeg（未安装可通过 Homebrew 安装）
- Python 3（GUI 模式需要）

```bash
brew install ffmpeg
pip3 install flask pillow
```

---

## 📺 示例演示

- 🌐 GitHub Pages 使用文档：👉 [点击查看](https://cyanskye.github.io/video-compression/)
- 📬 公众号文章讲解：👉 《compress-renew.sh 用 AI 思维压缩视频文件》

---

## ☕ 支持开发者

如果这个项目帮到了你，欢迎请我喝一杯咖啡 ☕～

微信赞助

<img src="https://github.com/user-attachments/assets/c2e30e34-aa4e-442f-b8b5-85054804fac2" alt="视频压缩工具脚本费" width="400"/>

微信号：神奇桑桑

---

## 📜 License

本项目采用 MIT License 开源协议，欢迎自由使用与二次开发。

---

## 📌 联系作者

- GitHub: [cyanskye](https://github.com/cyanskye)
- 微信公众号：神奇桑桑流量思维
- Email：magicsang666@gmail.com
