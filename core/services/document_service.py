"""
Document Service.
Handles document validation and text extraction for:
- PDF (.pdf) via PyPDF2
- Microsoft Word (.docx) via zipfile and XML
- Plain text (.txt) and Markdown (.md, .markdown)
"""
import io
import os
import zipfile
import logging
import xml.etree.ElementTree as ET
from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}
MIN_WORD_COUNT = 10
MAX_PAGES = 100


class DocumentExtractionError(Exception):
    """Raised when text cannot be validated or extracted from a document."""
    pass


def _get_extension(filename_or_path: str) -> str:
    return os.path.splitext(filename_or_path)[1].lower()


def validate_document_file(file_obj) -> None:
    """
    Validates uploaded document for format, encryption, corruption, and text content.
    Raises DocumentExtractionError if invalid.
    """
    filename = getattr(file_obj, "name", "")
    ext = _get_extension(filename)

    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentExtractionError(
            f"Unsupported file format '{ext}'. Supported formats: PDF (.pdf), Word (.docx), Plain Text (.txt), and Markdown (.md)."
        )

    # Read initial bytes to verify format signatures and reset pointer
    file_obj.seek(0)
    header = file_obj.read(1024)
    file_obj.seek(0)

    if not header:
        raise DocumentExtractionError("Uploaded document is empty (0 bytes).")

    if ext == ".pdf":
        if not header.startswith(b"%PDF"):
            raise DocumentExtractionError("Invalid or corrupted PDF file. File header signature is missing.")
        try:
            reader = PdfReader(file_obj)
            if reader.is_encrypted:
                raise DocumentExtractionError("This PDF is password-protected or encrypted. Please upload an unencrypted document.")
            num_pages = len(reader.pages)
            if num_pages == 0:
                raise DocumentExtractionError("The PDF document contains no pages.")
            if num_pages > MAX_PAGES:
                raise DocumentExtractionError(
                    f"PDF document exceeds the maximum limit of {MAX_PAGES} pages (found {num_pages} pages)."
                )
            
            # Check for extractable text across pages (detect scanned/image-only PDFs)
            sample_text = ""
            for page in reader.pages:
                text = page.extract_text() or ""
                if text:
                    sample_text += " " + text
                if len(sample_text.split()) >= MIN_WORD_COUNT:
                    break

            if len(sample_text.split()) < MIN_WORD_COUNT:
                raise DocumentExtractionError(
                    "The PDF appears to be scanned or contains no readable text. "
                    "Scanned documents require OCR, which is not currently supported. "
                    "Please upload a document with selectable text."
                )
        except DocumentExtractionError:
            raise
        except PdfReadError as err:
            logger.warning("PDF parsing error during validation: %s", err)
            raise DocumentExtractionError(f"Corrupted or unreadable PDF document: {err}")
        except Exception as err:
            logger.warning("Unexpected error during PDF validation: %s", err)
            raise DocumentExtractionError("Failed to read PDF document. Please verify the file is not corrupted.")
        finally:
            file_obj.seek(0)

    elif ext == ".docx":
        if not header.startswith(b"PK"):
            raise DocumentExtractionError("Invalid Word (.docx) document format.")
        try:
            with zipfile.ZipFile(file_obj) as z:
                if "word/document.xml" not in z.namelist():
                    raise DocumentExtractionError("Invalid Word document structure.")
                xml_content = z.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                texts = [
                    node.text for node in tree.iter()
                    if node.text and node.tag.endswith("}t")
                ]
                extracted = " ".join(texts).strip()
                if len(extracted.split()) < MIN_WORD_COUNT:
                    raise DocumentExtractionError(
                        "The Word document contains too little readable text. Please provide notes with more written content."
                    )
        except DocumentExtractionError:
            raise
        except zipfile.BadZipFile:
            raise DocumentExtractionError("Corrupted Word (.docx) archive.")
        except Exception as err:
            logger.warning("DOCX validation error: %s", err)
            raise DocumentExtractionError("Failed to read Word document. Please ensure it is a valid .docx file.")
        finally:
            file_obj.seek(0)

    elif ext in {".txt", ".md", ".markdown"}:
        try:
            content = file_obj.read()
            if isinstance(content, bytes):
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    text = content.decode("latin-1", errors="ignore")
            else:
                text = str(content)

            if len(text.strip().split()) < MIN_WORD_COUNT:
                raise DocumentExtractionError(
                    "The document contains too little readable text. Please provide notes with more written content."
                )
        except DocumentExtractionError:
            raise
        except Exception as err:
            logger.warning("Text file validation error: %s", err)
            raise DocumentExtractionError("Failed to read text document.")
        finally:
            file_obj.seek(0)


