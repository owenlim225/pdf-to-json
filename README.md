# PDF to JSON

Specification and project index for a skill-driven PDF processing workspace.

## Purpose

This repository is a local PDF-processing workspace centered on converting PDF content and form structures into structured JSON, validating extracted geometry, and writing data back into PDFs when needed.

The project currently uses skill assets under `.agents/skills` as its primary implementation surface, plus a main JSON template at the repository root.

## Scope

- Extract structured information from PDFs into JSON (text labels, field metadata, geometry).
- Support both fillable and non-fillable PDFs.
- Validate field bounding boxes and annotation placement before output generation.
- Fill fillable PDF fields from JSON values.
- Fill non-fillable PDFs using text annotations derived from JSON + coordinates.
- Convert PDF pages to images for visual validation workflows.

## Repository Index

```text
.
|-- .agents/
|   `-- skills/
|       |-- pdf/
|       |   |-- SKILL.md
|       |   |-- forms.md
|       |   |-- reference.md
|       |   |-- LICENSE.txt
|       |   `-- scripts/
|       |       |-- check_bounding_boxes.py
|       |       |-- check_fillable_fields.py
|       |       |-- convert_pdf_to_images.py
|       |       |-- create_validation_image.py
|       |       |-- extract_form_field_info.py
|       |       |-- extract_form_structure.py
|       |       |-- fill_fillable_fields.py
|       |       `-- fill_pdf_form_with_annotations.py
|       `-- pdftk-server/
|           |-- SKILL.md
|           `-- references/
|               |-- download.md
|               |-- pdftk-cli-examples.md
|               |-- pdftk-man-page.md
|               |-- pdftk-server-license.md
|               `-- third-party-materials.md
|-- skills-lock.json
`-- example.json
```

## Core Components

### 1) Skill Definitions (`.agents/skills`)

- `pdf` skill:
  - General PDF operations via Python libraries and CLI tools.
  - Includes practical scripts for form extraction, validation, and filling.
- `pdftk-server` skill:
  - CLI-first workflows for merge/split/rotate/encrypt/decrypt/fill/stamp/watermark.
  - Includes reference docs and examples for command usage.

### 2) PDF Processing Scripts (`.agents/skills/pdf/scripts`)

- `check_fillable_fields.py`  
  Detects whether a PDF exposes fillable AcroForm fields.

- `extract_form_field_info.py`  
  Reads fillable field definitions with field IDs, field type, page, and rectangle coordinates.

- `fill_fillable_fields.py`  
  Validates user-provided JSON values against extracted field metadata and fills form fields.

- `extract_form_structure.py`  
  For non-fillable PDFs, extracts words/lines/checkbox-like rectangles to produce structural JSON.

- `fill_pdf_form_with_annotations.py`  
  Writes non-fillable form values as PDF text annotations using either image-space or PDF-space coordinates.

- `check_bounding_boxes.py`  
  Detects overlapping bounding boxes and text-fit issues based on font size versus box height.

- `convert_pdf_to_images.py`  
  Renders pages to PNG for visual QA or coordinate design workflows.

- `create_validation_image.py`  
  Overlays entry and label rectangles on page image snapshots for fast visual validation.

### 3) Workspace Metadata

- `skills-lock.json` tracks installed skill sources and content hashes.

### 4) Main Template Data (`example.json`)

- `example.json` is the main template for succeeding instructions and demonstrates quiz-style structured JSON:
  - Root keys: `title`, `questions`
  - Question fields: `question`, `choices[]`, `correct`, `points`

Template usage convention:

- Treat `example.json` as the canonical schema reference when creating new JSON outputs.
- Keep key names and field types aligned with this template unless a new schema version is explicitly introduced.

## Functional Specification

## A. Fillable PDF Flow

1. Detect fields:
   - Input: `input.pdf`
   - Command: `python check_fillable_fields.py input.pdf`
2. Extract field metadata:
   - Output JSON: list of field objects with IDs/types/page/rect
3. Prepare values JSON:
   - Must match `field_id` and `page`
   - Must use valid field values for checkbox/radio/choice types
4. Fill and write output:
   - Command: `python fill_fillable_fields.py input.pdf field_values.json output.pdf`
5. Validate visually in a PDF viewer.

## B. Non-Fillable PDF Flow

1. Extract page structure:
   - Command: `python extract_form_structure.py input.pdf structure.json`
2. Convert pages to images for coordinate work:
   - Command: `python convert_pdf_to_images.py input.pdf output_dir`
3. Build `fields.json` with `form_fields`, bounding boxes, and optional text styles.
4. Validate geometry:
   - Command: `python check_bounding_boxes.py fields.json`
5. Optional validation preview:
   - Command: `python create_validation_image.py <page> fields.json page.png validation.png`
6. Write annotations into output PDF:
   - Command: `python fill_pdf_form_with_annotations.py input.pdf fields.json output.pdf`

## Data Contracts

### Field values input (fillable flow)

Expected array entries include:

- `field_id`: string, must match extracted field ID
- `page`: integer, must match extracted field page
- `value`: valid value for the field type

Validation rules enforced:

- Unknown `field_id` is rejected.
- Incorrect `page` is rejected.
- Invalid `value` for checkbox/radio/choice is rejected.

### Non-fillable fields file (`fields.json`)

Expected top-level keys used by scripts:

- `pages`: page metadata
- `form_fields`: list with each item containing:
  - `description`
  - `page_number`
  - `label_bounding_box` `[x0, y0, x1, y1]`
  - `entry_bounding_box` `[x0, y0, x1, y1]`
  - optional `entry_text` (`text`, `font`, `font_size`, `font_color`)

Coordinate handling:

- If `pages[*]` includes PDF dimensions, direct PDF coordinate transform is used.
- Otherwise image dimensions are used to scale to PDF coordinates.

## Non-Functional Requirements

- Deterministic JSON output formatting (`json.dump(..., indent=2)` in scripts).
- Validation-first behavior to fail early on invalid field IDs/pages/values.
- Script-level usability through simple CLI argument contracts.
- Cross-platform support targeted via Python and common PDF libraries.

## Dependencies

Primary Python libraries used by scripts:

- `pypdf`
- `pdfplumber`
- `pdf2image`
- `Pillow` (`PIL`)

Optional toolchain from skill docs:

- `pdftk` / `pdftk-java`
- `qpdf`
- `pdftotext` (Poppler)
- OCR stack (`pytesseract`, `pdf2image`, Tesseract binary)

## Environment Setup

1. Create and activate a Python virtual environment.
2. Install required packages:

```bash
pip install pypdf pdfplumber pdf2image pillow
```

3. For image conversion, install Poppler tools and ensure they are on system PATH.
4. For CLI PDF workflows, install `pdftk` and/or `qpdf` as needed.

## Operational Conventions

- Keep generated JSON files under a dedicated output folder (recommended: `outputs/`).
- Keep source PDFs immutable; always write to new output filenames.
- Validate bounding boxes before annotation fill on non-fillable forms.
- Preserve field IDs exactly as extracted for fillable forms.

## Current State and Gaps

Current state:

- The repository is a skill-centric workspace with working utility scripts.
- No application entrypoint, package manifest, or automated tests are defined at root.

Gaps to reach a production-ready "PDF to JSON app":

- Add a root Python package (`src/`) and orchestration CLI.
- Add `requirements.txt` or `pyproject.toml`.
- Add unit/integration tests for extraction and fill flows.
- Add sample input/output fixtures for repeatable QA.
- Add CI for linting, type checks, and test execution.

## Recommended Next Milestones

1. Build a unified CLI wrapper:
   - `pdf2json extract ...`
   - `pdf2json validate ...`
   - `pdf2json fill ...`
2. Standardize JSON schemas (with versioning) for:
   - extracted structure
   - fillable field metadata
   - field value payloads
3. Add schema validation (e.g., `jsonschema`) before script execution.
4. Add regression tests with fixture PDFs.
5. Document supported PDF edge cases and known limitations.

## License and Source Notes

- Skill content references proprietary and third-party materials:
  - `.agents/skills/pdf/LICENSE.txt`
  - `.agents/skills/pdftk-server/references/pdftk-server-license.md`
  - `.agents/skills/pdftk-server/references/third-party-materials.md`

Review those files before redistribution of skill-derived assets.