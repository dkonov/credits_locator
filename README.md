# Credits Locator (v0.2)

Local pilot for finding opening and ending credits in compressed full-length video. Uses sparse frame sampling, OpenCV, Tesseract OCR, and a conservative lexical/visual score. **No paid APIs or movie downloads.**

## Start (Linux + Docker)

```bash
mkdir -p input output
# Put .mp4/.mkv/.mov files in input/
docker compose build
docker compose run --rm locator
```

To refine boundaries (slower):

```bash
docker compose run --rm locator --input /data/input --output /data/output --refine
```

Results per movie in `output/<movie-stem>/`:
- `report.json`: candidate credit intervals, diagnostic OCR samples
- `samples.csv`: scores, OCR quality fields, extracted text
- `contact_sheet.jpg` and `frame_*.jpg`: evidence images

## What changed since v0.1

- OCR nonsense no longer scores highly from line counts alone.
- Russian credit keywords match inflected words (e.g. «режиссёр», «оператора»).
- Multiple corroborating frames are required by default (`--min-hits 2`).
- Dark, multi-line layouts can be detected without a dictionary match.
- `--refine` samples around confirmed hits, not around expanded intervals.
- File processing errors now return a nonzero exit code.

## Limitations

Sparse sampling can miss very short cards. Scores are **not calibrated probabilities**; the tool is not a definitive credits recognizer. The current implementation may reject genuine credits over moving backgrounds. Intervals are approximate. Keep original films locally; no video is committed to Git.

## Tune

`--edge-step 2 --middle-step 5`: denser search. `--threshold 0.6`: minimum score. `--padding 5`: seconds around hits. `--lang rus+eng`: installed OCR languages. `--min-hits 1`: less strict, higher false-positive risk.

## Test

```bash
python -m unittest discover -s tests -v
```

Requires Python dependencies listed in `requirements.txt`.


## v0.3 — frame-level credits extraction

Run the existing locator first, then run the **separate extractor**. It keeps the
v0.2 detection behavior unchanged and does not require any cloud API.

```bash
docker compose build
docker compose run --rm --entrypoint python locator /app/extract_credits.py \
  --video /data/input/za_steklom.mov \
  --report /data/output/za_steklom/report.json \
  --output /data/output/za_steklom/credits_raw.json \
  --step 1 --boundary-step 0.5
```

The extractor generates:
- `boundary_estimate`: OCR-based boundary refinement (approximate, not frame-exact);
- `frames[].lines[]`: full OCR text, confidence, **normalized bounding box**
  `[left, top, right, bottom]`, and a tentative column label;
- `merged_lines[]`: deduplicated lines and timestamps of first/last observation.

All original frame-level results are preserved even if the merge is wrong.
Two-column detection is a *heuristic*; it does not yet associate people with
their film jobs. Running `--step 0.5` improves coverage at additional cost.
`--width 1920` avoids downsizing HD frames, but cannot reconstruct detail lost
in a highly compressed source. No LLM is used in this release.

Run Python tests using `python -m unittest discover -s tests -v`.
