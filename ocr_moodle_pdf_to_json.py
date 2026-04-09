import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pdf2image import convert_from_path
from PIL import ImageOps


QUESTION_START_RE = re.compile(r"\bQuestion\s+\d+\b", re.IGNORECASE)
QUESTION_SPLIT_RE = re.compile(r"(?=\bQuestion\s+\d+\b)", re.IGNORECASE)
CHOICE_RE = re.compile(r"^\s*([abcd])\s*[\.\):]\s*(.+?)\s*$", re.IGNORECASE)
CORRECT_RE = re.compile(r"The\s+correct\s+answer\s+is\s*:\s*(.+)", re.IGNORECASE)


@dataclass
class ParseResult:
    question: dict[str, Any]
    malformed: bool
    unmatched_correct: bool
    reason: str | None


def normalize_spaces(text: str) -> str:
    cleaned = text.replace("\x0c", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\s*\n\s*", "\n", cleaned)
    return cleaned.strip()


def normalize_for_match(text: str) -> str:
    normalized = normalize_spaces(text).lower()
    normalized = re.sub(r"[^a-z0-9 ]+", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def sanitize_title_dir_name(title: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*]', "_", title.strip())
    safe = re.sub(r"\s+", " ", safe).strip().rstrip(".")
    return safe or "untitled_quiz"


def preprocess_image(image):
    gray = ImageOps.grayscale(image)
    # Simple thresholding improves OCR in lightly colored answer boxes.
    return gray.point(lambda p: 255 if p > 175 else 0)


def try_ocr_with_pytesseract(image) -> str:
    try:
        import pytesseract
    except Exception:
        return ""
    try:
        return pytesseract.image_to_string(image)
    except Exception:
        return ""


def try_ocr_with_easyocr(image) -> str:
    try:
        import easyocr
    except Exception:
        return ""
    try:
        reader = easyocr.Reader(["en"], gpu=False)
        chunks = reader.readtext(image, detail=0, paragraph=True)
        return "\n".join(chunks)
    except Exception:
        return ""


def is_useful_text(text: str) -> bool:
    if not text:
        return False
    compact = re.sub(r"\s+", "", text)
    return len(compact) > 20


def split_question_blocks(page_text: str) -> list[str]:
    if not QUESTION_START_RE.search(page_text):
        return []
    parts = [p.strip() for p in QUESTION_SPLIT_RE.split(page_text) if p.strip()]
    blocks: list[str] = []
    for part in parts:
        if part.lower().startswith("question"):
            blocks.append(part)
    return blocks


def extract_question_text(block: str) -> str:
    marker = re.search(r"Select\s+one\s*:", block, re.IGNORECASE)
    if not marker:
        return ""
    prefix = block[: marker.start()]
    prefix = re.sub(r"^\s*Question\s+\d+\s*", "", prefix, flags=re.IGNORECASE)
    return normalize_spaces(prefix)


def parse_choices(block: str) -> list[str]:
    choices: list[str] = []
    for line in block.splitlines():
        match = CHOICE_RE.match(line.strip())
        if match:
            choice_text = normalize_spaces(match.group(2))
            choices.append(choice_text)
    # Keep first four only for Moodle-style select-one blocks.
    return choices[:4]


def extract_correct_answer_text(block: str) -> str:
    for line in block.splitlines():
        match = CORRECT_RE.search(line)
        if match:
            return normalize_spaces(match.group(1))
    return ""


def reverse_lookup_correct_index(correct_text: str, choices: list[str]) -> int:
    if not correct_text or not choices:
        return -1

    target = normalize_for_match(correct_text)
    normalized_choices = [normalize_for_match(c) for c in choices]
    if target in normalized_choices:
        return normalized_choices.index(target)

    # Fallback: containment match for minor OCR omissions.
    for idx, candidate in enumerate(normalized_choices):
        if target and (target in candidate or candidate in target):
            return idx
    return -1


def parse_question_block(block: str) -> ParseResult:
    question_text = extract_question_text(block)
    choices = parse_choices(block)
    correct_text = extract_correct_answer_text(block)
    correct_index = reverse_lookup_correct_index(correct_text, choices)

    malformed_reasons: list[str] = []
    unmatched = False
    if not question_text:
        malformed_reasons.append("missing question text")
    if len(choices) < 2:
        malformed_reasons.append("insufficient choices")
    if not correct_text:
        malformed_reasons.append("missing answer block")
    elif correct_index < 0:
        unmatched = True
        malformed_reasons.append("correct answer text unmatched")

    return ParseResult(
        question={
            "question": question_text,
            "choices": choices,
            "correct": correct_index,
            "points": 1,
        },
        malformed=bool(malformed_reasons),
        unmatched_correct=unmatched,
        reason=", ".join(malformed_reasons) if malformed_reasons else None,
    )


def extract_questions_from_pdf(pdf_path: Path, dpi: int, verbose: bool) -> tuple[list[tuple[dict[str, Any], str, int, str | None]], dict[str, int]]:
    stats = {
        "parsed": 0,
        "malformed": 0,
        "unmatched_correct": 0,
    }
    parsed_entries: list[tuple[dict[str, Any], str, int, str | None]] = []

    images = convert_from_path(str(pdf_path), dpi=dpi)
    for page_num, image in enumerate(images, start=1):
        processed = preprocess_image(image)
        text = try_ocr_with_pytesseract(processed)
        engine = "pytesseract"

        if not is_useful_text(text):
            fallback = try_ocr_with_easyocr(processed)
            if is_useful_text(fallback):
                text = fallback
                engine = "easyocr"

        if verbose:
            print(f"[OCR] {pdf_path.name} page {page_num}: {engine}")

        blocks = split_question_blocks(normalize_spaces(text))
        for block in blocks:
            result = parse_question_block(block)
            parsed_entries.append((result.question, pdf_path.name, page_num, result.reason))
            stats["parsed"] += 1
            if result.malformed:
                stats["malformed"] += 1
            if result.unmatched_correct:
                stats["unmatched_correct"] += 1

    return parsed_entries, stats


def dedupe_questions(items: list[tuple[dict[str, Any], str, int, str | None]]) -> tuple[list[dict[str, Any]], int]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    duplicates = 0
    for question_obj, _, _, _ in items:
        key = normalize_for_match(question_obj.get("question", ""))
        if not key:
            key = f"__empty__{len(deduped)}"
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        deduped.append(question_obj)
    return deduped, duplicates


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR Moodle PDF to JSON parser.")
    parser.add_argument("--pdf-dir", default="pdf", help="Directory containing source PDFs.")
    parser.add_argument("--dpi", default=300, type=int, help="Render DPI for OCR (default: 300).")
    parser.add_argument("--verbose", action="store_true", help="Print OCR engine and extra logs.")
    args = parser.parse_args()

    title = input("Enter quiz title: ").strip()
    if not title:
        print("Error: Title is required.")
        return 1

    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists() or not pdf_dir.is_dir():
        print(f"Error: PDF directory not found: {pdf_dir}")
        return 1

    pdf_files = sorted([p for p in pdf_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])
    if not pdf_files:
        print(f"Error: No PDF files found in {pdf_dir}")
        return 1

    all_items: list[tuple[dict[str, Any], str, int, str | None]] = []
    totals = {
        "parsed": 0,
        "malformed": 0,
        "unmatched_correct": 0,
    }

    for pdf_file in pdf_files:
        try:
            entries, stats = extract_questions_from_pdf(pdf_file, args.dpi, args.verbose)
            all_items.extend(entries)
            for k in totals:
                totals[k] += stats[k]
        except Exception as exc:
            print(f"[ERROR] Failed to process {pdf_file.name}: {exc}")

    if not all_items:
        print("Error: No question blocks were extracted from provided PDFs.")
        return 1

    for question_obj, source_pdf, page_num, reason in all_items:
        if reason:
            snippet = question_obj.get("question", "").strip()[:100] or "(empty question text)"
            print(f"[REVIEW] {source_pdf} page {page_num}: {reason} | {snippet}")

    deduped_questions, duplicates_removed = dedupe_questions(all_items)

    output_data = {
        "title": title,
        "questions": deduped_questions,
    }

    output_dir = Path(sanitize_title_dir_name(title))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "output.json"

    try:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Error: Failed to write output file: {exc}")
        return 1

    print("\nDone.")
    print(f"Output: {output_path}")
    print("Summary:")
    print(f"  Parsed blocks: {totals['parsed']}")
    print(f"  Malformed blocks: {totals['malformed']}")
    print(f"  Unmatched correct answers: {totals['unmatched_correct']}")
    print(f"  Duplicates removed: {duplicates_removed}")
    print(f"  Final questions: {len(deduped_questions)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
