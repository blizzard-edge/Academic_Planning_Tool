"""
SCPTAA_011 - Input Validation

Validates the required inputs before course planning begins:
  * DegreeWorks PDF
  * CSU course catalog JSON
  * Four-year course offering schedule JSON

Expected catalog JSON:
[
  {"course_code": "CPSC 1302K", "title": "Introduction to ...", ...}
]

Expected offering schedule JSON:
{
  "CPSC 1302K": ["Fall", "Spring"],
  "CPSC 6125": ["Fall"]
}

The offering values may also be full terms, such as ["Fall 2026", "Spring 2027"].
For the validator, only the season is needed.
"""

import json
import os
import sys

from pypdf import PdfReader

VALID_SEASONS = {"spring", "summer", "fall"}

def validate_pdf(path):
    """Confirm the DegreeWorks input exists, is a PDF, and is readable."""
    if not path:
        raise ValueError("A DegreeWorks PDF path is required.")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"DegreeWorks PDF not found: {path}")
    if not path.lower().endswith(".pdf"):
        raise ValueError("DegreeWorks input must be a PDF file.")

    try:
        reader = PdfReader(path)
        if len(reader.pages) == 0:
            raise ValueError("The DegreeWorks PDF contains no pages.")
        # Attempt extraction so encrypted/corrupt/unreadable files are caught early.
        extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not extracted_text.strip():
            raise ValueError(
                "No selectable text was found in the DegreeWorks PDF. "
                "It may be scanned; OCR may be required."
            )
    except Exception as error:
        raise ValueError(f"Could not read DegreeWorks PDF: {error}") from error

    return True

def load_json(path, description):
    """Load JSON while reporting clear file and formatting errors."""
    if not path:
        raise ValueError(f"A path for {description} is required.")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{description} file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{description} is not valid JSON (line {error.lineno}, "
            f"column {error.colno}): {error.msg}"
        ) from error
    except OSError as error:
        raise ValueError(f"Could not read {description}: {error}") from error

def validate_catalog(catalog):
    """Check that the catalog is a non-empty list of usable course records."""
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("Course catalog JSON must contain a non-empty list.")

    errors = []
    for index, course in enumerate(catalog):
        if not isinstance(course, dict):
            errors.append(f"Catalog record {index + 1} is not an object.")
            continue
        if not isinstance(course.get("course_code"), str) or not course["course_code"].strip():
            errors.append(f"Catalog record {index + 1} has no valid course_code.")
        if not isinstance(course.get("title"), str) or not course["title"].strip():
            errors.append(f"Catalog record {index + 1} has no valid title.")

    if errors:
        raise ValueError("Invalid course catalog:\n- " + "\n- ".join(errors))
    return True

def validate_offerings(offerings):
    """Check that the offering schedule maps course codes to season/term lists."""
    if not isinstance(offerings, dict) or not offerings:
        raise ValueError(
            "Offering schedule JSON must be a non-empty object mapping course codes "
            "to lists of seasons or terms."
        )

    errors = []
    for code, terms in offerings.items():
        if not isinstance(code, str) or not code.strip():
            errors.append("An offering record has an empty or invalid course code.")
            continue
        if not isinstance(terms, list) or not terms:
            errors.append(f"{code}: offerings must be a non-empty list.")
            continue
        for term in terms:
            if not isinstance(term, str) or not term.strip():
                errors.append(f"{code}: each offering must be a non-empty string.")
                continue
            season = term.strip().split()[0].lower()
            if season not in VALID_SEASONS:
                errors.append(
                    f"{code}: '{term}' must start with Spring, Summer, or Fall."
                )

    if errors:
        raise ValueError("Invalid course offering schedule:\n- " + "\n- ".join(errors))
    return True

def validate_inputs(degreeworks_pdf, catalog_json, offerings_json):
    """Validate all required inputs and return the loaded JSON data."""
    validate_pdf(degreeworks_pdf)
    catalog = load_json(catalog_json, "Course catalog")
    offerings = load_json(offerings_json, "Course offering schedule")
    validate_catalog(catalog)
    validate_offerings(offerings)

    print("Input validation successful.")
    return {"catalog": catalog, "offerings": offerings}

def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python src/InputValidator.py "
            "<degreeworks.pdf> <course_catalog.json> <course_offerings.json>"
        )
        sys.exit(1)

    try:
        validate_inputs(sys.argv[1], sys.argv[2], sys.argv[3])
    except (ValueError, FileNotFoundError, OSError) as error:
        print(f"Input validation failed: {error}")
        sys.exit(1)

if __name__ == "__main__":
    main()