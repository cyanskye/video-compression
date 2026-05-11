#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

show_help() {
  cat <<'EOF'
用法：
  ./compress-renew.sh [选项] <视频目录或视频文件>

选项：
  --crf <数值>       压缩强度（18/20/23/28，默认 23）
  --yes              跳过确认，直接执行（等同 --no-confirm）
  --no-confirm       跳过确认，直接执行
  --dry-run          仅预检，不压缩
  --doctor           仅检查依赖环境
  -h, --help         显示帮助

示例：
  ./compress-renew.sh /path/to/videos
  ./compress-renew.sh --crf 20 /path/to/videos
  ./compress-renew.sh --dry-run /path/to/videos
  ./compress-renew.sh --doctor
EOF
}

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "❌ 未找到 python3。"
  echo "请先安装 Python 3 后重试。"
  exit 1
fi

if [ $# -eq 0 ]; then
  show_help
  exit 1
fi

MODE="compress"
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --doctor)
      MODE="doctor"
      shift
      ;;
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --yes)
      ARGS+=("--no-confirm")
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

if [ "$MODE" = "doctor" ]; then
  exec "$PYTHON_BIN" "$SCRIPT_DIR/video_agent.py" doctor
fi

if [ "$MODE" = "dry-run" ]; then
  exec "$PYTHON_BIN" "$SCRIPT_DIR/video_agent.py" dry-run "${ARGS[@]}"
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/video_agent.py" compress "${ARGS[@]}"
