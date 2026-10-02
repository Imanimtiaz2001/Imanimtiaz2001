import io

import pytest
from reportlab.pdfgen import canvas

from clearcv.evidence import verify
from clearcv.examples import make_example
from clearcv.local import extract_local
from clearcv.pdf import PDFError, extract_pdf


@pytest.mark.parametrize(
    "case,expected",
    [
        ("standard", "Maya Chen"),
        ("sidebar", "Maya Chen"),
        ("scanned", "Maya Chen"),
        ("unicode", "Élise Martin"),
        ("year-only", "Maya Chen"),
        ("sparse", "Noor Ali"),
    ],
)
def test_real_pdf_variations(case, expected):
    document = extract_pdf(make_example(case))
    fields = extract_local(document)
    verify(fields, document)
    assert fields.name.value == expected
    assert "Python" in [skill.value for skill in fields.skills]
    if case != "sparse":
        assert len(fields.employment) == 2
        assert len(fields.education) == 1
        assert fields.education[0].institution.value == "Example University"
    else:
        assert fields.education == [] and fields.employment == []
    if case == "scanned":
        assert document.ocr_pages == [1] and all(line.method == "ocr" for line in document.lines)


@pytest.mark.parametrize(
    "data,code", [(b"not a pdf", "invalid_signature"), (b"%PDF-1.7\nbroken", "invalid_pdf")]
)
def test_bad_files(data, code):
    with pytest.raises(PDFError) as exc:
        extract_pdf(data)
    assert exc.value.code == code


def test_page_limit():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for _ in range(3):
        pdf.drawString(50, 700, "Maya Chen Python")
        pdf.showPage()
    pdf.save()
    with pytest.raises(PDFError) as exc:
        extract_pdf(buffer.getvalue(), max_pages=2)
    assert exc.value.code == "too_many_pages"


def test_encrypted_pdf():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, encrypt="secret")
    pdf.drawString(50, 700, "Maya Chen")
    pdf.save()
    with pytest.raises(PDFError) as exc:
        extract_pdf(buffer.getvalue())
    assert exc.value.code == "encrypted_pdf"


def test_blank_pdf():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.showPage()
    pdf.save()
    with pytest.raises(PDFError) as exc:
        extract_pdf(buffer.getvalue())
    assert exc.value.code == "no_text"


def test_text_limit():
    with pytest.raises(PDFError) as exc:
        extract_pdf(make_example("standard"), max_chars=40)
    assert exc.value.code == "too_much_text"


def test_killable_worker_deadline():
    with pytest.raises(PDFError) as exc:
        extract_pdf(make_example("scanned"), timeout=0.001)
    assert exc.value.code == "pdf_timeout"
