"""办案助手 — 包装「办案材料助手」的本机 CLI 能力，供摩尚OA前端调用。

三类任务，全部在后台线程跑子进程/纯Python，前端轮询任务状态：
- convert:  材料转换（droplet --agent，PDF/图片 OCR、Office→MD、MD→Word、音视频逐字稿）
- wechat:   微信录屏取证（wechat_evidence.py interval-pdf）
- organize: 证据整理（移植自 vision-ocr-gui-native.py，扫描输出目录生成汇总/时间线/OS输入包）
"""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

# ------------------------------------------------------------------ 工具路径

# HOME 可能被启动环境（沙盒/代理 shell）重定向到临时目录，droplet.sh 及各 CLI
# 依赖 $HOME 定位 ~/.local/bin 和桌面输出目录，必须钉死为真实用户目录。
REAL_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
SUBPROC_ENV = {**os.environ, "HOME": str(REAL_HOME)}

HELPER_APP = Path("/Applications/办案工具集/办案材料助手.app")
DROPLET_SH = HELPER_APP / "Contents" / "MacOS" / "droplet.sh"
WECHAT_CLI = HELPER_APP / "Contents" / "Resources" / "wechat_evidence.py"
PY = "/opt/homebrew/bin/python3"

LOCAL_BIN = REAL_HOME / ".local" / "bin"
VISION_OCR_PDF = LOCAL_BIN / "vision-ocr-pdf"
MINERU_CLI = LOCAL_BIN / "mineru-local"
LEGAL_OCR_CLI = LOCAL_BIN / "legal-ocr-convert"

OUTPUT_DIR = REAL_HOME / "Desktop" / "VisionOCR_Output"
WECHAT_OUTPUT_DIR = REAL_HOME / "Desktop" / "录屏取证输出"

ENGINES = ["mineru", "visionocr", "legalocr", "legalocr-paddle", "legalocr-mineru"]

AUDIO_EXTS = {"mp3", "wav", "m4a", "aac", "flac", "ogg", "wma"}
VIDEO_EXTS = {"mp4", "m4v", "mov", "avi", "mkv", "webm", "flv"}
IMAGE_EXTS = {"png", "jpg", "jpeg", "tif", "tiff", "bmp", "gif", "heic", "webp"}
OCR_EXTS = {"pdf"} | IMAGE_EXTS
DOCX_EXTS = {"md", "txt", "markdown"}
OFFICE_EXTS = {"pptx", "ppt", "xlsx", "xls", "xlsm", "csv", "tsv", "ods", "docx", "doc", "html", "htm", "epub", "json", "xml", "zip"}
SUPPORTED_EXTS = OCR_EXTS | DOCX_EXTS | AUDIO_EXTS | VIDEO_EXTS | OFFICE_EXTS

EVIDENCE_TEXT_EXTS = {"md", "markdown", "txt"}
EVIDENCE_INDEX_EXTS = {"jsonl", "json"}
EVIDENCE_SKIP_DIRS = {"证据整理", "_原始抽帧缓存", "archive", "__pycache__"}


def tool_status() -> dict:
    return {
        "helper_app": DROPLET_SH.exists(),
        "wechat_evidence": WECHAT_CLI.exists(),
        "python3": Path(PY).exists(),
        "engines": {
            "mineru": MINERU_CLI.exists(),
            "visionocr": VISION_OCR_PDF.exists(),
            "legalocr": LEGAL_OCR_CLI.exists(),
        },
        "output_dir": str(OUTPUT_DIR),
        "wechat_output_dir": str(WECHAT_OUTPUT_DIR),
    }


# ------------------------------------------------------------------ 任务管理

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_LOG_LIMIT = 4000


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _new_job(kind: str, title: str, inputs: list[str]) -> dict:
    job = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "title": title,
        "status": "running",
        "detail": "已开始",
        "created_at": _now(),
        "finished_at": None,
        "inputs": inputs,
        "outputs": [],
        "log_tail": "",
        "error": None,
    }
    with _lock:
        _jobs[job["id"]] = job
    return job


