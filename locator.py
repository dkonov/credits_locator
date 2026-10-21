#!/usr/bin/env python3
"""Locate credit intervals in local video; sparse sampling, no remote APIs."""
import argparse
import csv
import json
import math
import re
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageDraw
from pytesseract import Output

EXTS = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm"}
TERMS = re.compile(
    r"\b(?:director|producer|cast|starring|editor|editing|cinematograph\w*|camera|"
    r"gaffer|grip|sound|music|costume\w*|makeup|casting|visual effects|"
    r"special thanks|written by|produced by|directed by|production|assistant|"
    r"оператор\w*|режисс[её]р\w*|продюсер\w*|монтаж\w*|звук\w*|музык\w*|"
    r"художник\w*|грим\w*|костюм\w*|сценар\w*|в ролях|благодарност\w*|"
    r"осветител\w*|ассистент\w*|гафф?ер\w*|фокус.пуллер\w*|механик|администратор\w*)\b",
    re.I,
)
WORD = re.compile(r"[A-Za-zА-Яа-яЁё]{2,}(?:[-–][A-Za-zА-Яа-яЁё]{2,})?")

def clock(seconds):
    s = max(0, int(seconds))
    return f"{s//3600:02d}:{s//60%60:02d}:{s%60:02d}"

def sample_times(duration, opening, closing, edge_step, middle_step):
    a = min(duration, opening)
    b = max(a, duration - closing)
    spans = [(0, a, edge_step), (a, b, middle_step), (b, duration, edge_step)]
    points = {0.0}
    for start, end, step in spans:
        t = start
        while t < end:
            points.add(round(t, 2))
            t += step
    return sorted(t for t in points if t < duration)