def extract_document_text(file_or_path, max_chars: int = 18000) -> str:
    """
    Extracts text from a given document path or Django FieldFile/file-like object.
    Supports both local files and storage abstractions.
    Raises DocumentExtractionError if the format is unsupported or corrupt.
    """
    close_file = False
    filename = ""

    if isinstance(file_or_path, str):
        if not os.path.exists(file_or_path):
            raise DocumentExtractionError("File not found on server.")
        filename = file_or_path
        ext = _get_extension(filename)
        file_obj = open(file_or_path, "rb")
        close_file = True
    else:
        # Django FieldFile or file-like object
        filename = getattr(file_or_path, "name", "")
        ext = _get_extension(filename)
        if hasattr(file_or_path, "open"):
            try:
                file_obj = file_or_path.open("rb")
                close_file = True
            except Exception:
                file_obj = file_or_path
        else:
            file_obj = file_or_path

    try:
        if ext not in ALLOWED_EXTENSIONS:
            raise DocumentExtractionError(
                f"Unsupported file format '{ext}'. Please upload a PDF, Word (DOCX), TXT, or Markdown file."
            )

        if ext == ".pdf":
            try:
                file_obj.seek(0)
                reader = PdfReader(file_obj)
                if reader.is_encrypted:
                    raise DocumentExtractionError(
                        "This PDF is password-protected or encrypted. Please upload an unencrypted document."
                    )
                pages_text = []
                for idx, page in enumerate(reader.pages):
                    if idx >= MAX_PAGES:
                        break
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
                extracted = "\n".join(pages_text)
            except DocumentExtractionError:
                raise
            except Exception as err:
                logger.error("Failed to extract text from PDF: %s", err)
                raise DocumentExtractionError(f"Failed to read PDF document ({err}).")

        elif ext in {".txt", ".md", ".markdown"}:
            try:
                file_obj.seek(0)
                raw = file_obj.read()
                if isinstance(raw, bytes):
                    try:
                        extracted = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        extracted = raw.decode("latin-1", errors="ignore")
                else:
                    extracted = str(raw)
            except Exception as err:
                logger.error("Failed to read text file: %s", err)
                raise DocumentExtractionError(f"Failed to read text document ({err}).")

        elif ext == ".docx":
            try:
                file_obj.seek(0)
                with zipfile.ZipFile(file_obj) as z:
                    xml_content = z.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                texts = [
                    node.text for node in tree.iter()
                    if node.text and node.tag.endswith("}t")
                ]
                extracted = " ".join(texts)
            except Exception as err:
                logger.error("Failed to read DOCX file: %s", err)
                raise DocumentExtractionError(f"Failed to read Word document ({err}).")

        cleaned_text = extracted.strip()
        if len(cleaned_text.split()) < MIN_WORD_COUNT:
            raise DocumentExtractionError(
                "The document appears to be scanned or contains too little readable text. "
                "Scanned documents require OCR, which is not currently supported. "
                "Please provide notes with more written content."
            )

        return cleaned_text[:max_chars]

    finally:
        if close_file and file_obj:
            try:
                file_obj.close()
            except Exception:
                pass
        if hasattr(file_or_path, "close"):
            try:
                file_or_path.close()
            except Exception:
                pass