def _update(job: dict, **kw) -> None:
    with _lock:
        job.update(kw)


def _finish(job: dict, outputs: list[str], error: str | None = None) -> None:
    _update(
        job,
        status="failed" if error else "done",
        detail="失败" if error else "完成",
        finished_at=_now(),
        outputs=outputs,
        error=error,
    )


def list_jobs() -> list[dict]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)


def get_job(job_id: str) -> dict | None:
    with _lock:
        return _jobs.get(job_id)


def _run_logged(job: dict, cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, text=True, capture_output=True, env=SUBPROC_ENV)
    log = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    _update(job, log_tail=log[-_LOG_LIMIT:])
    return proc


# ------------------------------------------------------------------ 材料转换


def _expected_output(path: Path) -> Path | None:
    ext = path.suffix.lower().lstrip(".")
    if ext in OCR_EXTS or ext in OFFICE_EXTS:
        return OUTPUT_DIR / f"{path.stem}.md"
    if ext in DOCX_EXTS:
        return OUTPUT_DIR / f"{path.stem}.docx"
    if ext in AUDIO_EXTS or ext in VIDEO_EXTS:
        return OUTPUT_DIR / f"{path.stem}_逐字稿.md"
    return None


def start_convert(paths: list[str], engine: str) -> dict:
    files = [Path(p).expanduser() for p in paths]
    title = f"材料转换（{len(files)} 个文件 · {engine}）"
    job = _new_job("convert", title, [str(p) for p in files])

    def run() -> None:
        try:
            missing = [str(p) for p in files if not p.is_file()]
            if missing:
                _finish(job, [], "文件不存在：" + "、".join(missing))
                return
            unsupported = [p.name for p in files if p.suffix.lower().lstrip(".") not in SUPPORTED_EXTS]
            if unsupported:
                _finish(job, [], "不支持的文件类型：" + "、".join(unsupported))
                return
            _update(job, detail="正在转换…")
            cmd = ["/bin/bash", str(DROPLET_SH), "--agent", "--engine", engine, *[str(p) for p in files]]
            proc = _run_logged(job, cmd)
            outputs = [str(o) for p in files if (o := _expected_output(p)) and o.is_file()]
            if outputs:
                _finish(job, outputs, None if proc.returncode == 0 else None)
                if proc.returncode != 0:
                    _update(job, detail=f"完成（部分失败，成功 {len(outputs)}/{len(files)}）")
            else:
                _finish(job, [], "转换失败，未生成输出文件（详见日志）")
        except Exception as exc:  # noqa: BLE001
            _finish(job, [], str(exc))

    threading.Thread(target=run, daemon=True).start()
    return job


# ------------------------------------------------------------------ 录屏取证


def start_wechat(paths: list[str], interval: float, smart_filter: bool, preserve_head_sec: float) -> dict:
    files = [Path(p).expanduser() for p in paths]
    title = f"微信录屏取证（{len(files)} 个视频 · 每{interval:g}秒1张{'+智能筛选' if smart_filter else ''}）"
    job = _new_job("wechat", title, [str(p) for p in files])

    def run() -> None:
        try:
            missing = [str(p) for p in files if not p.is_file()]
            if missing:
                _finish(job, [], "视频不存在：" + "、".join(missing))
                return
            _update(job, detail="正在抽帧并生成取证PDF…")
            cmd = [
                PY, str(WECHAT_CLI), "interval-pdf", *[str(p) for p in files],
                "--interval", str(interval),
                "--preserve-head-sec", str(preserve_head_sec),
            ]
            if smart_filter:
                cmd += ["--filter", "auto"]
            proc = _run_logged(job, cmd)
            # interval-pdf 末尾逐行打印导出目录 / PDF / 索引路径
            outputs = [
                line.strip()
                for line in (proc.stdout or "").splitlines()
                if line.strip().startswith("/") and Path(line.strip()).exists()
            ]
            if proc.returncode == 0 and outputs:
                _finish(job, outputs)
            else:
                _finish(job, outputs, None if outputs else "取证失败（详见日志）")
        except Exception as exc:  # noqa: BLE001
            _finish(job, [], str(exc))

    threading.Thread(target=run, daemon=True).start()
    return job


