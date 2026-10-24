"""Deterministic PDF extraction and SurveyJS validation tools."""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from .schemas import ExtractionResult, ValidationResult

MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 100
MIN_USEFUL_TEXT_CHARACTERS = 20

# Deliberately limited to common SurveyJS question types that this MVP can
# validate with useful deterministic checks.
SUPPORTED_QUESTION_TYPES = {
    "boolean",
    "checkbox",
    "comment",
    "dropdown",
    "html",
    "imagepicker",
    "matrix",
    "matrixdropdown",
    "matrixdynamic",
    "multipletext",
    "panel",
    "paneldynamic",
    "radiogroup",
    "rating",
    "ranking",
    "signaturepad",
    "tagbox",
    "text",
}
CHOICE_QUESTION_TYPES = {
    "checkbox",
    "dropdown",
    "imagepicker",
    "radiogroup",
    "ranking",
    "tagbox",
}


def _humanize_name(name: str) -> str:
    words = re.sub(r"[_-]+", " ", name).strip()
    return words[:1].upper() + words[1:] if words else name


def _clean_visible_if(expression: str) -> str:
    """Repair common quoting mistakes without changing condition meaning."""

    expression = expression.strip()
    quoted_comparison = re.fullmatch(
        r'"\{([^}]+)\}"\s*(=|!=)\s*"([^"]*)"', expression
    )
    if quoted_comparison:
        field, operator, value = quoted_comparison.groups()
        escaped_value = value.replace("'", "\\'")
        return f"{{{field}}} {operator} '{escaped_value}'"

    wrapped_expression = re.fullmatch(
        r'"(\{[^}]+\}\s+contains\s+\'[^\']+\')"', expression
    )
    if wrapped_expression:
        return wrapped_expression.group(1)
    return expression


