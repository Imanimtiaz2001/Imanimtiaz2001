"""Bounded extraction in a killable child, with coordinate-aware reading order."""

import io
import math
import multiprocessing as mp
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from clearcv.schemas import Document, SourceLine


class PDFError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _rows(words: list[dict]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1][0]["top"] - word["top"]) < 4:
            rows[-1].append(word)
        else:
            rows.append([word])
    return [sorted(row, key=lambda w: w["x0"]) for row in rows]


def _ordered_rows(words: list[dict], width: float) -> list[list[dict]]:
    rows = _rows(words)
    candidates: list[tuple[float, float]] = []
    for row in rows:
        if row[0]["top"] < 100:
            continue
        for left, right in zip(row, row[1:], strict=False):
            if right["x0"] - left["x1"] > 40:
                a, b = left["x1"] + 5, right["x0"] - 5
                if a < width * 0.75 and b > width * 0.25:
                    candidates.append((a, b))
    # A persistent gutter across at least four rows; titles can span it.
    splits = [x for x in range(int(width * 0.25), int(width * 0.75), 5)]
    scores = {x: sum(a < x < b for a, b in candidates) for x in splits}
    best = max(scores.values(), default=0)
    best_splits = [x for x, score in scores.items() if score == best]
    split = (min(best_splits) + max(best_splits)) / 2 if best_splits else 0
    if sum(a < split < b for a, b in candidates) < 4:
        return rows
    left_words = [w for w in words if w["x1"] <= split]
    right_words = [w for w in words if w["x0"] >= split]
    if len(left_words) < 8 or len(right_words) < 8:
        return rows
    header, left, right = [], [], []
    for row in rows:
        if row[0]["top"] < 100:
            header.append(row)
        else:
            left_row = [w for w in row if (w["x0"] + w["x1"]) / 2 < split]
            right_row = [w for w in row if (w["x0"] + w["x1"]) / 2 >= split]
            if left_row:
                left.append(left_row)
            if right_row:
                right.append(right_row)
    return header + left + right


def _ocr(data: bytes, page_index: int, language: str) -> str:
    import pypdfium2 as pdfium

    if not shutil.which("tesseract"):
        raise PDFError("ocr_unavailable", "Scanned PDF requires the Tesseract OCR executable.")
    with pdfium.PdfDocument(data) as pdf:
        page = pdf[page_index]
        w, h = page.get_size()
        if w <= 0 or h <= 0 or w * h > 100_000_000:
            raise PDFError("page_dimensions", "PDF page dimensions exceed safe rendering limits.")
        scale = min(2.5, math.sqrt(12_000_000 / (w * h)))
        bitmap = page.render(scale=scale)
        try:
            image = bitmap.to_pil()
            with tempfile.TemporaryDirectory(prefix="clearcv-ocr-") as temp:
                path = Path(temp) / "page.png"
                image.save(path)
                try:
                    result = subprocess.run(
                        ["tesseract", str(path), "stdout", "-l", language, "--psm", "3"],
                        capture_output=True,
                        timeout=20,
                        check=False,
                        env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                    )
                except subprocess.TimeoutExpired as exc:
                    raise PDFError(
                        "ocr_timeout", "OCR timed out; use a smaller or text-based PDF."
                    ) from exc
                if result.returncode:
                    raise PDFError("ocr_failed", "OCR failed; check the configured language packs.")
                return result.stdout.decode("utf-8", errors="replace")
        finally:
            bitmap.close()
            page.close()


