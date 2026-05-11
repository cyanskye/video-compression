#!/usr/bin/env python3
"""Local-first video compression agent.

The agent keeps all video work on this machine. It uses ffprobe/ffmpeg for
analysis, previews, compression, and progress events.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v"}
PREVIEW_FILTER = "scale=1920:1080:force_original_aspect_ratio=decrease"
OUTPUT_FILTER = "scale=1920:1080:force_original_aspect_ratio=decrease"

PRESETS = [
    {"key": "quality", "crf": 18, "name": "近原画", "desc": "小字、课件、录屏最稳，文件较大。", "ratio": 0.65},
    {"key": "course", "crf": 20, "name": "课程清晰", "desc": "推荐给课程视频，优先保住文字和人脸。", "ratio": 0.54},
    {"key": "balanced", "crf": 23, "name": "均衡压缩", "desc": "适合普通真人视频；小字多时可能显糊。", "ratio": 0.42},
    {"key": "compact", "crf": 28, "name": "强力省空间", "desc": "明显变小，也更容易出现压缩感。", "ratio": 0.28},
]


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    relpath: Path
    size_bytes: int
    duration: float
    width: int
    height: int
    bit_rate: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "path": str(self.path),
            "relpath": str(self.relpath),
            "name": self.path.name,
            "size_bytes": self.size_bytes,
            "size": format_bytes(self.size_bytes),
            "duration": self.duration,
            "duration_label": format_duration(self.duration),
            "width": self.width,
            "height": self.height,
            "bit_rate": self.bit_rate,
            "bit_rate_label": format_bitrate(self.bit_rate),
        }


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(_missing_tool_message(name))


def _missing_tool_message(name: str) -> str:
    return (
        f"未找到依赖：{name}\n"
        "请先安装 ffmpeg / ffprobe：\n"
        "  - macOS (Homebrew): brew install ffmpeg\n"
        "  - Ubuntu/Debian: sudo apt update && sudo apt install -y ffmpeg\n"
        "  - Fedora: sudo dnf install -y ffmpeg"
    )


def run_doctor() -> Dict[str, object]:
    checks = []
    python_ok = sys.version_info >= (3, 9)
    checks.append(
        {
            "name": "python3",
            "ok": python_ok,
            "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }
    )
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        checks.append({"name": tool, "ok": bool(path), "detail": path or "未安装"})

    ok = all(item["ok"] for item in checks)
    return {"ok": ok, "checks": checks}


def format_bytes(size: int) -> str:
    if size < 0:
        return "-" + format_bytes(abs(size))
    if size >= 1024**3:
        return f"{size / 1024**3:.2f} GB"
    if size >= 1024**2:
        return f"{size / 1024**2:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def format_bitrate(bit_rate: int) -> str:
    if bit_rate <= 0:
        return "未知"
    if bit_rate >= 1_000_000:
        return f"{bit_rate / 1_000_000:.1f} Mbps"
    return f"{bit_rate / 1_000:.0f} Kbps"


def collect_videos(target: os.PathLike[str] | str) -> Tuple[Path, List[Path]]:
    target_path = Path(target).expanduser().resolve()
    if target_path.is_file():
        if target_path.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError(f"不是支持的视频文件：{target_path}")
        return target_path.parent, [target_path]
    if not target_path.is_dir():
        raise FileNotFoundError(f"路径不存在：{target_path}")

    videos: List[Path] = []
    for path in sorted(target_path.rglob("*"), key=lambda p: (len(p.relative_to(target_path).parts), str(p.relative_to(target_path)))):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        rel_parts = path.relative_to(target_path).parts
        if "compressed" in rel_parts:
            continue
        videos.append(path.resolve())
    return target_path, videos


def _ffprobe_json(path: Path) -> Dict[str, object]:
    require_tool("ffprobe")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"ffprobe 读取失败：{path}")
    return json.loads(result.stdout or "{}")


def probe_video(base_dir: Path, path: Path) -> VideoInfo:
    data = _ffprobe_json(path)
    fmt = data.get("format", {}) if isinstance(data.get("format"), dict) else {}
    streams = data.get("streams", []) if isinstance(data.get("streams"), list) else []
    video_stream = next((s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"), {})

    def as_int(value: object, default: int = 0) -> int:
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return default

    def as_float(value: object, default: float = 0) -> float:
        try:
            return float(str(value))
        except (TypeError, ValueError):
            return default

    duration = as_float(fmt.get("duration"))
    bit_rate = as_int(fmt.get("bit_rate"))
    return VideoInfo(
        path=path,
        relpath=path.relative_to(base_dir),
        size_bytes=path.stat().st_size,
        duration=duration,
        width=as_int(video_stream.get("width")),
        height=as_int(video_stream.get("height")),
        bit_rate=bit_rate,
    )


def analyze_target(target: os.PathLike[str] | str) -> Tuple[Path, List[VideoInfo], Dict[str, object]]:
    base_dir, paths = collect_videos(target)
    videos = [probe_video(base_dir, path) for path in paths]
    return base_dir, videos, build_analysis(base_dir, videos)


def has_text_risk(video: VideoInfo) -> bool:
    text = f"{video.relpath} {video.path.stem}".lower()
    markers = ["字幕", "文字", "课件", "ppt", "slide", "subtitle", "caption", "screen", "录屏"]
    return any(marker in text for marker in markers)


def has_course_risk(video: VideoInfo) -> bool:
    text = f"{video.relpath} {video.path.stem}".lower()
    markers = ["课", "课程", "lesson", "course", "class", "training", "直播", "回放"]
    return any(marker in text for marker in markers)


def recommend_preset(videos: List[VideoInfo]) -> Dict[str, object]:
    if not videos:
        return {"crf": 23, "preset": "智能均衡", "confidence": "低", "reasons": ["没有找到可分析的视频。"], "risks": []}

    total_duration = sum(v.duration for v in videos if v.duration > 0)
    total_size = sum(v.size_bytes for v in videos)
    avg_height = sum(v.height for v in videos) / len(videos)
    avg_width = sum(v.width for v in videos) / len(videos)
    text_risk = any(has_text_risk(v) for v in videos)
    course_risk = any(has_course_risk(v) for v in videos)
    source_bitrate = int(total_size * 8 / total_duration) if total_duration > 0 else 0

    reasons: List[str] = []
    risks: List[str] = []
    crf = 23
    confidence = "中"

    if text_risk:
        crf = 23
        reasons.append("检测到字幕、课件、录屏或文字相关文件名，优先保护文字清晰度。")
        risks.append("如果画面里有小字号文字，建议预览后再确认。")
    elif course_risk and avg_height >= 1080:
        crf = 20
        confidence = "高"
        reasons.append("检测到课程类长视频，画面通常包含小字、PPT 或画中画，推荐先用课程清晰档。")
        risks.append("CRF 23/28 会更省空间，但小字号文字和截图细节可能明显变糊。")
    elif avg_height <= 720 or avg_width <= 1280:
        crf = 23
        reasons.append("素材分辨率不高，过度压缩更容易显糊。")
    elif source_bitrate >= 12_000_000:
        crf = 28
        confidence = "高"
        reasons.append("源视频码率较高，通常有较大压缩空间。")
    elif source_bitrate >= 6_000_000:
        crf = 23
        confidence = "高"
        reasons.append("源视频码率适中，推荐用均衡档保留课程观感。")
    else:
        crf = 23
        reasons.append("源视频码率不高，继续压小可能更容易出现块状感。")

    if any(v.height >= 1440 for v in videos):
        reasons.append("发现高分辨率视频，输出会限制在 1080p 内，适合课程平台分发。")
    if any(v.duration > 1800 for v in videos):
        risks.append("存在长视频，建议保持终端或浏览器窗口打开观察进度。")

    preset_name = next(p["name"] for p in PRESETS if p["crf"] == crf)
    return {"crf": crf, "preset": preset_name, "confidence": confidence, "reasons": reasons, "risks": risks}


def estimate_sizes(videos: List[VideoInfo]) -> Dict[str, int]:
    total_source = sum(v.size_bytes for v in videos)
    total_duration = sum(max(v.duration, 0) for v in videos)
    audio_floor = int(total_duration * 160_000 / 8) if total_duration > 0 else 0
    estimates: Dict[str, int] = {}
    for preset in PRESETS:
        estimated = int(total_source * float(preset["ratio"]))
        with_floor = max(estimated, audio_floor)
        estimates[str(preset["crf"])] = min(total_source, with_floor) if total_source > 0 else with_floor
    return estimates


def build_analysis(base_dir: Path, videos: List[VideoInfo]) -> Dict[str, object]:
    total_size = sum(v.size_bytes for v in videos)
    total_duration = sum(v.duration for v in videos)
    recommendation = recommend_preset(videos)
    size_estimates = estimate_sizes(videos)
    return {
        "base_dir": str(base_dir),
        "video_count": len(videos),
        "total_size_bytes": total_size,
        "total_size": format_bytes(total_size),
        "total_duration": total_duration,
        "total_duration_label": format_duration(total_duration),
        "presets": PRESETS,
        "recommendation": recommendation,
        "size_estimates": size_estimates,
        "size_estimate_labels": {crf: format_bytes(size) for crf, size in size_estimates.items()},
        "videos": [v.to_dict() for v in videos],
    }


def pick_preview_sources(videos: List[VideoInfo], limit: int = 3) -> List[Tuple[VideoInfo, float]]:
    ranked = sorted(videos, key=lambda v: (has_text_risk(v), v.size_bytes), reverse=True)
    selected = ranked[:limit]
    picks: List[Tuple[VideoInfo, float]] = []
    for video in selected:
        if video.duration <= 0:
            timestamp = 0
        elif video.duration < 12:
            timestamp = max(0.5, video.duration / 2)
        else:
            timestamp = min(video.duration * 0.55, video.duration - 4)
        picks.append((video, timestamp))
    return picks


def _image_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _run_ffmpeg(cmd: List[str]) -> None:
    require_tool("ffmpeg")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg 执行失败")


def generate_previews(base_dir: Path, videos: List[VideoInfo], max_items: int = 3) -> Dict[str, object]:
    tmp_dir = Path(tempfile.mkdtemp(prefix="video_agent_preview_"))
    frames: List[Dict[str, object]] = []
    try:
        for index, (video, timestamp) in enumerate(pick_preview_sources(videos, max_items)):
            original = tmp_dir / f"{index}_original.jpg"
            _run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    str(timestamp),
                    "-i",
                    str(video.path),
                    "-frames:v",
                    "1",
                    "-vf",
                    PREVIEW_FILTER,
                    "-q:v",
                    "2",
                    str(original),
                ]
            )

            variants: Dict[str, str] = {}
            for preset in PRESETS:
                crf = str(preset["crf"])
                sample = tmp_dir / f"{index}_crf{crf}.mp4"
                frame = tmp_dir / f"{index}_crf{crf}.jpg"
                start = max(0, timestamp - 1.0)
                _run_ffmpeg(
                    [
                        "ffmpeg",
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-ss",
                        str(start),
                        "-i",
                        str(video.path),
                        "-t",
                        "2",
                        "-vf",
                        PREVIEW_FILTER,
                        "-an",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        crf,
                        str(sample),
                    ]
                )
                _run_ffmpeg(
                    [
                        "ffmpeg",
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-ss",
                        "1",
                        "-i",
                        str(sample),
                        "-frames:v",
                        "1",
                        "-vf",
                        PREVIEW_FILTER,
                        "-q:v",
                        "2",
                        str(frame),
                    ]
                )
                variants[crf] = _image_data_uri(frame)

            frames.append(
                {
                    "video": video.to_dict(),
                    "timestamp": timestamp,
                    "timestamp_label": format_duration(timestamp),
                    "original": _image_data_uri(original),
                    "variants": variants,
                }
            )
        return {"frames": frames, "presets": PRESETS}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def output_path_for(base_dir: Path, source: Path) -> Path:
    base = Path(base_dir)
    src = Path(source)
    rel = src.relative_to(base)
    return base / "compressed" / rel.parent / f"{src.stem}_1080p.mp4"


def parse_out_time(value: str) -> float:
    try:
        hours, minutes, seconds = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (ValueError, AttributeError):
        return 0.0


def compress_video(base_dir: Path, video: VideoInfo, crf: int, emit: Callable[[Dict[str, object]], None]) -> Optional[Dict[str, object]]:
    return compress_video_with_cancel(base_dir, video, crf, emit, None)


def compress_video_with_cancel(
    base_dir: Path,
    video: VideoInfo,
    crf: int,
    emit: Callable[[Dict[str, object]], None],
    cancel_event: Optional[threading.Event],
) -> Optional[Dict[str, object]]:
    output = output_path_for(base_dir, video.path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if cancel_event is not None and cancel_event.is_set():
        emit({"type": "cancelled", "file": str(video.relpath), "message": "已停止，未开始下一个文件。"})
        return None
    start_time = time.time()
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-i",
        str(video.path),
        "-vf",
        OUTPUT_FILTER,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(crf),
        "-threads",
        "0",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ac",
        "1",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        str(output),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    progress = 0
    for line in proc.stdout:
        if cancel_event is not None and cancel_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            if output.exists():
                output.unlink()
            emit({"type": "cancelled", "file": str(video.relpath), "message": "已停止当前压缩，未保留半成品。"})
            return None
        key, _, value = line.strip().partition("=")
        if key == "out_time_ms":
            try:
                current = int(value) / 1_000_000
            except ValueError:
                current = 0
        elif key == "out_time":
            current = parse_out_time(value)
        else:
            continue
        if video.duration > 0:
            next_progress = min(100, int(current * 100 / video.duration))
            if next_progress != progress:
                progress = next_progress
                emit({"type": "file_progress", "file": str(video.relpath), "progress": progress})

    stderr = proc.stderr.read() if proc.stderr else ""
    return_code = proc.wait()
    if return_code != 0 or not output.exists() or output.stat().st_size == 0:
        emit({"type": "file_failed", "file": str(video.relpath), "error": stderr.strip() or "ffmpeg 执行失败"})
        return None

    elapsed = int(time.time() - start_time)
    result = {
        "source": str(video.relpath),
        "output": str(output.relative_to(base_dir)),
        "source_size": video.size_bytes,
        "output_size": output.stat().st_size,
        "duration": video.duration,
        "elapsed": elapsed,
        "saved": video.size_bytes - output.stat().st_size,
    }
    emit({"type": "file_done", "file": str(video.relpath), "output": result["output"], "progress": 100})
    return result


def write_report(base_dir: Path, crf: int, results: List[Dict[str, object]], failures: List[Dict[str, object]]) -> Path:
    output_dir = base_dir / "compressed"
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / "课程视频清单.md"
    total_source = sum(int(r["source_size"]) for r in results)
    total_output = sum(int(r["output_size"]) for r in results)
    lines = [
        "# 课程视频清单",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"压缩档位：CRF {crf}",
        "",
        "| 课程名称 | 原路径 | 原大小 | 时长 | 压缩后大小 | 耗时 | 压缩后文件 | 节省空间 | 压缩比 |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|",
    ]
    for result in results:
        source_size = int(result["source_size"])
        output_size = int(result["output_size"])
        saved = source_size - output_size
        ratio = (saved * 100 / source_size) if source_size else 0
        lines.append(
            "| {name} | {source} | {source_size} | {duration} | {output_size} | {elapsed} | {output} | {saved} | {ratio:.1f}% |".format(
                name=Path(str(result["source"])).stem,
                source=result["source"],
                source_size=format_bytes(source_size),
                duration=format_duration(float(result["duration"])),
                output_size=format_bytes(output_size),
                elapsed=format_duration(float(result["elapsed"])),
                output=result["output"],
                saved=format_bytes(saved),
                ratio=ratio,
            )
        )
    if failures:
        lines.extend(["", "## 失败文件"])
        for failure in failures:
            lines.append(f"- `{failure.get('file')}`：{failure.get('error')}")
    if results:
        saved = total_source - total_output
        ratio = (saved * 100 / total_source) if total_source else 0
        lines.extend(
            [
                "",
                f"> 总计：{len(results)} 个文件，{format_bytes(total_source)} → {format_bytes(total_output)}，节省 {format_bytes(saved)}（{ratio:.1f}%）。",
            ]
        )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def compress_directory(
    target: os.PathLike[str] | str,
    crf: int,
    no_confirm: bool = False,
    emit: Optional[Callable[[Dict[str, object]], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Dict[str, object]:
    require_tool("ffmpeg")
    base_dir, videos, analysis = analyze_target(target)
    if not videos:
        raise RuntimeError("没有找到可压缩的视频文件。")

    if not no_confirm:
        print(f"找到 {len(videos)} 个视频，总大小 {analysis['total_size']}，推荐 {analysis['recommendation']['preset']}。")
        answer = input(f"是否开始压缩 CRF {crf}？(y/n): ").strip().lower()
        if answer not in {"y", "yes"}:
            return {"cancelled": True, "results": [], "failures": []}

    output_dir = base_dir / "compressed"
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_file = output_dir / "compress_progress.txt"
    completed = set(progress_file.read_text(encoding="utf-8").splitlines()) if progress_file.exists() else set()

    results: List[Dict[str, object]] = []
    failures: List[Dict[str, object]] = []

    def send(event: Dict[str, object]) -> None:
        if emit:
            emit(event)

    send({"type": "started", "total": len(videos), "crf": crf})
    for index, video in enumerate(videos, start=1):
        if cancel_event is not None and cancel_event.is_set():
            send({"type": "cancelled", "message": "已停止压缩。"})
            return {"cancelled": True, "results": results, "failures": failures}
        output = output_path_for(base_dir, video.path)
        if str(video.relpath) in completed and output.exists() and output.stat().st_size > 0:
            send({"type": "file_skipped", "file": str(video.relpath), "index": index, "total": len(videos)})
            continue
        send({"type": "file_started", "file": str(video.relpath), "index": index, "total": len(videos)})
        result = compress_video_with_cancel(base_dir, video, crf, send, cancel_event)
        if cancel_event is not None and cancel_event.is_set():
            return {"cancelled": True, "results": results, "failures": failures}
        if result:
            results.append(result)
            with progress_file.open("a", encoding="utf-8") as handle:
                handle.write(str(video.relpath) + "\n")
        else:
            failures.append({"file": str(video.relpath), "error": "压缩失败，请查看事件或终端输出。"})

    existing_report = output_dir / "课程视频清单.md"
    if results or failures or not existing_report.exists():
        report = write_report(base_dir, crf, results, failures)
    else:
        report = existing_report
    final = {"type": "done", "results": results, "failures": failures, "report": str(report)}
    send(final)
    return {"cancelled": False, "results": results, "failures": failures, "report": report}


class AgentTask:
    def __init__(self, target: str):
        self.target = target
        self.events: "queue.Queue[Dict[str, object]]" = queue.Queue()
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.cancel_event = threading.Event()

    def start(self, crf: int) -> bool:
        if self.running:
            return False
        self.cancel_event.clear()
        self.running = True

        def worker() -> None:
            try:
                compress_directory(
                    self.target,
                    crf=crf,
                    no_confirm=True,
                    emit=self.events.put,
                    cancel_event=self.cancel_event,
                )
            except Exception as exc:  # pragma: no cover - surfaced through browser
                self.events.put({"type": "failed", "error": str(exc)})
            finally:
                self.running = False

        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()
        return True

    def cancel(self) -> bool:
        self.cancel_event.set()
        if not self.running:
            self.events.put({"type": "cancelled", "message": "当前没有正在执行的压缩任务。"})
        return True


class AgentState:
    def __init__(self, target: str):
        self.target = str(Path(target).expanduser().resolve())
        self.base_dir, self.videos, self.analysis = analyze_target(self.target)
        self.preview_cache: Optional[Dict[str, object]] = None
        self.preview_error: Optional[str] = None
        self.task = AgentTask(self.target)


def json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def build_app_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>本地视频压缩 Agent</title>
<style>
:root{--bg:#f5f6f7;--panel:#fff;--text:#17201c;--muted:#6c7671;--line:#d8dfdb;--accent:#12845a;--danger:#b8323b;--soft:#edf5f1}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif;overflow:hidden}
header{height:56px;padding:0 20px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;background:#fff}
h1{font-size:18px;margin:0}.privacy{font-size:13px;color:var(--muted)}
main{height:calc(100vh - 64px);padding:12px;display:grid;grid-template-columns:1fr 280px;gap:12px;min-height:0}
.stage{background:#111;border-radius:8px;overflow:hidden;display:grid;grid-template-rows:auto 1fr auto;min-width:0;min-height:0}
.stage-top{height:48px;display:grid;grid-template-columns:1fr auto auto;gap:10px;align-items:center;padding:0 12px;background:#fff;border:1px solid var(--line);border-bottom:0;border-radius:8px 8px 0 0}
.stage-title{font-weight:800}.chips{display:flex;gap:8px;align-items:center}.chip{background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:5px 9px;font-size:13px;color:var(--text);white-space:nowrap}
.view-modes{display:flex;gap:4px;padding:3px;border:1px solid var(--line);border-radius:8px;background:#f4f7f5}.mode-btn{padding:6px 9px;border-radius:6px;background:transparent;color:var(--muted);font-weight:800}.mode-btn.active{background:#fff;color:var(--accent);box-shadow:0 1px 4px rgba(0,0,0,.08)}
.preview{min-height:0;background:#0b0d0c;display:grid;place-items:center}.empty{color:#dbe3df;text-align:center}.empty button{margin-top:12px}
.frame{width:100%;height:100%;display:grid;grid-template-rows:auto 1fr;background:#111}.frame-head{padding:8px 12px;color:#dfe8e2;font-size:13px;background:#171d1a}.compare-slider{--split:50%;position:relative;min-height:0;overflow:hidden;background:#111}.compare-slider img{display:block;width:100%;height:100%;object-fit:contain}.compare-slider .compressed{position:absolute;inset:0;clip-path:inset(0 calc(100% - var(--split)) 0 0);border-right:2px solid #12d28b}.compare-slider input{position:absolute;left:16px;right:16px;bottom:14px;width:calc(100% - 32px)}.badge{position:absolute;top:12px;padding:5px 8px;border-radius:6px;background:rgba(0,0,0,.7);color:#fff;font-size:12px}.badge.left{left:12px}.badge.right{right:12px}.zoom-compare{display:grid;grid-template-columns:1fr 1fr;gap:1px;height:100%;background:#28312d}.zoom-pane{position:relative;overflow:hidden;background:#111}.zoom-pane img{width:100%;height:100%;object-fit:cover;transform:scale(1.65)}.diff-view{position:relative;width:100%;height:100%;background:#050606;display:grid;place-items:center}.diff-view canvas{width:100%;height:100%;object-fit:contain}.diff-view .badge{top:12px;left:12px;right:auto}
.filmstrip{height:54px;display:flex;gap:8px;align-items:center;padding:8px;background:#fff;border:1px solid var(--line);border-top:0;border-radius:0 0 8px 8px;overflow:auto}.frame-tabs{display:flex}.frame-tab{border:1px solid var(--line);border-radius:7px;background:#eef3f0;color:var(--text);padding:8px 10px;white-space:nowrap;font-weight:700}.frame-tab.active{background:var(--accent);color:#fff}
.controls{background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px;display:flex;flex-direction:column;gap:12px;min-height:0}.label{font-size:12px;color:var(--muted)}.path{font-size:12px;line-height:1.25;word-break:break-all}.stats{display:grid;grid-template-columns:1fr 1fr;gap:8px}.stat b{font-size:20px}.presets{display:grid;grid-template-columns:1fr 1fr;gap:8px}.preset{position:relative;border:1px solid var(--line);border-radius:8px;background:#fff;padding:10px 9px 24px;cursor:pointer;min-height:74px}.preset.active{border-color:var(--accent);box-shadow:0 0 0 2px rgba(18,132,90,.14)}.preset b{display:block;color:var(--accent);font-size:15px}.preset span{display:block;margin-top:4px;font-size:12px;color:var(--muted)}.preset em{position:absolute;left:9px;bottom:7px;font-style:normal;font-size:11px;color:#8a948f}button{border:0;border-radius:7px;padding:10px 12px;background:var(--accent);color:#fff;font-weight:800;cursor:pointer}button.secondary{background:#e7eeea;color:var(--text)}button.danger{background:#d9848c}button:disabled{opacity:.55;cursor:not-allowed}.buttons{display:grid;gap:8px;margin-top:auto}.run{display:grid;grid-template-columns:1fr 1fr;gap:8px}.log{height:34px;overflow:auto;background:#111815;border-radius:8px;padding:8px;color:#dbe7e1;font-size:12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}details{border:1px solid var(--line);border-radius:8px;padding:9px;background:#fbfcfb}summary{font-weight:800;cursor:pointer}.why-body p{margin:8px 0;line-height:1.45}
@media(max-width:980px){body{overflow:auto}main{height:auto;grid-template-columns:1fr}.stage{min-height:520px}.controls{grid-template-rows:auto}}
</style>
</head>
<body>
<header><h1>本地视频压缩 Agent</h1><div class="privacy">视频不上传，只在本机分析和压缩</div></header>
<main>
  <section class="stage">
    <div class="stage-top">
      <div><span class="stage-title">预览舞台</span> <span class="label" id="selected-label"></span></div>
      <div class="view-modes">
        <button class="mode-btn" data-mode="split">滑杆</button>
        <button class="mode-btn" data-mode="zoom">放大</button>
        <button class="mode-btn" data-mode="diff">差异</button>
      </div>
      <div class="chips"><span class="chip" id="rec-title"></span><span class="chip" id="summary"></span></div>
    </div>
    <div id="previews" class="preview"><div class="empty">先生成预览，再判断画质。<br><button id="load-previews-hero">生成预览</button></div></div>
    <div class="filmstrip"><div id="frame-tabs" class="frame-tabs"></div></div>
  </section>
  <aside class="controls">
    <div><div class="label">目录</div><div id="base" class="path"></div></div>
    <div class="stats"><div class="stat"><div class="label">视频</div><b id="count">-</b></div><div class="stat"><div class="label">推荐</div><b id="rec-short">-</b></div></div>
    <div><div class="label">清晰度</div><div class="presets" id="presets"></div></div>
    <details id="why-panel"><summary>为什么这样推荐</summary><div class="why-body"><div id="rec-reasons"></div><div id="risks"></div></div></details>
    <div class="buttons">
      <button id="load-previews">重新生成</button>
      <button class="secondary" id="select-quality">更清晰：CRF 18</button>
      <div class="run"><button id="start">开始压缩</button><button id="cancel" class="danger" disabled>停止压缩</button></div>
      <div class="log" id="log"></div>
    </div>
  </aside>
</main>
<script>
let analysis=null, selectedCrf=23, previewData=null, activeFrame=0, viewMode="zoom";
const $=id=>document.getElementById(id);
function log(msg){const el=$("log");el.innerHTML+=`<div>${new Date().toLocaleTimeString()} ${msg}</div>`;el.scrollTop=el.scrollHeight}
function currentPreset(){
  return analysis.presets.find(p=>p.crf===selectedCrf) || analysis.presets[0];
}
function renderSelectedLabels(){
  const preset=currentPreset();
  $("rec-title").textContent=`推荐 ${analysis.recommendation.preset}`;
  $("rec-short").textContent=analysis.recommendation.preset;
  $("selected-label").textContent=`当前：${preset.name}`;
  $("select-quality").textContent=selectedCrf===18?"已是最清晰":"切到最清晰";
}
function renderAnalysis(data){
  analysis=data; selectedCrf=data.recommendation.crf;
  $("base").textContent=data.base_dir; $("count").textContent=data.video_count; $("summary").textContent=`${data.total_size} · ${data.total_duration_label}`;
  $("rec-reasons").innerHTML=data.recommendation.reasons.map(x=>`<p>${x}</p>`).join("");
  $("risks").innerHTML=(data.recommendation.risks.length?data.recommendation.risks:["暂无明显风险，仍建议看一眼预览。"]).map(x=>`<p>${x}</p>`).join("");
  $("presets").innerHTML=data.presets.map(p=>`<div class="preset ${p.crf===selectedCrf?"active":""}" data-crf="${p.crf}"><b>${p.name}</b><span>${data.size_estimate_labels[p.crf]}</span><em>CRF ${p.crf}</em></div>`).join("");
  document.querySelectorAll(".preset").forEach(el=>el.onclick=()=>selectCrf(Number(el.dataset.crf)));
  renderSelectedLabels();
}
function selectCrf(crf){
  selectedCrf=crf;
  document.querySelectorAll(".preset").forEach(el=>el.classList.toggle("active",Number(el.dataset.crf)===selectedCrf));
  renderSelectedLabels();
  if(previewData) renderPreviews(previewData);
}
function setMode(mode){
  viewMode=mode;
  document.querySelectorAll(".mode-btn").forEach(btn=>btn.classList.toggle("active",btn.dataset.mode===viewMode));
  if(previewData) renderPreviews(previewData);
}
function drawDiff(originalSrc, compressedSrc){
  const canvas=$("diff-canvas");
  if(!canvas) return;
  const ctx=canvas.getContext("2d");
  const original=new Image();
  const compressed=new Image();
  let loaded=0;
  const done=()=>{
    loaded+=1;
    if(loaded<2) return;
    const w=Math.min(1280, original.naturalWidth || compressed.naturalWidth);
    const h=Math.round(w*((original.naturalHeight || compressed.naturalHeight)/(original.naturalWidth || compressed.naturalWidth)));
    canvas.width=w; canvas.height=h;
    const offA=document.createElement("canvas"), offB=document.createElement("canvas");
    offA.width=offB.width=w; offA.height=offB.height=h;
    const a=offA.getContext("2d"), b=offB.getContext("2d");
    a.drawImage(original,0,0,w,h); b.drawImage(compressed,0,0,w,h);
    const imgA=a.getImageData(0,0,w,h), imgB=b.getImageData(0,0,w,h), out=ctx.createImageData(w,h);
    for(let i=0;i<imgA.data.length;i+=4){
      const d=(Math.abs(imgA.data[i]-imgB.data[i])+Math.abs(imgA.data[i+1]-imgB.data[i+1])+Math.abs(imgA.data[i+2]-imgB.data[i+2]))/3;
      const v=Math.min(255, d*14);
      out.data[i]=v; out.data[i+1]=v; out.data[i+2]=v; out.data[i+3]=255;
    }
    ctx.putImageData(out,0,0);
  };
  original.onload=done; compressed.onload=done;
  original.src=originalSrc; compressed.src=compressedSrc;
}
function renderPreviews(data){
  if(!data.frames.length){$("frame-tabs").innerHTML="";$("previews").innerHTML="<p class='label'>没有可用预览。</p>";return}
  if(activeFrame>=data.frames.length) activeFrame=0;
  $("frame-tabs").innerHTML=data.frames.map((f,i)=>`<button class="frame-tab ${i===activeFrame?"active":""}" onclick="activeFrame=${i};renderPreviews(previewData)">片段 ${i+1}</button>`).join("");
  const f=data.frames[activeFrame];
  const compressed=f.variants[selectedCrf]||"";
  if(viewMode==="zoom"){
    $("previews").innerHTML=`<div class="frame"><div class="frame-head">${f.video.relpath} · ${f.timestamp_label} · ${currentPreset().name}</div><div class="zoom-compare"><div class="zoom-pane"><img src="${compressed}" alt="压缩"><span class="badge left">压缩预览</span></div><div class="zoom-pane"><img src="${f.original}" alt="原画"><span class="badge right">原画</span></div></div></div>`;
  }else if(viewMode==="diff"){
    $("previews").innerHTML=`<div class="frame"><div class="frame-head">${f.video.relpath} · ${f.timestamp_label} · ${currentPreset().name}</div><div class="diff-view"><canvas id="diff-canvas"></canvas><span class="badge">亮处就是差异</span></div></div>`;
    drawDiff(f.original, compressed);
  }else{
    $("previews").innerHTML=`<div class="frame"><div class="frame-head">${f.video.relpath} · ${f.timestamp_label} · ${currentPreset().name}</div><div class="compare-slider"><img src="${f.original}" alt="原画"><img class="compressed" src="${compressed}" alt="压缩"><span class="badge left">压缩预览</span><span class="badge right">原画</span><input type="range" min="0" max="100" value="50" oninput="this.parentElement.style.setProperty('--split',this.value+'%')"></div></div>`;
  }
}
async function init(){const r=await fetch("/api/analysis");renderAnalysis(await r.json())}
async function loadPreviews(){ $("previews").innerHTML="<div class='empty'>正在生成真实预览...</div>"; const r=await fetch("/api/previews"); const data=await r.json(); if(data.error){$("previews").textContent=data.error;return} previewData=data; renderPreviews(data); }
$("load-previews").onclick=loadPreviews;
$("load-previews-hero").onclick=loadPreviews;
$("select-quality").onclick=()=>selectCrf(18);
document.querySelectorAll(".mode-btn").forEach(btn=>btn.onclick=()=>setMode(btn.dataset.mode));
setMode(viewMode);
$("cancel").onclick=async()=>{ $("cancel").disabled=true; log("正在请求停止压缩..."); await fetch("/api/cancel",{method:"POST"}); };
$("start").onclick=async()=>{ $("start").disabled=true; $("cancel").disabled=false; await fetch("/api/start?crf="+selectedCrf,{method:"POST"}); const es=new EventSource("/api/events"); es.onmessage=e=>{const ev=JSON.parse(e.data); if(ev.type==="done"){log(`完成，报告：${ev.report}`); es.close(); $("start").disabled=false; $("cancel").disabled=true}else if(ev.type==="cancelled"){log(ev.message||"已停止压缩"); es.close(); $("start").disabled=false; $("cancel").disabled=true}else if(ev.type==="failed"){log("失败："+ev.error); es.close(); $("start").disabled=false; $("cancel").disabled=true}else if(ev.type==="file_progress"){log(`${ev.file} ${ev.progress}%`)}else if(ev.file){log(`${ev.type} ${ev.file}`)}else{log(ev.type)}}};
init().catch(e=>log("加载失败："+e.message));
</script>
</body>
</html>"""