# ------------------------------------------------------------------ 证据整理
# 以下逻辑移植自 办案材料助手 vision-ocr-gui-native.py（去掉 AppKit UI 部分，行为保持一致）


def _path_is_skipped(path: Path) -> bool:
    return bool(set(path.parts) & EVIDENCE_SKIP_DIRS)


def _is_evidence_file(path: Path) -> bool:
    suffix = path.suffix.lower().lstrip(".")
    return suffix in EVIDENCE_TEXT_EXTS or suffix == "pdf" or suffix in EVIDENCE_INDEX_EXTS


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _material_kind(path: Path) -> str:
    name = path.name
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "pdf":
        return "取证PDF" if "录屏取证" in name else "PDF"
    if suffix in {"jsonl", "json"}:
        return "OCR索引" if "OCR" in name or "索引" in name else "结构化索引"
    if "聊天记录分析报告" in name:
        return "聊天分析报告"
    if "OCR文字索引" in name:
        return "OCR Markdown"
    if "逐字稿" in name:
        return "音视频转写稿"
    return "Markdown文本" if suffix in EVIDENCE_TEXT_EXTS else "材料"


def _material_record(path: Path, source_dir: Path) -> dict:
    stat = path.stat()
    return {
        "material_id": f"mat-{hashlib.sha1(str(path.resolve()).encode('utf-8')).hexdigest()[:10]}",
        "title": path.stem,
        "kind": _material_kind(path),
        "path": str(path),
        "relative_path": str(path.relative_to(source_dir)) if source_dir in path.parents or path == source_dir else path.name,
        "suffix": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
        "sha256": _file_sha256(path),
        "pending_review": True,
    }


def _scan_evidence_materials(source_dir: Path) -> list[dict]:
    files = [
        path
        for path in sorted(source_dir.rglob("*"))
        if path.is_file() and not _path_is_skipped(path) and _is_evidence_file(path)
    ]
    return [_material_record(path, source_dir) for path in files]


def _read_text_material(path: Path, limit: int = 8000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except Exception:  # noqa: BLE001
        return ""


def _dir_has_evidence_files(folder: Path) -> bool:
    if not folder.exists():
        return False
    for child in folder.iterdir():
        if child.name in EVIDENCE_SKIP_DIRS:
            continue
        if child.is_file() and _is_evidence_file(child):
            return True
    return False


def latest_wechat_export_dir(base: Path = WECHAT_OUTPUT_DIR) -> Path:
    base = base.expanduser()
    if not base.exists() or _dir_has_evidence_files(base):
        return base
    candidates = []
    for child in base.iterdir():
        if not child.is_dir() or child.name in EVIDENCE_SKIP_DIRS:
            continue
        files = [p for p in child.rglob("*") if p.is_file() and _is_evidence_file(p) and not _path_is_skipped(p)]
        if files:
            newest = max(p.stat().st_mtime for p in files)
            candidates.append((newest, child))
    if not candidates:
        return base
    return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]


def _wechat_ocr_paths(source_dir: Path) -> dict[str, Path]:
    return {
        "index": source_dir / "复核资料" / "OCR文字索引.jsonl",
        "markdown": source_dir / "录屏取证初稿_OCR文字索引.md",
        "report": source_dir / "聊天记录分析报告.md",
    }


def _looks_like_wechat_export_dir(source_dir: Path) -> bool:
    return (
        (source_dir / "复核资料" / "截图索引.jsonl").exists()
        and (source_dir / "截图").exists()
        and any(source_dir.glob("录屏取证*.pdf"))
    )


