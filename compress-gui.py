#!/usr/bin/env python3
# 视频压缩清晰度预览工具（浏览器版）
# 用法: python3 compress-gui.py /path/to/视频目录
# 作者：神奇桑桑 | 麦极科技

import os
import sys
import random
import subprocess
import tempfile
import shutil
import threading
import base64
import webbrowser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

SCRIPT_DIR = Path(__file__).parent
COMPRESS_SCRIPT = SCRIPT_DIR / "compress-renew.sh"
LOGO_PATH = Path("/Users/magicsang666/Documents/ClaudePro/麦极科 logo/01.横版-白字.png")

CRF_PRESETS = [
    {"crf": 18, "label": "高清",   "color": "#4ade80", "glow": "rgba(74,222,128,0.3)",  "tag": "🟢"},
    {"crf": 28, "label": "标准",   "color": "#fbbf24", "glow": "rgba(251,191,36,0.3)",  "tag": "🟡"},
    {"crf": 40, "label": "省空间", "color": "#f87171", "glow": "rgba(248,113,113,0.3)", "tag": "🔴"},
]

PREVIEW_W = 1920
PREVIEW_H = 1080


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def find_videos(directory):
    exts = {".mp4", ".mov", ".mkv"}
    videos = []
    for f in Path(directory).rglob("*"):
        if f.suffix.lower() in exts and "compressed" not in f.parts:
            videos.append(f)
    return sorted(videos)