def make_handler(state: AgentState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = build_app_html().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            elif parsed.path == "/api/analysis":
                json_response(self, state.analysis)
            elif parsed.path == "/api/previews":
                if state.preview_cache is None and state.preview_error is None:
                    try:
                        state.preview_cache = generate_previews(state.base_dir, state.videos)
                    except Exception as exc:
                        state.preview_error = str(exc)
                if state.preview_error:
                    json_response(self, {"error": state.preview_error}, status=500)
                else:
                    json_response(self, state.preview_cache)
            elif parsed.path == "/api/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                while state.task.running or not state.task.events.empty():
                    try:
                        event = state.task.events.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    payload = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    if event.get("type") in {"done", "failed", "cancelled"}:
                        break
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/cancel":
                cancelled = state.task.cancel()
                json_response(self, {"cancelled": cancelled})
                return
            if parsed.path != "/api/start":
                self.send_error(404)
                return
            crf = int(parse_qs(parsed.query).get("crf", [state.analysis["recommendation"]["crf"]])[0])
            if crf not in [p["crf"] for p in PRESETS]:
                json_response(self, {"error": f"不支持的 CRF：{crf}"}, status=400)
                return
            started = state.task.start(crf)
            json_response(self, {"started": started, "crf": crf})

    return Handler


def run_app(target: str, open_browser: bool = True) -> None:
    state = AgentState(target)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"本地视频压缩 Agent：{url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已关闭本地 Agent。")