def _ensure_wechat_ocr(job: dict, source_dir: Path) -> str:
    if not _looks_like_wechat_export_dir(source_dir):
        return ""
    paths = _wechat_ocr_paths(source_dir)
    markdown_current = False
    if paths["markdown"].exists():
        try:
            markdown_current = "结构化聊天记录（去重）" in paths["markdown"].read_text(encoding="utf-8", errors="ignore")[:5000]
        except Exception:  # noqa: BLE001
            markdown_current = False
    if paths["index"].exists() and paths["markdown"].exists() and paths["report"].exists() and markdown_current:
        return ""
    _update(job, detail="正在整理取证PDF截图 OCR…")
    cmd = [PY, str(WECHAT_CLI), "ocr-index", str(source_dir), "--scope", "selected", "--jobs", "2"]
    proc = subprocess.run(cmd, text=True, capture_output=True, env=SUBPROC_ENV)
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout or "录屏取证 OCR 失败").strip()[:500]
    missing = [path.name for path in paths.values() if not path.exists()]
    if missing:
        return "录屏取证 OCR 未完整生成：" + "、".join(missing)
    return "已完成取证PDF截图全量 OCR"


def _copy_supporting_evidence_texts(evidence_dir: Path, materials: list[dict]) -> list[Path]:
    copied = []
    wanted_names = {"录屏取证初稿_OCR文字索引.md", "聊天记录分析报告.md"}
    for item in materials:
        src = Path(item["path"])
        if src.name not in wanted_names or not src.exists():
            continue
        dst = evidence_dir / src.name
        try:
            shutil.copy2(src, dst)
            copied.append(dst)
        except Exception:  # noqa: BLE001
            pass
    return copied


