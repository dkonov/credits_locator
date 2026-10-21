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
