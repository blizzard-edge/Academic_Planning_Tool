from pypdf import PdfReader


def extract_text_from_pdf(pdf_path):
    """Extract text from every page of a DegreeWorks PDF."""
    reader = PdfReader(pdf_path)

    pages = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            pages.append(text)

    return "\n".join(pages)


if __name__ == "__main__":
    pdf_path = "local_test_data/degree work.pdf"

    degreeworks_text = extract_text_from_pdf(pdf_path)

    print(degreeworks_text)