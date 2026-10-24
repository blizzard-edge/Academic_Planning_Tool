"""Tests for the Smart Class Planning Tool main controller."""

import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import Main


class TestMainController(unittest.TestCase):

    def make_args(self, input_path, output_path, pdf=False):
        return argparse.Namespace(
            degreeworks_pdf=input_path if pdf else None,
            degreeworks_json=None if pdf else input_path,
            track="software",
            start="Spring 2027",
            max_credits=12,
            no_summer=False,
            study_plans=Main.ROOT / "data" / "Graduate_Study_Plans.xlsx",
            schedule=Main.ROOT / "data" / "4_year_schedule.xlsx",
            catalog=Main.ROOT / "data" / "cpsc_course_catalog.json",
            output=output_path,
        )

    def test_json_input_exports_eight_courses(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            audit = folder / "audit.json"
            audit.write_text(
                '{"completed_courses":[],"in_progress_courses":[],"remaining_courses":[]}',
                encoding="utf-8",
            )

            output = folder / "plan.xlsx"
            result = Main.run_application(self.make_args(audit, output))

            self.assertTrue(output.is_file())
            self.assertEqual(
                sum(len(term["courses"]) for term in result["plan"]), 8
            )
            self.assertEqual(result["unscheduled"], [])

    def test_invalid_json_structure_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            audit = folder / "invalid.json"
            audit.write_text('{"plan":[]}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Invalid DegreeWorks data"):
                Main.run_application(
                    self.make_args(audit, folder / "invalid.xlsx")
                )

    def test_invalid_pdf_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            pdf = folder / "invalid.pdf"
            pdf.write_bytes(b"not a PDF")

            with self.assertRaises(ValueError):
                Main.run_application(
                    self.make_args(pdf, folder / "invalid.xlsx", pdf=True)
                )

    def test_pdf_path_uses_parser(self):
        student = {
            "completed_courses": [],
            "in_progress_courses": [],
            "remaining_courses": [],
        }

        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            pdf = folder / "sample.pdf"
            pdf.write_bytes(b"mock PDF")

            with (
                patch.object(Main, "validate_pdf") as validate,
                patch.object(Main, "extract_text_from_pdf", return_value="sample text") as extract,
                patch.object(Main, "parse_courses", return_value=student) as parse,
            ):
                output = folder / "plan.xlsx"
                result = Main.run_application(
                    self.make_args(pdf, output, pdf=True)
                )

            validate.assert_called_once_with(str(pdf))
            extract.assert_called_once_with(str(pdf))
            parse.assert_called_once_with("sample text")
            self.assertTrue(output.is_file())
            self.assertEqual(
                sum(len(term["courses"]) for term in result["plan"]), 8
            )


if __name__ == "__main__":
    unittest.main()