def frame_at(cap, t, width):
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0, t) * 1000)
    ok, frame = cap.read()
    if not ok:
        return None
    h, w = frame.shape[:2]
    if w > width:
        frame = cv2.resize(frame, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
    return frame

def features(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
    contrast = cv2.max(cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel),
                       cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel))
    _, mask = cv2.threshold(contrast, 22, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (12, 2)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects = []
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if .05*w <= cw <= .95*w and 3 <= ch <= .09*h and cw/ch >= 2.2:
            rects.append((x, y, cw, ch))
    upper = sum(y < .78*h for x, y, cw, ch in rects)
    return {"line_shapes": len(rects), "upper_shapes": upper,
            "bottom_shapes": len(rects)-upper,
            "dark_fraction": round(float(np.mean(gray < 65)), 3)}

def ocr(frame, lang):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    if w < 1100:
        rgb = cv2.resize(rgb, (1100, round(h*1100/w)), interpolation=cv2.INTER_CUBIC)
    data = pytesseract.image_to_data(rgb, lang=lang, config="--psm 11", output_type=Output.DICT)
    lines = {}
    confs = []
    for i, raw in enumerate(data["text"]):
        word = raw.strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not word or conf < 35:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        confs.append(conf)
    text = "\n".join(" ".join(words) for words in lines.values())
    return {"text": text, "ocr_lines": len(lines), "ocr_words": len(text.split()),
            "valid_words": sum(len(w) >= 3 for w in WORD.findall(text)),
            "credit_keywords": len(TERMS.findall(text)),
            "mean_ocr_confidence": round(sum(confs)/len(confs), 1) if confs else 0}

def score(feat, record):
    """Conservative evidence score, *not* a calibrated probability."""
    good, keywords = record["valid_words"], record["credit_keywords"]
    multiline = record["ocr_lines"] >= 4 and good >= 7
    dark = feat["dark_fraction"] >= .83
    structured = feat["upper_shapes"] >= 3
    if keywords == 0 and not (multiline and dark and structured):
        return 0.0
    if keywords >= 2 and good >= 5:
        return round(min(1., .70 + .08*min(keywords, 3) + .02*min(good, 10)), 3)
    if keywords >= 1 and good >= 5 and (dark or (multiline and structured)):
        return round(min(.92, .57 + .02*min(good, 12) + .05*int(dark)), 3)
    if dark and structured and multiline:
        return round(min(.79, .40 + .02*min(good, 14)), 3)
    return 0.0

def group_hits(records, threshold, gap, padding, duration, min_hits):
    hits = sorted(r["time_sec"] for r in records if r["score"] >= threshold)
    if not hits:
        return []
    groups = [[hits[0]]]
    for t in hits[1:]:
        if t - groups[-1][-1] <= gap:
            groups[-1].append(t)
        else:
            groups.append([t])
    result = []
    for group in groups:
        if len(group) < min_hits:
            continue
        start, end = max(0, group[0]-padding), min(duration, group[-1]+padding)
        result.append({"start_sec": round(start, 2), "end_sec": round(end, 2),
                       "start_time": clock(start), "end_time": clock(end), "hits": len(group)})
    return result

def contact_sheet(thumbs, path):
    if not thumbs:
        return
    tw, th, cols = 320, 215, 4
    canvas = Image.new("RGB", (cols*tw, math.ceil(len(thumbs)/cols)*th), "#1b1f24")
    draw = ImageDraw.Draw(canvas)
    for i, (t, frame, value) in enumerate(thumbs):
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        img.thumbnail((312, 180))
        x, y = i%cols*tw+4, i//cols*th+4
        canvas.paste(img, (x, y))
        draw.text((x, y+184), f"{clock(t)} score={value:.2f}", fill="white")
    canvas.save(path, quality=85)

def process(video, root, args):
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError("Cannot open video")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT)/fps if fps > 0 else 0
        if duration <= 0:
            raise RuntimeError("Cannot determine video duration")
        dest = root/video.stem
        dest.mkdir(parents=True, exist_ok=True)
        times = sample_times(duration, args.opening, args.closing,
                             args.edge_step, args.middle_step)
        records, thumbs = [], []
        scanned = 0
        for i, t in enumerate(times):
            frame = frame_at(cap, t, args.width)
            if frame is None:
                continue
            scanned += 1
            feat = features(frame)
            candidate = (feat["upper_shapes"] >= 2 or feat["line_shapes"] >= 5 or
                         (feat["dark_fraction"] >= .83 and feat["line_shapes"] >= 1))
            if not candidate:
                continue
            full = frame_at(cap, t, args.ocr_width)
            if full is None:
                continue
            info = ocr(full, args.lang)
            value = score(feat, info)
            records.append({"time_sec": round(t, 2), "timestamp": clock(t),
                            "score": value, **info, "features": feat})
            if value >= args.threshold:
                thumbs.append((t, full, value))
                cv2.imwrite(str(dest/f"frame_{round(t*10):08d}.jpg"), full)
            if (i+1) % 100 == 0:
                print(f"  scanned {i+1}/{len(times)}", flush=True)
        gap = max(args.edge_step, args.middle_step)*args.join_factor
        intervals = group_hits(records, args.threshold, gap, args.padding,
                               duration, args.min_hits)
        if args.refine:
            for interval in intervals:
                positive = [r["time_sec"] for r in records if r["score"] >= args.threshold
                            and interval["start_sec"] <= r["time_sec"] <= interval["end_sec"]]
                extra = []
                for center in (min(positive), max(positive)):
                    t = max(0, center-args.edge_step)
                    while t <= min(duration-.01, center+args.edge_step):
                        frame = frame_at(cap, t, args.ocr_width)
                        if frame is not None:
                            feat = features(frame)
                            if (feat["upper_shapes"] >= 2 or
                                (feat["dark_fraction"] >= .83 and feat["line_shapes"] >= 1)):
                                if score(feat, ocr(frame, args.lang)) >= args.threshold:
                                    extra.append(t)
                        t += args.refine_step
                if extra:
                    start = max(0, min(positive+extra)-args.refine_step)
                    end = min(duration, max(positive+extra)+args.refine_step)
                    interval.update(start_sec=round(start, 2), end_sec=round(end, 2),
                                    start_time=clock(start), end_time=clock(end))
        report = {"video": str(video), "duration_sec": round(duration, 2),
                  "sampled_frames": scanned, "ocr_frames": len(records),
                  "threshold": args.threshold,
                  "method": "sparse OCR + lexical/visual evidence (v0.2); not exhaustive",
                  "intervals": intervals, "samples": records}
        (dest/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
        with (dest/"samples.csv").open("w", newline="", encoding="utf-8-sig") as out:
            writer = csv.writer(out)
            writer.writerow(["time", "score", "ocr_lines", "ocr_words",
                             "valid_words", "keywords", "text"])
            for r in records:
                writer.writerow([r["timestamp"], r["score"], r["ocr_lines"], r["ocr_words"],
                                 r["valid_words"], r["credit_keywords"],
                                 r["text"].replace("\n", " | ")])
        contact_sheet(sorted(thumbs, key=lambda x: x[2], reverse=True)[:args.max_thumbs],
                      dest/"contact_sheet.jpg")
        print(f"sampled={scanned}; OCR={len(records)}; intervals={len(intervals)}; output={dest}")
        for interval in intervals:
            print(f'  {interval["start_time"]} - {interval["end_time"]} ({interval["hits"]} hits)')
    finally:
        cap.release()

def main():
    ap = argparse.ArgumentParser(description="Local film credits locator v0.2")
    ap.add_argument("--input", type=Path, default=Path("input"))
    ap.add_argument("--output", type=Path, default=Path("output"))
    ap.add_argument("--opening", type=float, default=600)
    ap.add_argument("--closing", type=float, default=900)
    ap.add_argument("--edge-step", type=float, default=5)
    ap.add_argument("--middle-step", type=float, default=20)
    ap.add_argument("--width", type=int, default=800)
    ap.add_argument("--ocr-width", type=int, default=1280)
    ap.add_argument("--lang", default="rus+eng")
    ap.add_argument("--threshold", type=float, default=.60)
    ap.add_argument("--padding", type=float, default=5)
    ap.add_argument("--join-factor", type=float, default=1.5)
    ap.add_argument("--min-hits", type=int, default=2)
    ap.add_argument("--refine", action="store_true")
    ap.add_argument("--refine-step", type=float, default=1)
    ap.add_argument("--max-thumbs", type=int, default=32)
    args = ap.parse_args()
    if min(args.edge_step, args.middle_step, args.refine_step) <= 0:
        ap.error("Sampling steps must be positive")
    if not 0 <= args.threshold <= 1:
        ap.error("Threshold must be in [0, 1]")
    args.output.mkdir(parents=True, exist_ok=True)
    paths = ([args.input] if args.input.is_file() else
             sorted(p for p in args.input.iterdir() if p.suffix.lower() in EXTS)
             if args.input.exists() else [])
    if not paths:
        ap.error(f"No video files found in {args.input}")
    errors = 0
    for path in paths:
        print(f"Processing {path}", flush=True)
        try:
            process(path, args.output, args)
        except Exception as exc:
            errors += 1
            print(f"ERROR {path}: {exc}", flush=True)
    if errors:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
