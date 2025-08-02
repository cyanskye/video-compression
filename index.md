---
layout: default
title: compress-renew.sh - 视频批量压缩脚本
---

# 🎥 compress-renew.sh - 视频批量压缩脚本

一个专为短视频创作者、内容运营团队、培训服务人员设计的 **批量视频压缩工具**。

无需图形界面，轻量好用，跨平台适配（macOS / Linux），一行命令即可批量压缩视频，保留清晰度，极大节省空间与传输时间。

> 📌 项目地址：[GitHub 仓库](https://github.com/cyanskye/video-compression)

---

## 🚀 快速上手

### ✅ 下载脚本

```bash
curl -O https://raw.githubusercontent.com/cyanskye/video-compression/main/compress-renew.sh
chmod +x compress-renew.sh
```

### ✅ 使用脚本
```bash
./compress-renew.sh /路径/到/视频文件夹
```

•	支持 .mp4 .mov .mkv 等视频格式
•	输出为 _compressed 后缀的新视频文件
•	默认保留原视频，压缩效果适配主流短视频平台

### 🛠️ 技术说明
本工具基于 ffmpeg，使用 H.264 编码进行压缩，默认压缩比为中高等级，适合内容平台如：
•	视频号 / 小红书 / 抖音
•	微信群 / 飞书分享
•	培训系统或网盘上传（小鹅通/创客匠人等知识付费平台）

如需自定义码率、分辨率、帧率，请修改脚本中的参数区域。

### 📽️ 视频演示

🧪 通过以下方式查看使用效果：

•	📺 B站演示视频：点击观看
•	🧾 公众号文章说明：阅读原文
•	🌐 本项目页面：当前页面即为项目展示主页

### 💬 常见问题

Q: 会覆盖原文件吗？
A: 不会。脚本默认会新生成 _compressed 文件，原文件保留。

Q: 可以在 Windows 上使用吗？
A: 建议使用 WSL（Windows 子系统）或 mac/Linux 环境。后续会考虑推出 Windows 版本。

Q: 压缩参数能调整吗？
A: 可以，打开脚本后自行修改 ffmpeg 相关命令部分的参数。

⸻

### ☕ 支持开发者

如果你觉得这个工具对你有帮助，可以扫码请我喝杯咖啡 👇
<br/>
<img src="https://github.com/user-attachments/assets/c2e30e34-aa4e-442f-b8b5-85054804fac2" alt="视频压缩工具脚本费" width="400"/>
<br/>
微信号：神奇桑桑（MagicSang666）

### 📄 License
本项目采用 MIT License 开源协议，欢迎自由使用与二次开发。

⸻
### 📬 联系我
•	GitHub：cyanskye
•	公众号：神奇桑桑流量思维
•	邮箱：magicsang666@gmail.com
