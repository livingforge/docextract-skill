---
name: docextract
description: Extract text, tables, and images from Office documents (docx/xlsx/pptx) and PDF into structured JSON, with OCR for image-embedded text and reconstruction of tables pasted as pictures. Use when asked to "parse / extract / convert / 解析 / 抽出 / 構造化" the contents of Word, Excel, PowerPoint, or PDF files. Requires Python 3.10+.
---

# docextract

Parse Office documents (Word / Excel / PowerPoint) and PDF into structured JSON
of **text, tables, and images**. What sets it apart is capturing content that
exists only as pixels:

- Text inside images / screenshots → **OCR** (RapidOCR), attached as `ocr_text`
- Tables pasted as pictures → **detected and reconstructed** (rapid_layout +
  rapid_table) into ordinary `table` elements (2-D arrays)

All dependencies are OSS cleared for commercial use (MIT / BSD / Apache-2.0);
see [package-meta/docextract/dependencies.md](../../package-meta/docextract/dependencies.md).

## Setup (automatic)

No manual install. The first run of `run_docextract.py` / `run_docagent.py`
bootstraps a shared `.venv` at the project root with [uv](https://docs.astral.sh/uv/),
installs `requirements.txt`, and re-executes there; later runs start instantly.

- `uv` is auto-installed on first use if missing (set `DOCEXTRACT_NO_UV_AUTOINSTALL=1`
  to opt out and install it yourself)
- OCR / table-detection models (tens of MB) download into `.venv` on first run
- For fully offline use, run once online to warm the cache, or use
  `--ocr-backend windows` (Windows only, built-in OCR)

## Usage

Run **from the project root** — never `cd` into the scripts directory; the
launcher is cwd-independent. Paths below are relative to the project root.

```bash
python .github/skills/docextract/scripts/run_docextract.py <files...> -o <output-dir>
python .github/skills/docextract/scripts/run_docextract.py --dir <folder> -o <output-dir>     # batch a folder
python .github/skills/docextract/scripts/run_docextract.py --dir <folder> -r -o <output-dir>  # recurse
```

- Formats: `.docx` `.xlsx` `.xlsm` `.pptx` `.pdf` (wildcards ok)
- Each input yields `<output-dir>/<id>/` containing `result.json` and `images/`, where
  `<id>` embeds a hash of the file's absolute path so same-named files in different
  folders never collide. A manifest `<output-dir>/index.json` indexes all extractions by id.
- `-d/--dir` (repeatable) batches every supported file in a folder; `-r` recurses.
  Office temp files (`~$…`) are skipped
- Other flags: `--no-ocr`, `--no-image-tables`, `--ocr-lang ja`,
  `--ocr-backend auto|rapidocr|windows`

Work with extracted results through the same launcher:
`python .github/skills/docextract/scripts/run_docagent.py <subcommand>`.

Python API:

```python
import sys; sys.path.insert(0, r".github/skills/docextract/scripts")
from docextract import extract
data = extract("report.docx", output_dir="out")   # returns a dict, also writes result.json
```

## Output

`elements` lists the document's contents in reading order. Three types:

| type | content | key fields |
|------|---------|-----------|
| `text` | paragraphs, headings, text boxes | `content`, `style`, `location` |
| `table` | tables (2-D array) | `rows`, `n_rows`, `n_cols`, `location` |
| `image` | reference to an extracted image | `file`, `ocr_text`, `width`, `height`, `location` |

`location` is format-specific: docx=`order`, xlsx=`sheet`, pptx=`slide`,
pdf=`page`+`bbox`. Tables detected inside images add `from_image` and
`bbox_in_image`. `summary` holds per-type counts; `metadata` holds title,
author, etc.

Full schema: [docs/output-schema.md](docs/output-schema.md). CLI reference, OCR
backends, self-test, and troubleshooting: [docs/usage.md](docs/usage.md).

## Limitations (surface these to the user)

- PDF table detection is ruling-based (pdfplumber); borderless tables may be missed
- Image tables recover row/column structure, but merged cells are padded with
  empty strings across the span
- Legacy formats (`.doc` `.xls` `.ppt`) are unsupported — advise converting first
- OCR is imperfect; note that hard-to-read images may yield noisy text