def normalize_survey(value: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize safe, unambiguous model mistakes before validation."""

    survey = deepcopy(value)
    warnings: list[str] = []
    pages = survey.get("pages")
    root_elements = survey.get("elements")

    if isinstance(pages, list):
        for page in pages:
            if isinstance(page, dict) and "elements" not in page:
                page["elements"] = []

    if isinstance(pages, list) and isinstance(root_elements, list):
        unmapped: list[Any] = []
        moved = 0
        for element in root_elements:
            if not isinstance(element, dict):
                unmapped.append(element)
                continue
            page_ref = element.get("page")
            page_index: int | None = None
            if isinstance(page_ref, int) and not isinstance(page_ref, bool):
                candidate = page_ref - 1
                if 0 <= candidate < len(pages):
                    page_index = candidate
            elif isinstance(page_ref, str):
                for index, page in enumerate(pages):
                    if isinstance(page, dict) and page_ref == page.get("name"):
                        page_index = index
                        break

            if page_index is None or not isinstance(pages[page_index], dict):
                unmapped.append(element)
                continue
            page_elements = pages[page_index].get("elements")
            if not isinstance(page_elements, list):
                unmapped.append(element)
                continue
            normalized_element = deepcopy(element)
            normalized_element.pop("page", None)
            page_elements.append(normalized_element)
            moved += 1

        if moved:
            warnings.append(
                f"Moved {moved} question(s) from top-level elements into their pages."
            )
        if unmapped:
            pages.append(
                {
                    "name": "additional_questions",
                    "title": "Additional questions",
                    "elements": unmapped,
                }
            )
            warnings.append(
                f"Placed {len(unmapped)} question(s) without a page reference in "
                "Additional questions."
            )
        survey.pop("elements", None)

    if isinstance(pages, list):
        nonempty_pages = [
            page
            for page in pages
            if not isinstance(page, dict)
            or not isinstance(page.get("elements"), list)
            or bool(page["elements"])
        ]
        removed_page_count = len(pages) - len(nonempty_pages)
        if removed_page_count and nonempty_pages:
            pages = nonempty_pages
            survey["pages"] = pages
            warnings.append(f"Removed {removed_page_count} empty page(s).")

        used_page_names: set[str] = set()
        for index, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                continue
            original_name = page.get("name")
            if isinstance(original_name, str) and original_name.strip():
                page.setdefault("title", _humanize_name(original_name))
                base_name = re.sub(r"[^a-z0-9]+", "_", original_name.lower()).strip("_")
            else:
                base_name = f"page_{index}"
            base_name = base_name or f"page_{index}"
            unique_name = base_name
            suffix = 2
            while unique_name in used_page_names:
                unique_name = f"{base_name}_{suffix}"
                suffix += 1
            page["name"] = unique_name
            used_page_names.add(unique_name)

    element_groups: list[list[Any]] = []
    if isinstance(survey.get("elements"), list):
        element_groups.append(survey["elements"])
    if isinstance(pages, list):
        for page in pages:
            if isinstance(page, dict) and isinstance(page.get("elements"), list):
                element_groups.append(page["elements"])

    for group in element_groups:
        for element, _ in _iter_elements(group, "elements"):
            if not isinstance(element, dict):
                continue
            name = element.get("name")
            if (
                element.get("type") != "html"
                and isinstance(name, str)
                and name.strip()
                and not isinstance(element.get("title"), str)
            ):
                element["title"] = _humanize_name(name)
            visible_if = element.get("visibleIf")
            if isinstance(visible_if, str):
                element["visibleIf"] = _clean_visible_if(visible_if)

    return survey, warnings


def extract_pdf(path: str | Path) -> ExtractionResult:
    """Extract text from a local, text-based PDF without OCR.

    The file is treated as untrusted data. Its contents are read as document
    text only and are never executed.
    """

    pdf_path = Path(path).expanduser()
    if not pdf_path.exists():
        return ExtractionResult(ok=False, error=f"PDF does not exist: {pdf_path}")
    if not pdf_path.is_file():
        return ExtractionResult(ok=False, error=f"Path is not a file: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        return ExtractionResult(ok=False, error="Only .pdf files are supported.")

    try:
        file_size = pdf_path.stat().st_size
    except OSError as exc:
        return ExtractionResult(ok=False, error=f"Could not inspect PDF: {exc}")
    if file_size == 0:
        return ExtractionResult(ok=False, error="PDF is empty.")
    if file_size > MAX_PDF_BYTES:
        return ExtractionResult(
            ok=False,
            error=f"PDF exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB limit.",
        )

    try:
        with pdf_path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                return ExtractionResult(
                    ok=False, error="File does not have a valid PDF signature."
                )
    except OSError as exc:
        return ExtractionResult(ok=False, error=f"Could not read PDF: {exc}")

    try:
        import pymupdf
    except ImportError:
        return ExtractionResult(
            ok=False,
            error="PyMuPDF is not installed. Run: pip install -r requirements.txt",
        )

    try:
        document = pymupdf.open(pdf_path)
    except Exception as exc:  # PyMuPDF exposes several format-specific errors.
        return ExtractionResult(ok=False, error=f"Could not open PDF: {exc}")

    try:
        if document.needs_pass:
            return ExtractionResult(ok=False, error="Password-protected PDFs are not supported.")
        page_count = document.page_count
        if page_count > MAX_PDF_PAGES:
            return ExtractionResult(
                ok=False,
                page_count=page_count,
                error=f"PDF exceeds the {MAX_PDF_PAGES}-page limit.",
            )

        pages: list[str] = []
        for page_number, page in enumerate(document, start=1):
            page_text = page.get_text("text").strip()
            if page_text:
                pages.append(f"--- Page {page_number} ---\n{page_text}")
        text = "\n\n".join(pages).strip()
    except Exception as exc:
        return ExtractionResult(ok=False, error=f"PDF text extraction failed: {exc}")
    finally:
        document.close()

    warnings: list[str] = []
    if len(text) < MIN_USEFUL_TEXT_CHARACTERS:
        warnings.append(
            "Little or no extractable text was found. The PDF may be scanned; "
            "OCR is not included in this MVP."
        )

    return ExtractionResult(
        ok=True,
        text=text,
        page_count=page_count,
        character_count=len(text),
        warnings=warnings,
    )


def extract_pdf_text(pdf_path: str) -> dict[str, Any]:
    """Extract plain text from a user-selected PDF.

    Args:
        pdf_path: Path to a local PDF selected by the user.

    Returns:
        A dictionary containing status, extracted text, counts, and warnings.
    """

    requested_path = Path(pdf_path).expanduser().resolve()
    allowed_root = Path(
        os.getenv("PDF_SURVEY_ALLOWED_ROOT", str(Path.cwd()))
    ).expanduser().resolve()
    if requested_path != allowed_root and allowed_root not in requested_path.parents:
        return ExtractionResult(
            ok=False,
            error=(
                "The ADK extraction tool may only read PDFs inside "
                f"PDF_SURVEY_ALLOWED_ROOT ({allowed_root})."
            ),
        ).to_dict()
    return extract_pdf(requested_path).to_dict()


def _iter_elements(elements: Iterable[Any], location: str) -> Iterable[tuple[Any, str]]:
    for index, element in enumerate(elements):
        item_location = f"{location}[{index}]"
        yield element, item_location
        if isinstance(element, dict):
            nested = element.get("elements")
            if isinstance(nested, list):
                yield from _iter_elements(nested, f"{item_location}.elements")
            template = element.get("templateElements")
            if isinstance(template, list):
                yield from _iter_elements(template, f"{item_location}.templateElements")


def validate_survey(value: Any) -> ValidationResult:
    """Validate the basic structure of a SurveyJS JSON definition."""

    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(value, dict):
        return ValidationResult(valid=False, errors=["Survey must be a JSON object."])

    element_groups: list[tuple[list[Any], str]] = []
    if "elements" in value and "pages" in value:
        errors.append(
            "Survey cannot mix top-level 'elements' with 'pages'; put each question "
            "inside its page's elements array."
        )
    if "elements" in value:
        if isinstance(value["elements"], list):
            element_groups.append((value["elements"], "elements"))
        else:
            errors.append("'elements' must be an array.")

    if "pages" in value:
        pages = value["pages"]
        if not isinstance(pages, list):
            errors.append("'pages' must be an array.")
        else:
            for page_index, page in enumerate(pages):
                page_location = f"pages[{page_index}]"
                if not isinstance(page, dict):
                    errors.append(f"{page_location} must be an object.")
                    continue
                page_name = page.get("name")
                if not isinstance(page_name, str) or not page_name.strip():
                    errors.append(f"{page_location}.name must be a non-empty string.")
                elements = page.get("elements")
                if not isinstance(elements, list):
                    errors.append(f"{page_location}.elements must be an array.")
                    continue
                element_groups.append((elements, f"{page_location}.elements"))

    if not element_groups:
        errors.append("Survey must contain an 'elements' array or pages with elements.")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    names: set[str] = set()
    question_count = 0
    for group, location in element_groups:
        for element, item_location in _iter_elements(group, location):
            if not isinstance(element, dict):
                errors.append(f"{item_location} must be an object.")
                continue
            question_type = element.get("type")
            if not isinstance(question_type, str) or not question_type:
                errors.append(f"{item_location}.type must be a non-empty string.")
                continue
            if question_type not in SUPPORTED_QUESTION_TYPES:
                errors.append(
                    f"{item_location}.type '{question_type}' is not supported by this MVP."
                )
                continue
            if question_type == "html":
                if not isinstance(element.get("html"), str):
                    errors.append(f"{item_location}.html must be a string.")
                continue

            question_count += 1
            name = element.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"{item_location}.name must be a non-empty string.")
            elif name in names:
                errors.append(f"Duplicate question name '{name}'.")
            else:
                names.add(name)

            title = element.get("title")
            if title is not None and not isinstance(title, str):
                errors.append(f"{item_location}.title must be a string when provided.")
            if not isinstance(title, str) or not title.strip():
                errors.append(f"{item_location}.title must be a non-empty string.")

            if "isRequired" in element and not isinstance(element["isRequired"], bool):
                errors.append(f"{item_location}.isRequired must be true or false.")
            if "visibleIf" in element and not isinstance(element["visibleIf"], str):
                errors.append(f"{item_location}.visibleIf must be a string.")

            if question_type in CHOICE_QUESTION_TYPES:
                choices = element.get("choices")
                if not isinstance(choices, list) or not choices:
                    errors.append(
                        f"{item_location}.choices must be a non-empty array for {question_type}."
                    )
                else:
                    for choice_index, choice in enumerate(choices):
                        valid_scalar = isinstance(choice, (str, int, float)) and not isinstance(
                            choice, bool
                        )
                        valid_object = (
                            isinstance(choice, dict)
                            and "value" in choice
                            and isinstance(choice["value"], (str, int, float))
                            and not isinstance(choice["value"], bool)
                        )
                        if not (valid_scalar or valid_object):
                            errors.append(
                                f"{item_location}.choices[{choice_index}] must be a scalar "
                                "or an object with a scalar 'value'."
                            )

    if question_count == 0:
        errors.append("Survey must contain at least one question.")
    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)


def validate_survey_json(survey_json: str) -> dict[str, Any]:
    """Validate a SurveyJS JSON string and return errors and warnings.

    Args:
        survey_json: A JSON string representing a SurveyJS definition.

    Returns:
        A dictionary with valid, errors, and warnings fields.
    """

    try:
        value = json.loads(survey_json)
    except json.JSONDecodeError as exc:
        return ValidationResult(
            valid=False,
            errors=[f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"],
        ).to_dict()
    return validate_survey(value).to_dict()