def print_event(event: Dict[str, object]) -> None:
    kind = event.get("type")
    if kind == "started":
        print(f"开始压缩：{event.get('total')} 个视频，CRF {event.get('crf')}")
    elif kind == "file_started":
        print(f"[{event.get('index')}/{event.get('total')}] {event.get('file')}")
    elif kind == "file_progress":
        print(f"\r  进度 {event.get('progress')}%", end="", flush=True)
    elif kind == "file_done":
        print(f"\n  完成：{event.get('output')}")
    elif kind == "file_failed":
        print(f"\n  失败：{event.get('file')} {event.get('error')}")
    elif kind == "done":
        print(f"全部结束。报告：{event.get('report')}")


def command_analyze(args: argparse.Namespace) -> int:
    _, _, analysis = analyze_target(args.target)
    print(json.dumps(analysis, ensure_ascii=False, indent=2))
    return 0


def command_preview(args: argparse.Namespace) -> int:
    base_dir, videos, _ = analyze_target(args.target)
    previews = generate_previews(base_dir, videos)
    print(json.dumps(previews, ensure_ascii=False) if args.json else f"已生成 {len(previews['frames'])} 组预览帧。")
    return 0


def command_compress(args: argparse.Namespace) -> int:
    compress_directory(args.target, crf=args.crf, no_confirm=args.no_confirm, emit=print_event)
    print()
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    report = run_doctor()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("环境检查：")
        for item in report["checks"]:
            mark = "✅" if item["ok"] else "❌"
            print(f"{mark} {item['name']}: {item['detail']}")
        if report["ok"]:
            print("可运行：依赖已就绪。")
        else:
            print("不可运行：请按提示安装缺失依赖。")
    return 0 if report["ok"] else 1