def _ensure_pdf_markdown(job: dict, source_dir: Path, evidence_dir: Path, materials: list[dict]) -> tuple[list[dict], str]:
    has_text = any(item["suffix"].lstrip(".") in EVIDENCE_TEXT_EXTS for item in materials)
    pdfs = [Path(item["path"]) for item in materials if item["suffix"] == ".pdf"]
    if has_text or not pdfs:
        return materials, ""
    pdf = sorted(pdfs, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    auto_dir = evidence_dir / "自动补转MD"
    auto_dir.mkdir(parents=True, exist_ok=True)
    out = auto_dir / f"{pdf.stem}.md"
    if not out.exists():
        _update(job, detail=f"正在将取证PDF补转 Markdown：{pdf.name}")
        proc = subprocess.run([PY, str(VISION_OCR_PDF), str(pdf), "--output", str(out)], text=True, capture_output=True, env=SUBPROC_ENV)
        if proc.returncode != 0 or not out.exists():
            return materials, (proc.stderr or proc.stdout or "PDF 补转 Markdown 失败").strip()[:500]
    auto_record = _material_record(out, source_dir)
    auto_record["kind"] = "自动补转Markdown"
    auto_record["source_pdf"] = str(pdf)
    materials.append(auto_record)
    return materials, ""


def _extract_timeline_events(materials: list[dict]) -> list[dict]:
    events: list[dict] = []
    date_pattern = re.compile(r"(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?|\d{1,2}月\d{1,2}日|\d{1,2}:\d{2}(?::\d{2})?)")
    for item in materials:
        path = Path(item["path"])
        suffix = item["suffix"].lstrip(".")
        if suffix == "jsonl":
            try:
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    chat_time = str(record.get("chat_time") or "").strip()
                    screen_time = str(record.get("timestamp_hms") or "").strip()
                    content = str(record.get("chat_content") or record.get("text") or "").strip()
                    if chat_time or screen_time or content:
                        events.append({
                            "time": chat_time or screen_time or "需人工确认",
                            "source": item["title"],
                            "excerpt": re.sub(r"\s+", " ", content)[:160] or "OCR记录，需人工核实",
                        })
            except Exception:  # noqa: BLE001
                pass
            continue
        if suffix not in EVIDENCE_TEXT_EXTS:
            continue
        text = _read_text_material(path, limit=30000)
        for line in text.splitlines():
            clean = line.strip().strip("| ")
            if not clean:
                continue
            match = date_pattern.search(clean)
            if match or "录屏时间" in clean or "聊天时间" in clean:
                events.append({
                    "time": match.group(1) if match else "需人工确认",
                    "source": item["title"],
                    "excerpt": clean[:180],
                })
            if len(events) >= 300:
                break
    return events[:300]


def _write_evidence_outputs(
    source_dir: Path,
    evidence_dir: Path,
    materials: list[dict],
    timeline_events: list[dict],
    conversion_note: str,
) -> tuple[Path, ...]:
    generated_at = _now()
    summary_path = evidence_dir / "案件材料汇总.md"
    timeline_path = evidence_dir / "案件时间线.md"
    manifest_path = evidence_dir / "materials_manifest.json"
    intake_path = evidence_dir / "case_os_intake_package.json"

    summary_lines = [
        "# 案件材料汇总",
        "",
        "需人工核实。本汇总只基于当前输出文件夹中的文件生成，OCR、语音识别、身份、金额和日期均不得直接作为已确认事实。",
        "",
        f"- 生成时间：{generated_at}",
        f"- 来源目录：`{source_dir}`",
        f"- 材料数量：{len(materials)}",
        "",
        "## 材料清单",
        "",
        "| 序号 | 类型 | 文件 | 修改时间 | SHA256 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for idx, item in enumerate(materials, start=1):
        summary_lines.append(
            f"| {idx} | {item['kind']} | `{item['relative_path']}` | {item['mtime']} | `{item['sha256'][:12]}` |"
        )
    if conversion_note:
        summary_lines.extend(["", "## 自动补转提示", "", f"- {conversion_note}"])
    summary_lines.extend(["", "## 文本摘录", ""])
    for item in materials:
        if item["suffix"].lstrip(".") not in EVIDENCE_TEXT_EXTS:
            continue
        text = _read_text_material(Path(item["path"]), limit=3000).strip()
        summary_lines.extend([
            f"### {item['title']}",
            "",
            f"- 类型：{item['kind']}",
            f"- 文件：`{item['path']}`",
            "",
            "```text",
            text or "（无可读取文本）",
            "```",
            "",
        ])
    summary_path.write_text("\n".join(summary_lines).rstrip() + "\n", encoding="utf-8")

    timeline_lines = [
        "# 案件时间线",
        "",
        "需人工核实。以下时间线由 Markdown、OCR 索引和转写文本中可识别的时间线索自动抽取。",
        "",
        "| 序号 | 时间线索 | 来源 | 内容摘录 |",
        "| --- | --- | --- | --- |",
    ]
    if timeline_events:
        for idx, event in enumerate(timeline_events, start=1):
            excerpt = str(event["excerpt"]).replace("|", "｜")
            timeline_lines.append(f"| {idx} | {event['time']} | {event['source']} | {excerpt} |")
    else:
        timeline_lines.append("| 1 | 需人工补充 | 当前材料 | 未自动识别到稳定时间线索 |")
    timeline_path.write_text("\n".join(timeline_lines).rstrip() + "\n", encoding="utf-8")

    manifest = {
        "package_version": "evidence-organizer-v0.1",
        "generated_at": generated_at,
        "source_dir": str(source_dir),
        "evidence_dir": str(evidence_dir),
        "materials": materials,
        "outputs": {
            "summary_md": str(summary_path),
            "timeline_md": str(timeline_path),
            "manifest_json": str(manifest_path),
            "case_os_intake_package_json": str(intake_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    intake = {
        "package_version": "case-os-intake-v0.1",
        "source_system": "摩尚OA-办案助手-证据整理",
        "generated_at": generated_at,
        "intended_use": "供案件OS Phase A读取的材料输入包；不表示案件OS任一步骤已经完成。",
        "source_dir": str(source_dir),
        "materials": materials,
        "derived_outputs": manifest["outputs"],
        "upstream_summary": {
            "step": "证据材料文字化与整理",
            "conclusion": f"已从当前输出目录登记 {len(materials)} 份材料，并生成材料汇总与时间线初稿。",
            "key_findings": [
                f"自动抽取时间线索 {len(timeline_events)} 条",
                "所有 OCR、语音识别和自动抽取内容均需律师人工核实",
            ],
            "pending_review": True,
            "confirmation_status": "pending",
        },
        "handoff_notes": {
            "missing_info": ["材料真实性、完整性、发言人身份、金额和日期均需人工确认"],
            "risk_alerts": [
                "本包不得替代原始录屏、截图、PDF或音视频文件",
                "不得把 OCR 或语音转写内容直接写成已确认事实",
            ],
            "next_step_hints": ["可交给案件OS Phase A继续做案件理解、归档和证据卡片整理"],
        },
    }
    intake_path.write_text(json.dumps(intake, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    copied = _copy_supporting_evidence_texts(evidence_dir, materials)
    return (summary_path, timeline_path, *copied, manifest_path, intake_path)


def start_organize(source: str, custom_dir: str | None) -> dict:
    if source == "wechat":
        source_dir = latest_wechat_export_dir()
    elif source == "custom" and custom_dir:
        source_dir = Path(custom_dir).expanduser()
    else:
        source_dir = OUTPUT_DIR
    job = _new_job("organize", f"证据整理（{source_dir.name}）", [str(source_dir)])

    def run() -> None:
        try:
            if not source_dir.exists():
                _finish(job, [], f"目录不存在：{source_dir}")
                return
            evidence_dir = source_dir / "证据整理"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            ocr_note = _ensure_wechat_ocr(job, source_dir)
            _update(job, detail="正在扫描输出文件夹…")
            materials = _scan_evidence_materials(source_dir)
            materials, conversion_note = _ensure_pdf_markdown(job, source_dir, evidence_dir, materials)
            conversion_note = "；".join(note for note in (ocr_note, conversion_note) if note)
            if not materials:
                _finish(job, [], f"当前目录中没有找到 Markdown、PDF 或 OCR 索引：{source_dir}")
                return
            _update(job, detail="正在抽取时间线索…")
            timeline_events = _extract_timeline_events(materials)
            _update(job, detail="正在生成证据整理文件…")
            outputs = _write_evidence_outputs(source_dir, evidence_dir, materials, timeline_events, conversion_note)
            _update(job, log_tail=f"整理 {len(materials)} 份材料，抽取时间线索 {len(timeline_events)} 条")
            _finish(job, [str(p) for p in outputs])
        except Exception as exc:  # noqa: BLE001
            _finish(job, [], str(exc))

    threading.Thread(target=run, daemon=True).start()
    return job


# ------------------------------------------------------------------ 文件选择 / 打开


_PICK_FILES_SCRIPT = """
tell application "System Events" to activate
set fs to choose file with multiple selections allowed with prompt "选择要处理的材料文件"
set out to ""
repeat with f in fs
    set out to out & POSIX path of f & linefeed
end repeat
return out
"""

_PICK_FOLDER_SCRIPT = """
tell application "System Events" to activate
set f to choose folder with prompt "选择要整理的输出目录"
return POSIX path of f
"""


def pick_paths(mode: str) -> list[str]:
    script = _PICK_FOLDER_SCRIPT if mode == "folder" else _PICK_FILES_SCRIPT
    try:
        proc = subprocess.run(["osascript", "-"], input=script, text=True, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired:
        return []
    if proc.returncode != 0:  # 用户取消等
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def reveal(path: str) -> bool:
    target = Path(path).expanduser()
    if target.is_dir():
        subprocess.run(["open", str(target)], check=False)
        return True
    if target.is_file():
        subprocess.run(["open", "-R", str(target)], check=False)
        return True
    return False
