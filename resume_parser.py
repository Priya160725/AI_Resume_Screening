import pymupdf
import os


def extract_resume_text(filepath):

    text = ""

    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"File not found: {filepath}"
        )

    # PDF files
    if filepath.lower().endswith(".pdf"):

        document = pymupdf.open(filepath)

        for page in document:
            text += page.get_text()

        document.close()

    # DOCX files
    elif filepath.lower().endswith(".docx"):

        from docx import Document

        document = Document(filepath)

        for paragraph in document.paragraphs:
            text += paragraph.text + "\n"

    else:

        raise ValueError(
            "Only PDF and DOCX files are supported."
        )

    return text.strip()

def extract_text_from_file(filepath):
    return extract_resume_text(filepath)
