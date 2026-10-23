"""Integration and regression tests for the course planner and its use of
the team's study-plan and four-year-schedule parsers.

These are integration tests, not isolated unit tests: they read the
project's real input files, so these must be present:

    data/Graduate_Study_Plans.xlsx
    data/4_year_schedule.xlsx
    data/cpsc_course_catalog.json

If any is missing, the tests are skipped with a message rather than
failing. Student records are built in memory; data/degree_works_info.json
is never read.

Run from the project root:

    python -m unittest discover -s test -v
"""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from CoursePlanner import parse_prerequisite_groups, prerequisites_satisfied  # noqa: E402
from CoursePlannerIntegration import (  # noqa: E402
    DEFAULT_CATALOG,
    DEFAULT_SCHEDULE,
    DEFAULT_STUDY_PLANS,
    TRACKS,
    build_integrated_plan,
    offerings_from_schedule,
    resolve_study_plan_prerequisite,
)
from FourYearScheduleParser import load_four_year_schedule  # noqa: E402
import PrerequisiteChecker  # noqa: E402

MISSING_DATA = [
    str(path) for path in (DEFAULT_STUDY_PLANS, DEFAULT_SCHEDULE, DEFAULT_CATALOG)
    if not os.path.exists(path)
]
needs_project_data = unittest.skipIf(
    MISSING_DATA, "project data files not found: " + ", ".join(MISSING_DATA)
)

NEW_STUDENT = {"completed_courses": [], "in_progress_courses": []}
IN_PROGRESS_STUDENT = {
    "completed_courses": [
        {"course_code": "CPSC 6109", "grade": "A"},
        {"course_code": "CYBR 6126", "grade": "B"},
    ],
    "in_progress_courses": [
        {"course_code": "CPSC 6114"},
        {"course_code": "CPSC 6119"},
    ],
}


def write_student(record):
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(record, handle)
    handle.close()
    return handle.name


def scheduled(result):
    return [(s["semester"], c["course_code"]) for s in result["plan"] for c in s["courses"]]


@needs_project_data
class PlannerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.new_student = write_student(NEW_STUDENT)
        cls.in_progress_student = write_student(IN_PROGRESS_STUDENT)
        with open(DEFAULT_CATALOG, encoding="utf-8") as file:
            cls.catalog = {c["course_code"]: c for c in json.load(file)}
        cls.plans = {}
        for track in TRACKS:
            for start in ("Fall 2026", "Spring 2027"):
                cls.plans[(track, start)] = build_integrated_plan(
                    track=track, start_semester=start, degreeworks_path=cls.new_student
                )

    @classmethod
    def tearDownClass(cls):
        os.remove(cls.new_student)
        os.remove(cls.in_progress_student)

    def prerequisite_text(self, result, code):
        if code in result["provisional_courses"]:
            return result["provisional_courses"][code]["prerequisites"]
        return self.catalog[code].get("prerequisites")


class TestAcsRegression(PlannerTestCase):
    def test_software_spring_start_matches_known_plan(self):
        self.assertEqual(
            scheduled(self.plans[("software", "Spring 2027")]),
            [
                ("Spring 2027", "CPSC 6109"), ("Spring 2027", "CPSC 6185"),
                ("Spring 2027", "CYBR 6126"), ("Spring 2027", "CPSC 6179"),
                ("Summer 2027", "CPSC 6119"),
                ("Fall 2027", "CPSC 6177"), ("Fall 2027", "CPSC 6175"),
                ("Spring 2028", "CPSC 6127"),
            ],
        )

    def test_acs_required_courses_unchanged(self):
        self.assertEqual(
            self.plans[("general", "Fall 2026")]["required_courses"],
            ["CPSC 6119", "CPSC 6109", "CPSC 6157", "CPSC 6185",
             "CPSC 6127", "CYBR 6126", "CPSC 6177", "CPSC 6125"],
        )

    def placements(self, track, start, student_path):
        result = build_integrated_plan(
            track=track, start_semester=start, degreeworks_path=student_path
        )
        return {
            c["course_code"]: (s["semester"], c["notes"])
            for s in result["plan"] for c in s["courses"]
        }

    def test_in_progress_prerequisite_unlocks_next_term_as_conditional(self):
        # CPSC 6114 is in progress in Fall 2026; CPSC 6124 needs it.
        placed = self.placements("ai", "Spring 2027", self.in_progress_student)
        term, notes = placed["CPSC 6124"]
        self.assertEqual(term, "Spring 2027")
        self.assertIn("CONDITIONAL", notes)
        self.assertIn("Expected completion of CPSC 6114", notes)

    def test_in_progress_prerequisite_does_not_count_in_current_term(self):
        # CPSC 6121 is offered in Fall 2026, but 6114 is only in progress
        # then, so 6121 must wait for the next fall and stay conditional.
        placed = self.placements("ai", "Fall 2026", self.in_progress_student)
        self.assertNotIn("Fall 2026", [term for term, _ in placed.values()])
        term, notes = placed["CPSC 6121"]
        self.assertEqual(term, "Fall 2027")
        self.assertIn("CONDITIONAL", notes)

    def test_in_progress_cybr_prerequisite_is_conditional(self):
        student = write_student({
            "completed_courses": [],
            "in_progress_courses": [{"course_code": "CYBR 6126"}],
        })
        try:
            placed = self.placements("cyber-defense", "Spring 2027", student)
        finally:
            os.remove(student)
        term, notes = placed["CYBR 6167"]
        self.assertEqual(term, "Spring 2027")
        self.assertIn("Expected completion of CYBR 6126", notes)
        self.assertIn("PROVISIONAL", notes)