def _extract(data: bytes, max_pages: int, max_chars: int, language: str) -> Document:
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    lines, ocr_pages, warnings = [], [], []
    total_chars = 0
    try:
        with pdfplumber.open(io.BytesIO(data), unicode_norm="NFKC") as pdf:
            if len(pdf.pages) > max_pages:
                raise PDFError("too_many_pages", f"PDF exceeds the {max_pages}-page limit.")
            if not pdf.pages:
                raise PDFError("empty_pdf", "PDF has no pages.")
            for index, page in enumerate(pdf.pages):
                if len(page.chars) > 100000:
                    raise PDFError("too_much_text", "PDF contains too many text objects.")
                words = page.extract_words(x_tolerance=2, y_tolerance=3)
                rows = _ordered_rows(words, page.width)
                extracted = [
                    (
                        " ".join(w["text"] for w in row),
                        [
                            float(min(w["x0"] for w in row)),
                            float(min(w["top"] for w in row)),
                            float(max(w["x1"] for w in row)),
                            float(max(w["bottom"] for w in row)),
                        ],
                    )
                    for row in rows
                ]
                method = "text"
                if sum(len(text) for text, _ in extracted) < 20:
                    text = _ocr(data, index, language)
                    extracted = [(line.strip(), None) for line in text.splitlines() if line.strip()]
                    method = "ocr"
                    ocr_pages.append(index + 1)
                if not extracted:
                    warnings.append(f"Page {index + 1} has no readable text.")
                for text, bbox in extracted:
                    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text).strip()
                    if not text:
                        continue
                    total_chars += len(text)
                    if total_chars > max_chars or len(lines) >= 3000:
                        raise PDFError(
                            "too_much_text", "Extracted text exceeds the document limit."
                        )
                    lines.append(
                        SourceLine(
                            id=f"p{index + 1}-l{len(lines) + 1}",
                            page=index + 1,
                            text=text,
                            bbox=bbox,
                            method=method,
                        )
                    )
                page.close()
            if not lines:
                raise PDFError("no_text", "No readable text was found, including after OCR.")
            if ocr_pages:
                warnings.append(
                    "OCR was used. Verify spelling, names and dates against the original PDF."
                )
            return Document(
                lines=lines, page_count=len(pdf.pages), ocr_pages=ocr_pages, warnings=warnings
            )
    except (PDFPasswordIncorrect, pdfplumber.utils.exceptions.PdfminerException) as exc:
        if not isinstance(exc, PDFPasswordIncorrect) and not isinstance(
            exc.args[0] if exc.args else None, PDFPasswordIncorrect
        ):
            raise
        raise PDFError(
            "encrypted_pdf", "Password-protected PDFs are not supported; upload an unlocked copy."
        ) from exc


def _worker(connection, data: bytes, max_pages: int, max_chars: int, language: str, timeout: int):
    try:
        # Unix defense in depth. Windows still has the parent deadline and input bounds.
        if os.name == "posix":
            import resource

            resource.setrlimit(
                resource.RLIMIT_CPU, (max(1, math.ceil(timeout)), max(1, math.ceil(timeout)) + 1)
            )
            resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024,) * 2)
        document = _extract(data, max_pages, max_chars, language)
        connection.send({"ok": document.model_dump()})
    except PDFError as exc:
        connection.send({"error": exc.code, "message": str(exc)})
    except Exception:
        connection.send(
            {
                "error": "invalid_pdf",
                "message": "PDF could not be read safely. Upload a valid, unlocked PDF.",
            }
        )
    finally:
        connection.close()


def extract_pdf(
    data: bytes,
    *,
    max_pages: int = 10,
    max_chars: int = 60000,
    language: str = "eng",
    timeout: int = 60,
) -> Document:
    if not data.startswith(b"%PDF-"):
        raise PDFError("invalid_signature", "File must be a PDF with a valid PDF signature.")
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_worker, args=(sender, data, max_pages, max_chars, language, timeout)
    )
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout):
            raise PDFError("pdf_timeout", "PDF extraction timed out. Use a smaller or simpler PDF.")
        try:
            payload = receiver.recv()
        except EOFError as exc:
            raise PDFError(
                "pdf_worker_failed", "PDF extraction exceeded worker resource limits."
            ) from exc
        if "error" in payload:
            raise PDFError(payload["error"], payload["message"])
        return Document.model_validate(payload["ok"])
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join(timeout=2)
