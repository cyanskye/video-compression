# compress-renew.sh

一个用于 **批量压缩视频文件** 的 Shell 脚本，支持文件夹内所有视频的自动压缩和转码，适用于 Mac / Linux 环境。

由 [神奇桑桑](https://github.com/cyanskye) 开发，适用于短视频工作者、内容创作者、团队协作等多种场景。

---

## 🧰 核心功能

- 批量压缩 `.mp4` / `.mov` / `.mkv` 视频文件
- 保留原始文件，压缩文件以 `_compressed` 后缀命名
- 默认压缩比高，画质控制适中（可按需修改参数）
- 支持文件夹内递归处理

---

## 🚀 使用方式

### 1. 下载脚本

```bash
curl -O https://raw.githubusercontent.com/cyanskye/video-compression/main/compress-renew.sh
chmod +x compress-renew.sh
```

2. 开始压缩

```bash
./compress-renew.sh /路径/到/你的视频文件夹
```

压缩完成后，文件将以 _compressed.mp4 命名保存在同目录下。

🖥️ 环境要求

请确保系统已安装：
• bash
• ffmpeg（如未安装，可通过 Homebrew 安装）

```bash
brew install ffmpeg
```

📺 示例演示
•🌐 GitHub Pages 使用文档：👉 点击查看
•📬 公众号文章讲解：👉 《compress-renew.sh 用 AI 思维压缩视频文件》🔗 阅读原文
☕ 支持开发者

如果这个项目帮到了你，欢迎请我喝一杯咖啡 ☕～

微信赞助

<img src="https://github.com/user-attachments/assets/c2e30e34-aa4e-442f-b8b5-85054804fac2" alt="视频压缩工具脚本费" width="400"/>


微信号：神奇桑桑

📜 License

本项目采用 MIT License 开源协议，欢迎自由使用与二次开发。

📌 联系作者
- GitHub: cyanskye
- 微信公众号：神奇桑桑流量思维
- Email：magicsang666@gmail.com