class TestAllTracks(PlannerTestCase):
    def test_every_required_course_is_scheduled_once_or_explained(self):
        for key, result in self.plans.items():
            with self.subTest(track=key[0], start=key[1]):
                placed = [code for _, code in scheduled(result)]
                skipped = [u["course_code"] for u in result["unscheduled"]]
                self.assertEqual(len(placed), len(set(placed)), "course scheduled twice")
                self.assertEqual(sorted(placed + skipped), sorted(result["required_courses"]))
                for item in result["unscheduled"]:
                    self.assertTrue(item["reason"])

    def test_no_term_exceeds_credit_cap(self):
        for key, result in self.plans.items():
            for semester in result["plan"]:
                with self.subTest(track=key[0], start=key[1], term=semester["semester"]):
                    self.assertLessEqual(sum(c["credits"] for c in semester["courses"]), 12)

    def test_prerequisites_always_finish_in_an_earlier_term(self):
        for key, result in self.plans.items():
            done_before = set()
            for semester in result["plan"]:
                for course in semester["courses"]:
                    expression = parse_prerequisite_groups(
                        self.prerequisite_text(result, course["course_code"])
                    )
                    with self.subTest(track=key[0], start=key[1], course=course["course_code"]):
                        self.assertTrue(prerequisites_satisfied(expression, done_before))
                done_before |= {c["course_code"] for c in semester["courses"]}


class TestCybersecurityPrerequisites(PlannerTestCase):
    def test_cybr_prerequisites_come_from_the_study_plan(self):
        result = self.plans[("cyber-defense", "Fall 2026")]
        self.assertEqual(result["provisional_courses"]["CYBR 6128"]["prerequisites"],
                         "CYBR 6126 AND CPSC 6157")

    def test_cybr_6128_and_6226_after_6126_and_6157(self):
        for start in ("Fall 2026", "Spring 2027"):
            term = {code: t for t, code in scheduled(self.plans[("cyber-defense", start)])}
            order = [s["semester"] for s in self.plans[("cyber-defense", start)]["plan"]]
            for later in ("CYBR 6128", "CYBR 6226"):
                for earlier in ("CYBR 6126", "CPSC 6157"):
                    with self.subTest(start=start, course=later, needs=earlier):
                        self.assertLess(order.index(term[earlier]), order.index(term[later]))

    def test_template_same_semester_conflict_is_reported(self):
        warnings = self.plans[("cyber-defense", "Spring 2027")]["warnings"]
        conflicts = [w for w in warnings if w.startswith("CYBR 6226") and "concurrent" in w]
        self.assertEqual(len(conflicts), 2)  # one each for CYBR 6126 and CPSC 6157
        self.assertTrue(all("advisor" in w for w in conflicts))

    def test_template_conflicts_reported_exactly_where_they_exist(self):
        # The official templates place a course alongside its prerequisite
        # in exactly two places: CYBR 6226 (Cyber Defense, Spring start)
        # and CPSC 6121 with CPSC 6114 (AI, Spring start, semester 3).
        expected = {
            ("cyber-defense", "Spring 2027"): ["CYBR 6226", "CYBR 6226"],
            ("ai", "Spring 2027"): ["CPSC 6121"],
        }
        for key, result in self.plans.items():
            with self.subTest(track=key[0], start=key[1]):
                flagged = sorted(
                    w.split(":")[0] for w in result["warnings"] if "concurrent" in w
                )
                self.assertEqual(flagged, expected.get(key, []))

    def test_provisional_courses_keep_advisor_warnings(self):
        for track in ("cyber-defense", "cyber-management"):
            result = self.plans[(track, "Fall 2026")]
            for code in result["provisional_courses"]:
                with self.subTest(track=track, course=code):
                    self.assertTrue(any(
                        w.startswith(code) and "advisor verification" in w
                        for w in result["warnings"]
                    ))

    def test_ambiguous_number_is_left_for_advisor_review(self):
        resolved = resolve_study_plan_prerequisite("6126", ["CYBR 6126", "CPSC 6126"])
        self.assertEqual(resolved, "6126")
        with self.assertRaises(ValueError):
            parse_prerequisite_groups(resolved)


@needs_project_data
class TestScheduleAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schedule = load_four_year_schedule(str(DEFAULT_SCHEDULE))

    def test_question_mark_cells_are_not_offered(self):
        offerings, warnings = offerings_from_schedule(
            self.schedule, "Spring 2027", courses_of_interest=["CPSC 3555"]
        )
        self.assertNotIn("CPSC 3555", offerings)
        self.assertTrue(any("CPSC 3555" in w and "uncertain" in w for w in warnings))

    def test_may_session_cells_are_offered(self):
        offerings, _ = offerings_from_schedule(self.schedule, "Spring 2027")
        self.assertIn("Summer 2027", offerings["CPSC 3165"])

    def test_past_terms_are_ignored(self):
        offerings, _ = offerings_from_schedule(self.schedule, "Spring 2027")
        self.assertEqual(offerings["CPSC 6125"], ["Fall 2027", "Fall 2028"])


class TestPrerequisiteCheckerHandoff(PlannerTestCase):
    def test_checker_accepts_completed_plus_planned_courses(self):
        result = build_integrated_plan(
            track="ai", start_semester="Spring 2027", degreeworks_path=self.in_progress_student
        )
        done = [c["course_code"] for c in
                IN_PROGRESS_STUDENT["completed_courses"] + IN_PROGRESS_STUDENT["in_progress_courses"]]
        planned = [code for _, code in scheduled(result)]
        self.assertEqual(
            PrerequisiteChecker.main(list(self.catalog.values()), {"courses": done + planned}), {}
        )


if __name__ == "__main__":
    unittest.main()
