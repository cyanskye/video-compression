#!/bin/bash
# ----------------------------
# 授权校验模块 by 神奇桑桑
# ----------------------------
USER_ID="cyanskye"
AUTH_URL="https://gist.githubusercontent.com/cyanskye/GIST_ID_PLACEHOLDER/raw/auth.json"

echo "🔒 正在联网校验使用授权..."
auth_list=$(curl -s "$AUTH_URL")
if [[ $? -ne 0 || -z "$auth_list" ]]; then
  echo "⚠️ 无法获取授权名单，请检查网络或联系神奇桑桑。"
  exit 1
fi

if ! echo "$auth_list" | grep -q "\"${USER_ID}\""; then
  echo "❌ 抱歉，GitHub 用户 $USER_ID 未在授权名单中。请扫码付款后联系神奇桑桑添加授权。"
  exit 1
fi

echo "✅ 授权校验成功，继续执行压缩脚本。"


#!/bin/bash

#!/bin/bash
# ======================================================
# 项目: 视频批量压缩工具
# 作者: 神奇桑桑 (思路提供), ChatGPT & TRAE (代码实现)
# 创建日期: 2025年07月22日 15:18:36
# 最后更新: 2025年07月22日 23:42:25

# 主要功能:
# - 帮助小额通上架前的短视频压缩
# - 批量处理视频文件，保持目录结构
# - 自动生成课程视频清单.md文件
# - 支持断点重开和单实例运行
#
# 项目背景:
# 客户提供的3分钟视频大小超过500MB，超出预期
# 为避免从源头上压缩影响其他地方使用高清画质
# 开发此工具进行批量压缩，平衡画质和文件大小
#
# 未来规划:
# - 接入API，实现自动压缩并上架课程
#
# 致谢:
# 感谢AI工具提供的赋能，让视频压缩工作变得更加轻松高效
# ======================================================

# ======================================================
# 目录和文件定义
# ======================================================
# 定义输出目录和创建
OUTPUT_DIR="./compressed"
mkdir -p "$OUTPUT_DIR"

# 防止无限循环压缩 - 排除输出目录
EXCLUDE_DIR="./compressed"
# 确保排除目录的路径格式正确
EXCLUDE_DIR=$(realpath "$EXCLUDE_DIR")



# ======================================================
# 断点重开机制
# ======================================================
# 定义记录文件
progress_file="./compress_progress.txt"

# 确保progress_file存在
touch "$progress_file"

# 检查文件是否已完全压缩
is_file_compressed() {
  local file=$1
  # 检查文件是否在进度文件中
  grep -Fxq "$file" "$progress_file" 2>/dev/null
}

# ======================================================
# 初始化日志和Markdown文件
# ======================================================
start_time=$(date +%s)
log_file="compress_log_$(date +%Y%m%d_%H%M%S).txt"
md_file="./课程视频清单.md"

# ======================================================
# 系统信息和日志初始化
# ======================================================
# 记录系统信息
echo "[系统信息] 操作系统: $(uname -a)" >> "$log_file"
echo "[系统信息] 当前用户: $(whoami)" >> "$log_file"
echo "[系统信息] 当前目录: $(pwd)" >> "$log_file"

# ======================================================
# Markdown文件管理
# ======================================================
# 确保创建Markdown文件
if [ ! -f "$md_file" ]; then
  echo "# 🎬 课程视频清单" > "$md_file"
  echo "🗓️ 生成时间：$(date '+%Y-%m-%d %H:%M:%S')" >> "$md_file"
  echo "👤 压缩作者：$(whoami)" >> "$md_file"
  echo "🖥️ 压缩机器：$(scutil --get ComputerName)" >> "$md_file"
  echo "" >> "$md_file"
  echo "| 课程名称 | 原路径 | 原大小 | 时长 | 压缩后大小 | 耗时 | 压缩后文件 | 节省空间 | 压缩比 |" >> "$md_file"
  echo "|-----------|--------|---------|------|-------------|------|--------------|----------|--------|" >> "$md_file"
  echo "✅ 已创建课程视频清单.md" | tee -a "$log_file"