def get_duration(video_path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0


def get_total_duration(directory):
    return sum(get_duration(v) for v in find_videos(directory))


def get_sample_bitrate(sample_path):
    """用 ffprobe 测实际比特率（bps）"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=bit_rate",
         "-of", "default=noprint_wrappers=1:nokey=1", str(sample_path)],
        capture_output=True, text=True
    )
    try:
        return int(result.stdout.strip())
    except (ValueError, TypeError):
        return 0


def format_size(size_bytes):
    if size_bytes <= 0:
        return "计算中..."
    if size_bytes >= 1024 ** 3:
        return f"~{size_bytes / 1024 ** 3:.1f} GB"
    return f"~{size_bytes / 1024 ** 2:.0f} MB"


def pick_timestamps(duration, count=3):
    margin = duration * 0.05
    start, end = margin, duration - margin
    if end <= start:
        start, end = 0, duration
    step = (end - start) / (count + 1)
    base = [start + step * (i + 1) for i in range(count)]
    jitter = step * 0.3
    return [max(0, min(duration, t + random.uniform(-jitter, jitter))) for t in base]


def extract_original_frame(video_path, timestamp, output_path):
    """直接从原视频取一帧（不压缩）"""
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(timestamp),
         "-i", str(video_path), "-vframes", "1",
         "-vf", f"scale={PREVIEW_W}:{PREVIEW_H}",
         str(output_path)],
        capture_output=True
    )


def extract_frame(video_path, timestamp, crf, output_path, sample_dir):
    """压缩 3 秒样本，取中间帧；返回样本路径（用于比特率测量）"""
    sample_path = Path(sample_dir) / f"sample_crf{crf}.mp4"
    subprocess.run(
        ["ffmpeg", "-y",
         "-ss", str(max(0, timestamp - 1.5)),
         "-i", str(video_path), "-t", "3",
         "-vf", "scale=1920:1080",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
         "-c:a", "aac", "-b:a", "128k",
         str(sample_path)],
        capture_output=True
    )
    subprocess.run(
        ["ffmpeg", "-y", "-ss", "1.5", "-i", str(sample_path),
         "-vframes", "1",
         "-vf", f"scale={PREVIEW_W}:{PREVIEW_H}",
         str(output_path)],
        capture_output=True
    )
    return str(sample_path) if sample_path.exists() else None



def logo_base64():
    if LOGO_PATH.exists():
        with open(LOGO_PATH, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    return ""


def img_to_base64(path):
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    return ""


def generate_previews(video_path, tmp_dir):
    duration = get_duration(video_path)
    n_frames = 2 if duration < 10 else 3
    timestamps = pick_timestamps(duration, n_frames)
    # 每个 CRF + 原版
    total = n_frames * (len(CRF_PRESETS) + 1)
    done = 0
    frames_data = []
    sample_paths = {}

    print(f"\n🎬 正在生成预览帧（共 {total} 张）...")
    for i, ts in enumerate(timestamps):
        row = {}
        # 原版帧
        orig_out = Path(tmp_dir) / f"frame_{i}_orig.png"
        done += 1
        pct = done * 100 // total
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct}%  帧{i+1} 原版   ", end="", flush=True)
        extract_original_frame(video_path, ts, orig_out)
        row["orig"] = str(orig_out) if orig_out.exists() else None

        for preset in CRF_PRESETS:
            crf = preset["crf"]
            out = Path(tmp_dir) / f"frame_{i}_crf{crf}.png"
            done += 1
            pct = done * 100 // total
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r  [{bar}] {pct}%  帧{i+1} CRF{crf} {preset['label']}   ",
                  end="", flush=True)
            sample = extract_frame(video_path, ts, crf, out, tmp_dir)
            if i == 0 and sample:
                sample_paths[crf] = sample
            row[crf] = str(out) if out.exists() else None
        frames_data.append(row)

    print("\n✅ 预览帧生成完毕\n")
    return frames_data, sample_paths, duration
    return frames_data, sample_paths, duration


# ──────────────────────────────────────────────
# HTML 页面生成
# ──────────────────────────────────────────────

def build_html(video_name, frames_data, size_estimates):
    logo_src = logo_base64()
    logo_block = f'<a href="https://magictime999.cn" target="_blank"><img src="{logo_src}" class="logo-img"></a>' if logo_src else ""

    n_frames = len(frames_data)

    # 方案定义（用户友好名称，CRF 只在内部用）
    # "orig" 是特殊 key，不对应 CRF，用于原版参照
    PLANS = [
        {"key": "orig",    "crf": None, "icon": "📹", "name": "原版",      "desc": "未压缩，作为参照",   "color": "#94a3b8", "glow": "rgba(148,163,184,0.25)", "orig": True},
        {"key": "hd",      "crf": 18,   "icon": "🟢", "name": "画质优先",  "desc": "最清晰，文件较大",   "color": "#4ade80", "glow": "rgba(74,222,128,0.35)"},
        {"key": "balance", "crf": 23,   "icon": "🟡", "name": "均衡",       "desc": "画质好，体积小",     "color": "#fbbf24", "glow": "rgba(251,191,36,0.35)", "recommended": True},
        {"key": "small",   "crf": 28,   "icon": "🔴", "name": "体积优先",   "desc": "文件最小，画质略降", "color": "#f87171", "glow": "rgba(248,113,113,0.35)"},
    ]

    # 构建每个方案的帧图片数组（JS 数据）
    frames_js_parts = []

    for plan in PLANS:
        srcs = []
        for i, frame_row in enumerate(frames_data):
            if plan.get("orig"):
                path = frame_row.get("orig")
            else:
                path = frame_row.get(plan["crf"])
            src = img_to_base64(path)
            srcs.append(src if src else "")
        srcs_js = "[" + ",".join(f'"{s}"' for s in srcs) + "]"
        frames_js_parts.append(f'"{plan["key"]}": {srcs_js}')

    frames_js = "{" + ", ".join(frames_js_parts) + "}"

    # 卡片 HTML
    cards_html = ""
    for pi, plan in enumerate(PLANS):
        recommended = plan.get("recommended", False)
        is_orig = plan.get("orig", False)
        rec_badge = '<span class="rec-badge">推荐</span>' if recommended else ""
        if is_orig:
            size = "参照基准"
        else:
            size = format_size(size_estimates.get(plan["crf"], 0))
        # 帧切换 dots
        dots_html = "".join(
            f'<button class="dot{" dot-active" if j == 0 else ""}" onclick="setFrame({j})" aria-label="第{j+1}段画面"></button>'
            for j in range(n_frames)
        )
        # 第一帧预览图
        if frames_data:
            first_path = frames_data[0].get("orig") if is_orig else frames_data[0].get(plan["crf"])
            first_src = img_to_base64(first_path)
        else:
            first_src = ""
        img_tag = f'<img src="{first_src}" class="card-img" id="img-{plan["key"]}" onclick="openLightbox(\'{plan["key"]}\')">' if first_src else '<div class="card-img-err">预览生成失败</div>'
        selected_class = " card-selected" if recommended else ""
        # 原版卡片：只展示，无选择按钮
        if is_orig:
            btn_html = '<div class="orig-label">仅供对比参照</div>'
        else:
            btn_label = "✓ 已选择" if recommended else "选这个"
            btn_class = "btn-select btn-selected" if recommended else "btn-select"
            btn_html = f'<button class="{btn_class}" id="btn-{plan["key"]}" onclick="selectPlan(\'{plan["key"]}\')">{btn_label}</button>'
        cards_html += f"""
<div class="quality-card{selected_class}" id="card-{plan['key']}" style="--card-color:{plan['color']};--card-glow:{plan['glow']}">
  <div class="card-header">
    <span class="card-icon">{plan['icon']}</span>
    <span class="card-name">{plan['name']}</span>
    {rec_badge}
  </div>
  <div class="card-desc">{plan['desc']}</div>
  <div class="card-img-wrap" onclick="openLightbox('{plan['key']}')">
    {img_tag}
  </div>
  <div class="card-dots" id="dots-{plan['key']}">{dots_html}</div>
  <div class="card-size">{size}</div>
  {btn_html}
</div>"""

    # 灯箱图片数据（JS）
    lb_plan_parts = []
    for p in PLANS:
        frame_entries = []
        for i in range(n_frames):
            if p.get("orig"):
                src = img_to_base64(frames_data[i].get("orig")) or ""
            else:
                src = img_to_base64(frames_data[i].get(p["crf"])) or ""
            label = p["name"] + " · 第" + str(i + 1) + "段画面"
            frame_entries.append('{src:"' + src + '", label:"' + label + '"}')
        lb_plan_parts.append('"' + p["key"] + '": [' + ", ".join(frame_entries) + "]")
    lb_imgs_js = "{" + ", ".join(lb_plan_parts) + "}"

    # CRF 映射（内部用，原版不参与）
    crf_map_js = "{" + ", ".join(f'"{p["key"]}": {p["crf"]}' for p in PLANS if not p.get("orig")) + "}"

    # 方案名称映射（底部状态栏显示用，原版不参与）
    name_map_js = "{" + ", ".join(f'"{p["key"]}": "{p["icon"]} {p["name"]}"' for p in PLANS if not p.get("orig")) + "}"

    # 可选方案 key 列表（JS，不含原版）
    selectable_keys_js = '["' + '","'.join(p["key"] for p in PLANS if not p.get("orig")) + '"]'

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>选择压缩方案</title>
<style>
:root {{
  --bg: #080c14; --surface: #0d1525; --border: #1e2d45;
  --text: #e2e8f0; --muted: #64748b;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ height: 100%; }}
body {{
  background: var(--bg);
  background-image: radial-gradient(ellipse at 20% 0%, #0f2040 0%, transparent 55%),
                    radial-gradient(ellipse at 80% 100%, #0a1a30 0%, transparent 55%);
  color: var(--text);
  font-family: -apple-system, "PingFang SC", sans-serif;
  display: flex; flex-direction: column;
  height: 100vh; padding: 14px 20px; gap: 10px; overflow: hidden;
}}

/* 品牌栏 */
.brand-bar {{
  display: flex; align-items: center; justify-content: space-between;
  padding-bottom: 10px; border-bottom: 1px solid var(--border); flex-shrink: 0;
}}
.logo-img {{ height: 28px; opacity: .9; transition: opacity .2s; }}
.logo-img:hover {{ opacity: 1; }}
.brand-right {{ text-align: right; }}
.slogan {{ font-size: .82em; color: var(--muted); }}
.site-link {{ font-size: .72em; color: #3b82f6; text-decoration: none; }}
.site-link:hover {{ text-decoration: underline; }}

/* 标题区 */
.title-area {{ flex-shrink: 0; }}
.page-title {{ font-size: 1.15em; font-weight: 700; margin-bottom: 2px; }}
.page-sub {{ font-size: .8em; color: var(--muted); }}

/* 卡片区 — 撑满剩余高度 */
.cards-row {{
  display: flex; gap: 16px; flex: 1; min-height: 0;
}}
.quality-card {{
  flex: 1; display: flex; flex-direction: column; gap: 10px;
  background: linear-gradient(160deg, color-mix(in srgb, var(--card-color) 8%, var(--surface)), var(--surface));
  border: 2px solid color-mix(in srgb, var(--card-color) 25%, var(--border));
  border-radius: 16px; padding: 16px; cursor: default;
  transition: border-color .2s, box-shadow .2s;
}}
.quality-card.card-selected {{
  border-color: var(--card-color);
  box-shadow: 0 0 28px var(--card-glow), inset 0 0 40px color-mix(in srgb, var(--card-color) 6%, transparent);
}}
.card-header {{
  display: flex; align-items: center; gap: 8px;
}}
.card-icon {{ font-size: 1.3em; }}
.card-name {{ font-size: 1em; font-weight: 700; color: var(--card-color); }}
.rec-badge {{
  font-size: .7em; font-weight: 600; color: var(--card-color);
  background: color-mix(in srgb, var(--card-color) 18%, transparent);
  border: 1px solid color-mix(in srgb, var(--card-color) 45%, transparent);
  padding: 2px 9px; border-radius: 12px; margin-left: auto;
}}
.card-desc {{ font-size: .8em; color: var(--muted); margin-top: -4px; }}

/* 图片区 */
.card-img-wrap {{
  flex: 1; min-height: 0; position: relative; border-radius: 10px; overflow: hidden;
  background: #0a0f1a; cursor: pointer;
}}
.card-img {{
  width: 100%; height: 100%; object-fit: cover; display: block;
  transition: transform .25s, filter .25s;
}}
.card-img-wrap:hover .card-img {{ transform: scale(1.03); filter: brightness(1.08); }}
.card-img-wrap:hover {{ box-shadow: inset 0 0 0 2px var(--card-color); }}
.card-img-err {{
  width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
  color: #f87171; font-size: .85em;
}}

/* 帧切换点 */
.card-dots {{
  display: flex; justify-content: center; gap: 8px;
}}
.dot {{
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--border); border: none; cursor: pointer;
  transition: background .18s, transform .18s;
}}
.dot:hover {{ background: color-mix(in srgb, var(--card-color) 60%, var(--border)); }}
.dot-active {{ background: var(--card-color) !important; transform: scale(1.3); }}

/* 大小估算 */
.card-size {{
  text-align: center; font-size: .88em; font-weight: 600;
  color: var(--card-color);
}}

/* 原版参照标签（无按钮） */
.orig-label {{
  text-align: center; font-size: .8em; color: var(--muted);
  padding: 9px 0; border-radius: 9px;
  border: 1.5px dashed var(--border);
}}

/* 选择按钮 */
.btn-select {{
  width: 100%; padding: 9px 0; border-radius: 9px; border: none; cursor: pointer;
  font-size: .9em; font-weight: 700;
  background: color-mix(in srgb, var(--card-color) 15%, transparent);
  color: var(--card-color);
  border: 1.5px solid color-mix(in srgb, var(--card-color) 40%, transparent);
  transition: all .18s;
}}
.btn-select:hover {{
  background: color-mix(in srgb, var(--card-color) 25%, transparent);
  border-color: var(--card-color);
}}
.btn-selected {{
  background: var(--card-color) !important;
  color: #000 !important; border-color: var(--card-color) !important;
}}

/* 底部操作栏 */
.action-bar {{
  display: flex; align-items: center; gap: 16px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 12px 20px; flex-shrink: 0;
}}
#selected-label {{
  font-size: .9em; font-weight: 600; flex: 1;
}}
.btn-start {{
  background: linear-gradient(135deg, #16a34a, #22c55e);
  color: white; border: none;
  padding: 10px 32px; border-radius: 9px;
  font-size: .95em; font-weight: 700; cursor: pointer; white-space: nowrap;
  box-shadow: 0 4px 16px rgba(34,197,94,.3); transition: all .18s;
}}
.btn-start:hover {{ transform: translateY(-1px); box-shadow: 0 6px 24px rgba(34,197,94,.45); }}
#status {{ font-size: .85em; color: #60a5fa; white-space: nowrap; }}

/* 灯箱 */
#lightbox {{
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,.88); z-index: 9999;
  align-items: center; justify-content: center;
  cursor: zoom-out;
}}
#lightbox.open {{ display: flex; animation: lbIn .18s ease; }}
@keyframes lbIn {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
#lb-wrap {{
  position: relative; display: flex; flex-direction: column;
  align-items: center; gap: 14px; cursor: default;
}}
#lb-img {{
  max-width: 88vw; max-height: 84vh;
  border-radius: 10px; box-shadow: 0 0 80px rgba(0,0,0,.9);
  animation: imgIn .2s cubic-bezier(.22,.68,0,1.2);
}}
@keyframes imgIn {{ from {{ transform:scale(.93); opacity:0; }} to {{ transform:scale(1); opacity:1; }} }}
#lb-label {{ color: #94a3b8; font-size: .88em; }}
#lb-close {{
  position: fixed; top: 20px; right: 28px;
  width: 36px; height: 36px; border-radius: 50%;
  background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.2);
  color: white; font-size: 1.1em; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s;
}}
#lb-close:hover {{ background: rgba(255,255,255,.22); }}
#lb-prev, #lb-next {{
  position: fixed; top: 50%; transform: translateY(-50%);
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.15);
  color: white; font-size: 1.8em; padding: 10px 16px;
  cursor: pointer; border-radius: 10px; transition: background .15s;
}}
#lb-prev {{ left: 16px; }} #lb-next {{ right: 16px; }}
#lb-prev:hover, #lb-next:hover {{ background: rgba(255,255,255,.2); }}
@keyframes fadeIn {{ from {{ opacity:0; transform:scale(.97); }} to {{ opacity:1; transform:scale(1); }} }}
</style>
</head>
<body>

<div class="brand-bar">
  <div>{logo_block}</div>
  <div class="brand-right">
    <div class="slogan">让每个小生意，也能用大科技</div>
    <a class="site-link" href="https://magictime999.cn" target="_blank">magictime999.cn ↗</a>
  </div>
</div>

<div class="title-area">
  <div class="page-title">选择压缩方案</div>
  <div class="page-sub">{video_name} · 看看实际效果，挑一个合适的再开始</div>
</div>

<div class="cards-row">
{cards_html}
</div>

<div class="action-bar">
  <div id="selected-label">已选：🟡 均衡</div>
  <div id="status"></div>
  <button class="btn-start" onclick="startCompress()">开始压缩 ▶</button>
</div>

<div id="lightbox" onclick="if(event.target===this)closeLightbox()">
  <button id="lb-close" onclick="closeLightbox()">✕</button>
  <button id="lb-prev" onclick="lbStep(-1)">‹</button>
  <div id="lb-wrap">
    <img id="lb-img" src="" alt="">
    <div id="lb-label"></div>
  </div>
  <button id="lb-next" onclick="lbStep(1)">›</button>
</div>

<script>
const FRAMES = {frames_js};
const LB_IMGS = {lb_imgs_js};
const CRF_MAP = {crf_map_js};
const NAME_MAP = {name_map_js};
const N_FRAMES = {n_frames};
const ALL_KEYS = ["orig","hd","balance","small"];
const SELECTABLE = {selectable_keys_js};

let activeFrame = 0;
let selectedPlan = "balance";
let lbKey = "balance";

// ── 音效（Web Audio API，无需外部文件）──
const AC = new (window.AudioContext || window.webkitAudioContext)();

function playClick() {{
  const o = AC.createOscillator(), g = AC.createGain();
  o.connect(g); g.connect(AC.destination);
  o.type = "sine";
  o.frequency.setValueAtTime(1200, AC.currentTime);
  o.frequency.exponentialRampToValueAtTime(600, AC.currentTime + 0.06);
  g.gain.setValueAtTime(0.18, AC.currentTime);
  g.gain.exponentialRampToValueAtTime(0.001, AC.currentTime + 0.07);
  o.start(); o.stop(AC.currentTime + 0.07);
}}

function playSelect() {{
  [0, 80, 160].forEach((ms, i) => {{
    setTimeout(() => {{
      const o = AC.createOscillator(), g = AC.createGain();
      o.connect(g); g.connect(AC.destination);
      o.type = "sine";
      o.frequency.value = [660, 880, 1100][i];
      g.gain.setValueAtTime(0.12, AC.currentTime);
      g.gain.exponentialRampToValueAtTime(0.001, AC.currentTime + 0.12);
      o.start(); o.stop(AC.currentTime + 0.12);
    }}, ms);
  }});
}}

// ── 帧切换 ──
function setFrame(idx) {{
  activeFrame = idx;
  ALL_KEYS.forEach(key => {{
    const img = document.getElementById("img-" + key);
    if (img && FRAMES[key]?.[idx]) img.src = FRAMES[key][idx];
    document.getElementById("dots-" + key)?.querySelectorAll(".dot").forEach((d,i) => {{
      d.classList.toggle("dot-active", i === idx);
    }});
  }});
  if (document.getElementById("lightbox").classList.contains("open")) {{
    const d = LB_IMGS[lbKey]?.[idx];
    if (d?.src) {{ document.getElementById("lb-img").src = d.src; document.getElementById("lb-label").textContent = d.label; }}
  }}
}}

// ── 方案选择 ──
function selectPlan(key) {{
  playSelect();
  selectedPlan = key;
  SELECTABLE.forEach(k => {{
    document.getElementById("card-" + k).classList.toggle("card-selected", k === key);
    const btn = document.getElementById("btn-" + k);
    if (btn) {{ btn.textContent = k === key ? "✓ 已选择" : "选这个"; btn.classList.toggle("btn-selected", k === key); }}
  }});
  document.getElementById("selected-label").textContent = "已选：" + NAME_MAP[key];
}}

// ── 灯箱 ──
function openLightbox(key) {{
  playClick();
  lbKey = key;
  const d = LB_IMGS[key]?.[activeFrame];
  if (!d?.src) return;
  document.getElementById("lb-img").src = d.src;
  document.getElementById("lb-label").textContent = d.label;
  document.getElementById("lightbox").classList.add("open");
}}
function closeLightbox() {{
  playClick();
  document.getElementById("lightbox").classList.remove("open");
}}
function lbStep(dir) {{
  let pi = ALL_KEYS.indexOf(lbKey) + dir;
  if (pi < 0) pi = ALL_KEYS.length - 1;
  if (pi >= ALL_KEYS.length) pi = 0;
  lbKey = ALL_KEYS[pi];
  const d = LB_IMGS[lbKey]?.[activeFrame];
  if (d?.src) {{ document.getElementById("lb-img").src = d.src; document.getElementById("lb-label").textContent = d.label; }}
}}
document.addEventListener("keydown", e => {{
  if (!document.getElementById("lightbox").classList.contains("open")) return;
  if (e.key === "Escape") closeLightbox();
  if (e.key === "ArrowLeft") lbStep(-1);
  if (e.key === "ArrowRight") lbStep(1);
}});

// ── 开始压缩 ──
function startCompress() {{
  playSelect();
  const crf = CRF_MAP[selectedPlan];
  document.getElementById("status").textContent = "⏳ 启动中，请看终端...";
  fetch("/start?crf=" + crf).then(r => r.text()).then(t => {{
    document.getElementById("status").textContent = "✅ " + t;
  }});
}}
</script>
</body>
</html>"""



# ──────────────────────────────────────────────
# HTTP 服务器
# ──────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    html_content = ""
    chosen_crf = None
    server_ref = None

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(Handler.html_content.encode("utf-8"))
        elif parsed.path == "/start":
            crf = parse_qs(parsed.query).get("crf", ["23"])[0]
            Handler.chosen_crf = int(crf)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"已选 CRF {crf}，请查看终端".encode())
            threading.Thread(target=self._shutdown, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def _shutdown(self):
        import time; time.sleep(0.6)
        Handler.server_ref.shutdown()


def run_server(html, directory):
    Handler.html_content = html
    server = HTTPServer(("127.0.0.1", 0), Handler)
    Handler.server_ref = server
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}"
    print(f"🌐 预览页面：{url}")
    webbrowser.open(url)
    server.serve_forever()
    return Handler.chosen_crf


