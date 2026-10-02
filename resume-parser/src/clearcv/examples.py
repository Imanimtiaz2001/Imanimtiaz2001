"""Synthetic fixtures only. No real candidate data is shipped."""

import io
from pathlib import Path

from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

CASES = ("standard", "sidebar", "scanned", "unicode", "year-only", "sparse")
FONT_PATH = Path(__import__("reportlab").__file__).parent / "fonts" / "Vera.ttf"
if "ClearCVVera" not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont("ClearCVVera", str(FONT_PATH)))


def make_example(case: str) -> bytes:
    if case not in CASES:
        raise ValueError("Unknown example")
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(612, 792), invariant=1)
    pdf.setTitle(f"Synthetic ClearCV resume: {case}")
    pdf.setFont("ClearCVVera", 11)

    def line(text, x=48, y=740, size=11):
        pdf.setFont("ClearCVVera", size)
        pdf.drawString(x, y, text)

    if case == "scanned":
        import pypdfium2 as pdfium

        with pdfium.PdfDocument(make_example("standard")) as source:
            page = source[0]
            bitmap = page.render(scale=2.5)
            try:
                pdf.drawImage(ImageReader(bitmap.to_pil()), 0, 0, width=612, height=792)
            finally:
                bitmap.close()
                page.close()
    elif case == "sidebar":
        line("Maya Chen", size=25)
        line("AI Engineer", y=710, size=13)
        left = [
            "SKILLS",
            "Python",
            "FastAPI",
            "PostgreSQL",
            "Docker",
            "PyTorch",
            "EDUCATION",
            "BS Computer Science",
            "Example University",
            "2020",
        ]
        right = [
            "EXPERIENCE",
            "ML Engineer | Northstar Labs",
            "Jan 2021 - Dec 2023",
            "Built Python extraction services.",
            "Consultant | Orbit Systems",
            "Jan 2023 - Present",
            "Designed FastAPI data pipelines.",
        ]
        for i, text in enumerate(left):
            line(text, x=48, y=650 - i * 28)
        for i, text in enumerate(right):
            line(text, x=282, y=650 - i * 28)
    elif case == "sparse":
        line("Name: Noor Ali", size=19)
        line("SKILLS", y=680)
        line("Python", y=650)
    else:
        name = "Élise Martin" if case == "unicode" else "Maya Chen"
        rows = [
            name,
            "AI Engineer",
            "maya@example.invalid",
            "SKILLS",
            "Python, FastAPI, PostgreSQL, Docker, PyTorch",
            "EXPERIENCE",
            "ML Engineer | Northstar Labs",
            "2021 - 2023" if case == "year-only" else "Jan 2021 - Dec 2023",
            "Built reliable document extraction pipelines.",
            "Consultant | Orbit Systems",
            "2023 - Present" if case == "year-only" else "Jan 2023 - Present",
            "Designed evidence-grounded AI services.",
            "EDUCATION",
            "BS Computer Science | Example University | 2020",
        ]
        for i, text in enumerate(rows):
            line(text, y=740 - i * 32, size=25 if i == 0 else 11)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