else
  # 更新生成时间
  sed -i '' "2s/.*/🗓️ 生成时间：$(date '+%Y-%m-%d %H:%M:%S')/" "$md_file"
  # 确保作者和机器信息存在
  if ! grep -q "👤 压缩作者：" "$md_file"; then
    sed -i '' "2a\
👤 压缩作者：$(whoami)\
🖥️ 压缩机器：$(hostname) ($(uname -a | cut -d ' ' -f 1-3))" "$md_file"
  else
    # 更新作者和机器信息
    sed -i '' "3s/.*/👤 压缩作者：$(whoami)/" "$md_file"
    sed -i '' "4s/.*/🖥️ 压缩机器：$(scutil --get ComputerName)/" "$md_file"
  fi
  echo "✅ 已更新课程视频清单.md的生成时间和基本信息" | tee -a "$log_file"
fi

echo "🗓 开始压缩时间：$(date)" | tee -a "$log_file"
echo "📂 输出目录：$OUTPUT_DIR" | tee -a "$log_file"
echo "------------------------------------------" | tee -a "$log_file"

# ======================================================
# 环境设置和文件收集
# ======================================================
# 修复空格/中文路径处理
export LC_ALL=en_US.UTF-8

# 收集所有视频文件路径到数组 - 排除压缩目录
video_files=()
while IFS= read -r -d '' file; do
  # 确保只处理当前目录下的视频文件，不包括子目录中的compressed目录
  if [[ $(realpath "$file") != *"$EXCLUDE_DIR"* ]]; then
    video_files+=("$file")
  fi
done < <(LC_ALL=en_US.UTF-8 find . -type f \( -iname "*.mp4" -o -iname "*.mov" -o -iname "*.mkv" \) -print0)

# 收集所有封面文件路径到数组
cover_files=()
while IFS= read -r -d '' file; do
  cover_files+=("$file")
done < <(LC_ALL=en_US.UTF-8 find . -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) -not -path "./$EXCLUDE_DIR/*" -print0)