def command_dry_run(args: argparse.Namespace) -> int:
    base_dir, videos, analysis = analyze_target(args.target)
    output_dir = base_dir / "compressed"
    print("压缩预检（不执行压缩）：")
    print(f"- 输入目录: {base_dir}")
    print(f"- 输出目录: {output_dir}")
    print(f"- 文件数量: {len(videos)}")
    print(f"- 总大小: {analysis['total_size']}")
    print(f"- 总时长: {analysis['total_duration_label']}")
    print(f"- 推荐档位: CRF {analysis['recommendation']['crf']} ({analysis['recommendation']['preset']})")
    print(f"- 本次设定: CRF {args.crf}")
    if videos:
        print("- 示例文件:")
        for item in videos[:5]:
            print(f"  - {item.relpath}")
        if len(videos) > 5:
            print(f"  - ... 其余 {len(videos) - 5} 个")
    return 0


def command_app(args: argparse.Namespace) -> int:
    run_app(args.target, open_browser=not args.no_open)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI-native 本地视频压缩 Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="检查本机运行依赖")
    doctor.add_argument("--json", action="store_true", help="输出 JSON")
    doctor.set_defaults(func=command_doctor)

    analyze = sub.add_parser("analyze", help="分析视频目录并输出 JSON")
    analyze.add_argument("target")
    analyze.set_defaults(func=command_analyze)

    preview = sub.add_parser("preview", help="生成真实压缩预览")
    preview.add_argument("target")
    preview.add_argument("--json", action="store_true", help="输出 base64 JSON")
    preview.set_defaults(func=command_preview)

    compress = sub.add_parser("compress", help="批量压缩视频")
    compress.add_argument("target")
    compress.add_argument("--crf", type=int, default=23)
    compress.add_argument("--no-confirm", action="store_true")
    compress.set_defaults(func=command_compress)

    dry_run = sub.add_parser("dry-run", help="仅预检，不执行压缩")
    dry_run.add_argument("target")
    dry_run.add_argument("--crf", type=int, default=23)
    dry_run.set_defaults(func=command_dry_run)

    app = sub.add_parser("app", help="启动本地浏览器 Agent")
    app.add_argument("target")
    app.add_argument("--no-open", action="store_true")
    app.set_defaults(func=command_app)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
