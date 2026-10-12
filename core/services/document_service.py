"""
Document Service.
Handles extraction of readable text from multiple file formats:
- PDF (.pdf) via PyPDF2
- Microsoft Word (.docx) via standard zipfile / XML parsing
- Plain text (.txt) and Markdown (.md)
"""
import os
import zipfile
import xml.etree.ElementTree as ET
from PyPDF2 import PdfReader


class DocumentExtractionError(Exception):
    """Raised when text cannot be extracted from a document."""
    pass


def extract_document_text(file_path: str, max_chars: int = 18000) -> str:
    """
    Extracts text from a given document path.
    Raises DocumentExtractionError if the format is unsupported or corrupt.
    """
    if not os.path.exists(file_path):
        raise DocumentExtractionError("File not found on server.")

    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == ".pdf":
            reader = PdfReader(file_path)
            extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif ext in {".txt", ".md", ".markdown"}:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
                extracted = file.read()
        elif ext == ".docx":
            with zipfile.ZipFile(file_path) as z:
                xml_content = z.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            texts = [
                node.text for node in tree.iter()
                if node.text and node.tag.endswith("}t")
            ]
            extracted = " ".join(texts)
        else:
            raise DocumentExtractionError(
                f"Unsupported file format '{ext}'. Please upload a PDF, Word (DOCX), TXT, or Markdown file."
            )
    except DocumentExtractionError:
        raise
    except Exception as err:
        raise DocumentExtractionError(f"Failed to read file ({err}).")

    cleaned_text = extracted.strip()
    if len(cleaned_text.split()) < 10:
        raise DocumentExtractionError(
            "The document contains too little readable text. Please provide notes with more written content."
        )

    return cleaned_text[:max_chars]