# 统计找到的文件数量
file_count=${#video_files[@]}
echo "🔍 找到的视频文件总数: $file_count" | tee -a "$log_file"

# 初始化计数器和计时器
counter=0
total_estimated_time=0

# 计算总预估时间
for file in "${video_files[@]}"; do
  duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$file")
  duration_int=$(printf "%.0f" "$duration")
  total_estimated_time=$((total_estimated_time + duration_int))
done

total_estimated_fmt=$(printf '%02d:%02d:%02d' $((total_estimated_time/3600)) $(((total_estimated_time%3600)/60)) $((total_estimated_time%60)))

# ======================================================
# 用户交互和系统检查
# ======================================================
# 检查是否需要跳过确认框
if [ "$1" != "--no-confirm" ]; then
  # 交互逻辑 - 询问用户是否需要压缩
  clear
   echo "=========================================="
   echo "📊 找到 $file_count 个视频文件"
   echo "⌛ 预估总压缩时长: $total_estimated_fmt"
   echo "=========================================="
   read -p "是否开始压缩？(y/n): " confirm
   if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
     echo "❌ 压缩已取消" | tee -a "$log_file"
     exit 0
   fi
fi

# ======================================================
# 前置条件检查
# ======================================================
# 检查是否有视频文件
if [ $file_count -eq 0 ]; then
  echo "❌ 错误: 没有找到视频文件" | tee -a "$log_file"
  exit 1
fi

# 检查ffmpeg是否可用
if ! command -v ffmpeg &> /dev/null; then
  echo "❌ 错误: 未找到ffmpeg命令，请先安装ffmpeg" | tee -a "$log_file"
  exit 1
fi

# 检查磁盘空间
free_space=$(df -k . | tail -1 | awk '{print $4}')
# 确保有至少1GB的可用空间
if [ $free_space -lt 1048576 ]; then
  echo "❌ 错误: 磁盘空间不足，请确保有至少1GB的可用空间" | tee -a "$log_file"
  exit 1
fi

# 检查内存是否足够
# 假设我们需要至少2GB的内存
memory_total=$(sysctl -n hw.memsize)
memory_total_gb=$((memory_total / 1024 / 1024 / 1024))
if [ $memory_total_gb -lt 2 ]; then
  echo "⚠️ 警告: 系统内存不足2GB，压缩过程可能会变慢或失败" | tee -a "$log_file"
fi

# 检查是否有权限写入输出目录
if [ ! -w "$OUTPUT_DIR" ]; then
  echo "❌ 错误: 没有权限写入输出目录 $OUTPUT_DIR" | tee -a "$log_file"
  exit 1
fi

# 检查是否有权限读取进度文件
if [ -f "$progress_file" ] && [ ! -r "$progress_file" ]; then
  echo "❌ 错误: 没有权限读取进度文件 $progress_file" | tee -a "$log_file"
  exit 1
fi

# 检查是否有权限写入进度文件
if [ ! -w "$(dirname "$progress_file")" ]; then
  echo "❌ 错误: 没有权限写入进度文件 $progress_file" | tee -a "$log_file"
  exit 1
fi

# 检查是否有权限写入日志文件
if [ ! -w "$(dirname "$log_file")" ]; then
  echo "❌ 错误: 没有权限写入日志文件 $log_file" | tee -a "$log_file"
  exit 1
fi

# 检查是否有权限写入Markdown文件
if [ -f "$md_file" ] && [ ! -w "$md_file" ]; then
  echo "❌ 错误: 没有权限写入Markdown文件 $md_file" | tee -a "$log_file"
  exit 1
elif [ ! -w "$(dirname "$md_file")" ]; then
  echo "❌ 错误: 没有权限创建Markdown文件 $md_file" | tee -a "$log_file"
  exit 1
fi

# ======================================================
# 断点进度加载
# ======================================================
# 检查是否有断点进度
completed_files=()
if [ -f "$progress_file" ]; then
  echo "🔍 发现断点记录，正在加载已完成的文件..." | tee -a "$log_file"
  while IFS= read -r line; do
    completed_files+=("$line")
  done < "$progress_file"
fi

echo "------------------------------------------" | tee -a "$log_file"

# ======================================================
# 压缩准备
# ======================================================
# 计算源文件总大小
total_source_size=0
for file in "${video_files[@]}"; do
  source_size=$(du -k "$file" | cut -f1)
  total_source_size=$((total_source_size + source_size))
done

total_source_size_human=$(printf '%.2fGB' $(echo "$total_source_size / 1024 / 1024" | bc -l))

# 初始化压缩后总大小
total_compressed_size=0

# ======================================================
# 视频压缩处理
# ======================================================
# 遍历视频文件数组
for file in "${video_files[@]}"; do
  # 检查文件是否需要重新压缩
  if is_file_compressed "$file"; then
    echo "🔄 跳过已压缩的文件: $file" | tee -a "$log_file"
    continue
  fi

  # 增加计数器
  counter=$((counter+1))
  filename=$(basename "$file")
  filepath=$(dirname "$file")
  relpath="${filepath#./}"
  # 防止递归创建压缩目录
  relpath=$(echo "$relpath" | sed 's|^'"$EXCLUDE_DIR"'||')
  output_subdir="$OUTPUT_DIR/$relpath"
  # 确保输出目录路径没有空格
  output_subdir=$(echo "$output_subdir" | tr -s ' ')
  mkdir -p "$output_subdir"
  if [ $? -ne 0 ]; then
    echo "❌ 错误: 创建输出子目录失败: $output_subdir" | tee -a "$log_file"
    continue
  fi

  # 获取文件基本信息
  raw_size=$(du -h "$file" | cut -f1)
  duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$file")
  duration_int=$(printf "%.0f" "$duration")
  duration_fmt=$(printf '%02d:%02d:%02d' $((duration_int/3600)) $(((duration_int%3600)/60)) $((duration_int%60)))

  # 预估时长
  estimated_time=$duration_int
  total_estimated_time=$((total_estimated_time + estimated_time))
  total_estimated_fmt=$(printf '%02d:%02d:%02d' $((total_estimated_time/3600)) $(((total_estimated_time%3600)/60)) $((total_estimated_time%60)))

  # 计算已用时间和预计剩余时间
  current_time=$(date +%s)
  elapsed_total_sec=$((current_time - start_time))
  elapsed_total_fmt=$(printf '%02d:%02d:%02d' $((elapsed_total_sec/3600)) $(((elapsed_total_sec%3600)/60)) $((elapsed_total_sec%60)))
  remaining_time=$((total_estimated_time - elapsed_total_sec))
  remaining_fmt=$(printf '%02d:%02d:%02d' $((remaining_time/3600)) $(((remaining_time%3600)/60)) $((remaining_time%60)))

  # 显示进度信息
  progress_percent=$((counter * 100 / file_count))
  # 清除当前行并显示进度
  echo -e "\r\033[K"
  echo "=========================================="
  echo "📊 压缩总进度: $counter/$file_count ($progress_percent%)"
  echo "------------------------------------------"
  echo "🎬 正在压缩: $filename"
  echo "📁 源路径: $file"
  echo "📏 原始大小: $raw_size"
  echo "⏱️ 视频时长: $duration_fmt"
  echo "------------------------------------------"
  echo "⏳ 已用时间: $elapsed_total_fmt"
  echo "🔜 预计剩余时间: $remaining_fmt"
  echo "=========================================="

  # 开始压缩
  compress_start=$(date +%s)
  output_file="$output_subdir/${filename%.*}_1080p.mp4"
  # 确保输出文件路径没有空格
  output_file=$(echo "$output_file" | tr -s ' ')

  # 实时更新进度信息
  current_time=$(date +%s)
  elapsed_total_sec=$((current_time - start_time))
  elapsed_total_fmt=$(printf '%02d:%02d:%02d' $((elapsed_total_sec/3600)) $(((elapsed_total_sec%3600)/60)) $((elapsed_total_sec%60)))
  remaining_time=$((total_estimated_time - elapsed_total_sec))
  remaining_fmt=$(printf '%02d:%02d:%02d' $((remaining_time/3600)) $(((remaining_time%3600)/60)) $((remaining_time%60)))
  
  # 显示实时进度到控制台
  echo -e "\r🔄 正在压缩: $filename ($counter/$file_count) | 已用时间: $elapsed_total_fmt | 剩余时间: $remaining_fmt" 
  
  # 记录到日志
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] 正在压缩: $filename ($counter/$file_count)" | tee -a "$log_file"
  echo "[文件信息] 大小: $raw_size, 时长: $duration_fmt" | tee -a "$log_file"
  echo "[进度信息] 已用时间: $elapsed_total_fmt, 预计总时长: $total_estimated_fmt, 剩余时间: $remaining_fmt" | tee -a "$log_file"
  echo "[输出信息] 输出文件: $output_file" | tee -a "$log_file"

  # 使用ffmpeg压缩视频，并只显示进度信息
  # 优化压缩参数: 增加线程数，优化编码速度
  # 保留错误输出到日志文件
  ffmpeg -y -hide_banner -i "$file" \
    -vf "scale=1920:1080" \
    -c:v libx264 -preset medium -crf 23 -threads 0 \
    -c:a aac -b:a 160k -ac 1 \
    -progress pipe:1 \
    "$output_file" 2>> "$log_file" | while read line; do
    # 解析ffmpeg进度信息
    if [[ $line == frame=* ]]; then
      frame=$(echo $line | cut -d'=' -f2)
    elif [[ $line == fps=* ]]; then
      fps=$(echo $line | cut -d'=' -f2)
    elif [[ $line == out_time=* ]]; then
      out_time=$(echo $line | cut -d'=' -f2)
      # 计算单个视频进度
      video_progress=$(echo "$out_time" | cut -d':' -f3 | cut -d'.' -f1)
      # 检查video_progress是否为数字
      if [[ $video_progress =~ ^[0-9]+$ ]]; then
        # 确保将video_progress解释为十进制数
        video_progress=$((10#$video_progress * 100 / duration_int))
      else
        # 非数字则设为0
        video_progress=0
      fi
      # 显示单个视频进度
      echo -ne "\r🔄 视频压缩进度: $video_progress%" 
    fi
  done

  # 检查ffmpeg命令是否成功执行
  if [ $? -ne 0 ]; then
    echo "❌ 错误: ffmpeg执行失败: $file" | tee -a "$log_file"
    # 记录错误详情到日志
    echo "[错误详情] ffmpeg命令执行失败，退出码: $?" >> "$log_file"
    continue
  fi

  # 确保文件确实被创建
  if [ ! -f "$output_file" ]; then
    echo "❌ 错误: 输出文件未创建: $output_file" | tee -a "$log_file"
    continue
  fi

  # 检查输出文件大小，确保不是空文件
  if [ ! -s "$output_file" ]; then
    echo "❌ 错误: 输出文件为空: $output_file" | tee -a "$log_file"
    continue
  fi

  # 压缩完成，显示结果
  compress_end=$(date +%s)
  elapsed_sec=$((compress_end - compress_start))
  elapsed_fmt=$(printf '%02d:%02d' $(($elapsed_sec/60)) $(($elapsed_sec%60)))
  new_size=$(du -h "$output_file" | cut -f1)
  new_size_kb=$(du -k "$output_file" | cut -f1)
  total_compressed_size=$((total_compressed_size + new_size_kb))

  # 同步移动封面文件
  filename_no_ext=$(basename "$file" .${file##*.})
  for cover in "${cover_files[@]}"; do
    cover_basename=$(basename "$cover")
    cover_name_no_ext=$(basename "$cover" .${cover##*.})
    if [[ "$cover_name_no_ext" == "$filename_no_ext"* ]]; then
      cover_output_dir="$output_subdir"
      cp -f "$cover" "$cover_output_dir"
      if [ $? -eq 0 ]; then
        echo "✅ 已同步封面: $cover_basename" | tee -a "$log_file"
      else
        echo "❌ 同步封面失败: $cover_basename" | tee -a "$log_file"
      fi
      break
    fi
  done

  echo -e "\n✅ 完成: $filename"
  echo "📦 压缩后大小: $new_size"
  echo "⏱️ 压缩耗时: $elapsed_fmt"
  echo "------------------------------------------"

  # 记录到日志和表格
  echo "[$(date '+%H:%M:%S')] ✅ 完成: $filename" | tee -a "$log_file"
  echo "[结果] 压缩后大小: $new_size, 耗时: $elapsed_fmt" | tee -a "$log_file"
  
  # 计算压缩节省的空间和压缩比
  source_size_kb=$(du -k "$file" | cut -f1)
  saved_size_kb=$((source_size_kb - new_size_kb))
  saved_size_human=$(printf '%.2fMB' $(echo "$saved_size_kb / 1024" | bc -l))
  if [ $source_size_kb -gt 0 ]; then
    compression_ratio=$(printf '%.1f%%' $(echo "($source_size_kb - $new_size_kb) * 100 / $source_size_kb" | bc -l))
  else
    compression_ratio="0.0%"
  fi
  
  # 调试信息 - 显示要写入Markdown的内容
  echo "[调试] 准备写入Markdown: | ${filename%.*} | $relpath | $raw_size | $duration_fmt | $new_size | $elapsed_fmt | ${filename%.*}_1080p.mp4 | $saved_size_human | $compression_ratio |" | tee -a "$log_file"
  
  # 确保正确写入Markdown文件
  if echo "| ${filename%.*} | $relpath | $raw_size | $duration_fmt | $new_size | $elapsed_fmt | ${filename%.*}_1080p.mp4 | $saved_size_human | $compression_ratio |" >> "$md_file"; then
    echo "✅ 已更新课程视频清单.md" | tee -a "$log_file"
  else
    echo "❌ 无法更新课程视频清单.md" | tee -a "$log_file"
    # 尝试创建新的Markdown文件
    echo "# 🎬 课程视频清单" > "$md_file"
    echo "🗓️ 生成时间：$(date '+%Y-%m-%d %H:%M:%S')" >> "$md_file"
    echo "" >> "$md_file"
    echo "| 课程名称 | 原路径 | 原大小 | 时长 | 压缩后大小 | 耗时 | 压缩后文件 | 节省空间 | 压缩比 |" >> "$md_file"
    echo "|-----------|--------|---------|------|-------------|------|--------------|----------|--------|" >> "$md_file"
    echo "| ${filename%.*} | $relpath | $raw_size | $duration_fmt | $new_size | $elapsed_fmt | ${filename%.*}_1080p.mp4 | $saved_size_human | $compression_ratio |" >> "$md_file"
    echo "🔄 已尝试重新创建课程视频清单.md" | tee -a "$log_file"
  fi
  echo "------------------------------------------" | tee -a "$log_file"

  # 断点重开机制 - 记录已完成的文件
  echo "$file" >> "$progress_file"
done

# ======================================================
# 压缩完成统计
# ======================================================
# 总耗时计算
end_time=$(date +%s)
total_time=$((end_time - start_time))
total_fmt=$(printf '%02d:%02d:%02d' $(($total_time/3600)) $(($total_time%3600/60)) $(($total_time%60)))

# 计算压缩统计信息
total_compressed_size_human=$(printf '%.2fGB' $(echo "$total_compressed_size / 1024 / 1024" | bc -l))
saved_size=$((total_source_size - total_compressed_size))
saved_size_human=$(printf '%.2fGB' $(echo "$saved_size / 1024 / 1024" | bc -l))

if [ $total_source_size -gt 0 ]; then
  compression_ratio=$(printf '%.1f%%' $(echo "($total_source_size - $total_compressed_size) * 100 / $total_source_size" | bc -l))
else
  compression_ratio="0.0%"
fi

# 显示统计信息
echo -e "\033[H\033[2J"  # 清屏
echo "=========================================="
echo "🎉 所有视频压缩完成!"
echo "------------------------------------------"
echo "📊 总文件数: $file_count"
echo "⏱️ 总耗时: $total_fmt"
echo "💾 源文件总大小: $total_source_size_human"
echo "💾 压缩后总大小: $total_compressed_size_human"
echo "💰 节约空间: $saved_size_human"
echo "📉 压缩比: $compression_ratio"
if [ $total_estimated_time -gt 0 ]; then
  accuracy=$((total_time * 100 / total_estimated_time))
  echo "📈 预估准确率: $accuracy%"
fi
echo "=========================================="

# ======================================================
# 日志和Markdown更新
# ======================================================
# 记录到日志
if [ $total_estimated_time -gt 0 ]; then
  echo "[统计] 总文件数: $file_count, 总耗时: $total_fmt, 预估准确率: $accuracy%" | tee -a "$log_file"
else
  echo "[统计] 总文件数: $file_count, 总耗时: $total_fmt" | tee -a "$log_file"
fi

echo "🎉 所有视频压缩完成，总耗时：$total_fmt" | tee -a "$log_file"
echo "" >> "$md_file"
echo "> ✅ 视频全部压缩完成，总耗时：$total_fmt，生成于 $(date '+%Y-%m-%d %H:%M:%S')" >> "$md_file"

# 确保Markdown文件已更新
if [ -f "$md_file" ]; then
  echo "✅ 课程视频清单.md 已成功更新" | tee -a "$log_file"
else
  echo "❌ 课程视频清单.md 不存在，正在创建..." | tee -a "$log_file"
  echo "# 🎬 课程视频清单" > "$md_file"
  echo "🗓️ 生成时间：$(date '+%Y-%m-%d %H:%M:%S')" >> "$md_file"
  echo "" >> "$md_file"
  echo "| 课程名称 | 原路径 | 原大小 | 时长 | 压缩后大小 | 耗时 | 压缩后文件 | 节省空间 | 压缩比 |" >> "$md_file"
  echo "|-----------|--------|---------|------|-------------|------|--------------|----------|--------|" >> "$md_file"
  echo "✅ 已创建课程视频清单.md" | tee -a "$log_file"
fi

# ======================================================
# 日志清理
# ======================================================
# 不保存日志文件，删除所有日志
 echo "🗑️ 正在删除所有日志文件..." | tee -a "$log_file"
rm -f compress_log_*.txt
 echo "✅ 已删除所有日志文件" | tee -a "$log_file"

# ======================================================
# 完成通知
# ======================================================
say "恭喜你，所有视频压缩完成"
osascript -e 'display notification "所有视频压缩完成" with title "压缩完成提示"'
