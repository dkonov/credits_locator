#!/usr/bin/env python3
"""Extract frame-level credit text and coordinates from locator's report.json."""
import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import pytesseract
from pytesseract import Output

from locator import score, features, ocr

def recognize_lines(frame, lang="rus+eng", min_conf=35):
    """Return lines with normalized bounding boxes and original OCR order."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    data = pytesseract.image_to_data(rgb, lang=lang, config="--psm 11", output_type=Output.DICT)
    grouped = {}
    for i, word in enumerate(data["text"]):
        word = word.strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if not word or conf < min_conf:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        grouped.setdefault(key, []).append((int(data["left"][i]), int(data["top"][i]),
            int(data["width"][i]), int(data["height"][i]), word, conf))
    result = []
    for parts in grouped.values():
        parts.sort(key=lambda x: x[0])
        text = " ".join(x[4] for x in parts)
        if not re.search(r"[A-Za-zА-Яа-яЁё]{2,}", text):
            continue
        x1, y1 = min(p[0] for p in parts), min(p[1] for p in parts)
        x2, y2 = max(p[0] + p[2] for p in parts), max(p[1] + p[3] for p in parts)
        result.append({"text": text, "bbox": [round(x1/w, 5), round(y1/h, 5),
                       round(x2/w, 5), round(y2/h, 5)],
                       "confidence": round(sum(p[5] for p in parts)/len(parts), 1)})
    return sorted(result, key=lambda p: (p["bbox"][1], p["bbox"][0]))

def infer_columns(lines):
    """Use spatially separated text line centers to infer side-by-side columns.
    Conservative: labels are hints; all coordinates are retained for downstream review.
    """
    if len(lines) < 6:
        return 1
    left = sum(1 for item in lines if item["bbox"][2] < .49)
    right = sum(1 for item in lines if item["bbox"][0] > .51)
    return 2 if left >= 3 and right >= 3 else 1

def reading_order(lines):
    n = infer_columns(lines)
    for line in lines:
        box = line["bbox"]
        if n == 2:
            center = (box[0]+box[2])/2
            line["column"] = "left" if center < .5 else "right"
        else:
            line["column"] = "full"
    # Order for reading, while preserving original geometry in bbox.
    return sorted(lines, key=lambda x: (0 if x["column"] in ("left","full") else 1,
                                         x["bbox"][1], x["bbox"][0])), n

def normalized(text):
    return re.sub(r"[^a-zа-яё0-9]+", "", text.casefold())

def consolidate(frames, minimum_similarity=.90):
    """Keep first occurrence of a line; aggregate evidence across sampled frames.
    This is a non-destructive index: every frame and line remains in 'frames'.
    """
    items = []
    for frame in frames:
        for line in frame["lines"]:
            key = normalized(line["text"])
            if len(key) < 4:
                continue
            match = None
            for existing in reversed(items):
                # Skip near-duplicates only when columns agree.
                if existing["column"] != line["column"]:
                    continue
                if abs(frame["time_sec"] - existing["last_seen_sec"]) > 12:
                    continue
                similarity = SequenceMatcher(None, key, normalized(existing["text"])).ratio()
                if similarity >= minimum_similarity:
                    match = existing
                    break
            if match:
                match["last_seen_sec"] = frame["time_sec"]
                match["observations"] += 1
                if line["confidence"] > match["best_confidence"]:
                    match["text"] = line["text"]
                    match["best_confidence"] = line["confidence"]
                    match["bbox"] = line["bbox"]
            else:
                items.append({"text": line["text"], "column": line["column"],
                    "bbox": line["bbox"], "first_seen_sec": frame["time_sec"],
                    "last_seen_sec": frame["time_sec"], "observations": 1,
                    "best_confidence": line["confidence"]})
    return items

def read_frame(cap, second, width):
    cap.set(cv2.CAP_PROP_POS_MSEC, second*1000)
    ok, frame = cap.read()
    if not ok:
        return None
    h, w = frame.shape[:2]
    if w > width:
        frame = cv2.resize(frame, (width, round(h*width/w)), interpolation=cv2.INTER_AREA)
    return frame

def refine_boundaries(cap, interval, duration, args):
    """Probe within a small margin; boundaries are sampled estimates, not frame-exact."""
    begin, end = float(interval["start_sec"]), float(interval["end_sec"])
    seek_begin = max(0, begin-args.boundary_margin)
    seek_end = min(duration, end+args.boundary_margin)
    positives = []
    second = seek_begin
    while second < seek_end:
        frame = read_frame(cap, second, args.width)
        if frame is not None:
            evidence = ocr(frame, args.lang)
            if score(features(frame), evidence) >= args.threshold:
                positives.append(second)
        second += args.boundary_step
    if not positives:
        return {"start_sec": begin, "end_sec": end, "refined": False}
    return {"start_sec": round(max(0, min(positives)-args.boundary_step), 2),
            "end_sec": round(min(duration, max(positives)+args.boundary_step), 2),
            "refined": True, "positive_boundary_probes": len(positives)}

def extract(video, report_path, args):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = cap.get(cv2.CAP_PROP_FRAME_COUNT)/fps if fps > 0 else report.get("duration_sec", 0)
    result = {"video": str(video), "source_report": str(report_path),
              "method": "coordinate OCR + frame-level evidence; role mapping not verified",
              "intervals": []}
    try:
        for interval in report["intervals"]:
            bounds = refine_boundaries(cap, interval, duration, args)
            frames = []
            t = bounds["start_sec"]
            while t < bounds["end_sec"]:
                frame = read_frame(cap, t, args.width)
                if frame is not None:
                    lines, ncol = reading_order(recognize_lines(frame, args.lang, args.min_conf))
                    frames.append({"time_sec": round(t, 2), "columns_detected": ncol,
                                   "lines": lines})
                t += args.step
            result["intervals"].append({"locator_interval": interval,
                  "boundary_estimate": bounds, "frames": frames,
                  "merged_lines": consolidate(frames)})
    finally:
        cap.release()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.output} ({sum(len(x['frames']) for x in result['intervals'])} frames)")

def main():
    ap = argparse.ArgumentParser(description="Credits Locator v0.3: coordinate-aware OCR")
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--step", type=float, default=1.0)
    ap.add_argument("--boundary-step", type=float, default=.5)
    ap.add_argument("--boundary-margin", type=float, default=7)
    ap.add_argument("--threshold", type=float, default=.6)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--min-conf", type=float, default=35)
    ap.add_argument("--lang", default="rus+eng")
    args = ap.parse_args()
    if args.step <= 0 or args.boundary_step <= 0:
        ap.error("Steps must be positive")
    extract(args.video, args.report, args)

if __name__ == "__main__":
    main()