# ──────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = input("请输入视频目录路径：").strip().strip("'\"")
    directory = str(Path(directory).resolve())

    if not os.path.isdir(directory):
        print(f"❌ 目录不存在：{directory}")
        sys.exit(1)

    videos = find_videos(directory)
    if not videos:
        print(f"❌ 目录中没有找到视频文件：{directory}")
        sys.exit(1)

    video_path = str(videos[0])
    print(f"📹 预览视频：{Path(video_path).name}（共 {len(videos)} 个视频）")

    tmp_dir = tempfile.mkdtemp(prefix="compress_preview_")
    try:
        frames_data, sample_paths, src_duration = generate_previews(video_path, tmp_dir)

        # 用实测样本比特率推算整个目录的压缩后大小
        total_duration = sum(get_duration(v) for v in find_videos(directory))
        size_estimates = {}
        for preset in CRF_PRESETS:
            crf = preset["crf"]
            sample = sample_paths.get(crf)
            if sample and os.path.exists(sample):
                bitrate = get_sample_bitrate(sample)  # bps
                if bitrate > 0:
                    size_estimates[crf] = int(bitrate * total_duration / 8)
                    continue
            # 降级：固定比例
            from pathlib import Path as P
            total_src = sum(v.stat().st_size for v in find_videos(directory))
            ratio = {18: 0.55, 23: 0.35, 28: 0.22}
            size_estimates[crf] = int(total_src * ratio.get(crf, 0.35))

        html = build_html(Path(video_path).name, frames_data, size_estimates)
        chosen_crf = run_server(html, directory)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if chosen_crf is None:
        print("❌ 未选择质量，已取消")
        sys.exit(0)

    print(f"\n🚀 启动压缩，CRF={chosen_crf}，目录：{directory}\n")
    os.execv("/bin/bash",
             ["/bin/bash", str(COMPRESS_SCRIPT),
              "--crf", str(chosen_crf), directory])


if __name__ == "__main__":
    main()
