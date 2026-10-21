
"""SCPTAA_001: Semester-by-semester academic course planner.

Produces exporter-compatible semester plans using catalog prerequisites,
DegreeWorks progress, and confirmed course offerings.

Unverified grades and expected completion of in-progress prerequisites
are explicitly identified as conditional recommendations.
"""

import re

from openpyxl import load_workbook


SEMESTER_ORDER = {"spring": 0, "summer": 1, "fall": 2}
TERM_PREFIXES = {"SP": "Spring", "SU": "Summer", "FA": "Fall"}
CONFIRMED_DELIVERY_CODES = {"F", "O", "D", "N"}
COURSE_CODE_PATTERN = re.compile(r"[A-Z]{4}\s+\d{4}[A-Z]?")
TOKEN_PATTERN = re.compile(
    r"\s*(?:"
    r"(?P<course>[A-Z]{4}\s+\d{4}[A-Z]?)"
    r"|(?P<operator>AND|OR)\b"
    r"|(?P<paren>[()])"
    r")",
    re.IGNORECASE,
)
GRADE_PATTERN = re.compile(
    r"\s+WITH\s+A\s+MINIMUM\s+GRADE\s+OF\s+([A-DF])\b",
    re.IGNORECASE,
)
CONCURRENT_PATTERN = re.compile(
    r"\s*\(\s*MAY\s+BE\s+TAKEN\s+CONCURRENTLY\s*\)",
    re.IGNORECASE,
)
GRADE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}


class UnsupportedPrerequisiteError(ValueError):
    """An academic requirement cannot be interpreted safely."""


def normalize_course_code(value):
    if not isinstance(value, str):
        return ""
    value = value.replace("\u00c2", "").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip().upper()


def extract_credits(course_hours):
    if isinstance(course_hours, int) and not isinstance(course_hours, bool):
        return course_hours if course_hours >= 0 else None
    if not isinstance(course_hours, str):
        return None
    match = re.fullmatch(
        r"\(\s*\d+\s*-\s*\d+\s*-\s*(\d+)\s*\)",
        course_hours.strip(),
    )
    return int(match.group(1)) if match else None


def semester_sort_key(semester):
    if not isinstance(semester, str):
        raise ValueError("Semester must be a string.")
    match = re.fullmatch(
        r"\s*(Spring|Summer|Fall)\s+(\d{4})\s*",
        semester,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(
            f"Invalid semester '{semester}'. Expected 'Spring 2027'."
        )
    return int(match.group(2)), SEMESTER_ORDER[match.group(1).lower()]


def generate_semesters(start_semester, count):
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError("Semester count must be positive.")
    year, season = semester_sort_key(start_semester)
    seasons = ["Spring", "Summer", "Fall"]
    return [
        f"{seasons[(season + i) % 3]} {year + (season + i) // 3}"
        for i in range(count)
    ]


def parse_schedule_heading(heading):
    if not isinstance(heading, str):
        return None
    match = re.fullmatch(r"(SP|SU|FA)(\d{2})", heading.strip().upper())
    if not match:
        return None
    return f"{TERM_PREFIXES[match.group(1)]} {2000 + int(match.group(2))}"


def is_discontinued_cell(cell):
    fill = cell.fill
    return (
        fill.patternType == "solid"
        and fill.fgColor.type == "theme"
        and fill.fgColor.theme == 1
        and abs(fill.fgColor.tint - 0.5) < 0.01
    )


def has_confirmed_offering(value):
    if not isinstance(value, str):
        return False
    value = value.strip().upper()
    if not value or "?" in value:
        return False
    codes = [part.strip() for part in value.split(",")]
    return all(code in CONFIRMED_DELIVERY_CODES for code in codes)


def load_course_offerings(workbook_path, start_semester="Fall 2026"):
    """Read only confirmed future offerings from the schedule workbook."""
    start_key = semester_sort_key(start_semester)
    workbook = load_workbook(workbook_path, data_only=True)
    try:
        sheet = workbook.active
        columns = {}
        for column in range(3, sheet.max_column + 1):
            term = parse_schedule_heading(sheet.cell(3, column).value)
            if term and semester_sort_key(term) >= start_key:
                columns[column] = term

        offerings = {}
        for row in range(4, sheet.max_row + 1):
            code = normalize_course_code(sheet.cell(row, 1).value)
            if not COURSE_CODE_PATTERN.fullmatch(code):
                continue
            for column, term in columns.items():
                cell = sheet.cell(row, column)
                if is_discontinued_cell(cell):
                    continue
                if has_confirmed_offering(cell.value):
                    terms = offerings.setdefault(code, [])
                    if term not in terms:
                        terms.append(term)
        return offerings
    finally:
        workbook.close()


def normalize_course_list(courses):
    result = set()
    for course in courses or []:
        value = course.get("course_code") if isinstance(course, dict) else course
        code = normalize_course_code(value)
        if code:
            result.add(code)
    return result


def tokenize_prerequisites(text):
    """Tokenize boolean course requirements; reject unsupported words."""
    text = normalize_course_code(text)
    tokens = []
    position = 0
    while position < len(text):
        if text[position:].isspace():
            break
        match = TOKEN_PATTERN.match(text, position)
        if not match:
            raise UnsupportedPrerequisiteError(
                f"Unsupported prerequisite language near {text[position:position + 50]!r}"
            )
        if match.group("course"):
            tokens.append(("COURSE", normalize_course_code(match.group("course"))))
        elif match.group("operator"):
            operator = match.group("operator").upper()
            tokens.append((operator, operator))
        else:
            symbol = match.group("paren")
            tokens.append((symbol, symbol))
        position = match.end()
    return tokens


class PrerequisiteExpressionParser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.position = 0

    def peek(self):
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position][0]

    def consume(self, expected):
        if self.peek() != expected:
            raise UnsupportedPrerequisiteError(
                f"Expected {expected}, found {self.peek()}."
            )
        value = self.tokens[self.position][1]
        self.position += 1
        return value

    def parse(self):
        if not self.tokens:
            return None
        expression = self.parse_or()
        if self.peek() is not None:
            raise UnsupportedPrerequisiteError("Unexpected trailing prerequisite.")
        return expression

    def parse_or(self):
        left = self.parse_and()
        while self.peek() == "OR":
            self.consume("OR")
            left = ("OR", left, self.parse_and())
        return left

    def parse_and(self):
        left = self.parse_atom()
        while self.peek() == "AND":
            self.consume("AND")
            left = ("AND", left, self.parse_atom())
        return left

    def parse_atom(self):
        if self.peek() == "COURSE":
            return ("COURSE", self.consume("COURSE"))
        if self.peek() == "(":
            self.consume("(")
            expression = self.parse_or()
            self.consume(")")
            return expression
        raise UnsupportedPrerequisiteError(
            f"Expected course or opening parenthesis, found {self.peek()}."
        )


def parse_prerequisite_details(prerequisite_text):
    """Return parsed requirements, minimum grades, and concurrency notes.

    Minimum-grade and concurrency language is recognized, but not
    silently treated as proof that those conditions were satisfied.
    """
    if prerequisite_text is None or prerequisite_text == "":
        return None, {}, set()

    if not isinstance(prerequisite_text, str):
        raise UnsupportedPrerequisiteError("Prerequisites must be text.")

    text = normalize_course_code(prerequisite_text)
    minimum_grades = {}
    concurrent = set()

    # Preserve grade requirements before removing catalog prose.
    for match in re.finditer(
        r"([A-Z]{4}\s+\d{4}[A-Z]?)"
        r"\s+WITH\s+A\s+MINIMUM\s+GRADE\s+OF\s+([A-DF])\b",
        text,
    ):
        minimum_grades[normalize_course_code(match.group(1))] = match.group(2)

    # Record courses explicitly marked as eligible for concurrency.
    for match in re.finditer(
        r"([A-Z]{4}\s+\d{4}[A-Z]?)"
        r"\s*\(\s*MAY\s+BE\s+TAKEN\s+CONCURRENTLY\s*\)",
        text,
    ):
        concurrent.add(normalize_course_code(match.group(1)))

    cleaned = GRADE_PATTERN.sub("", text)
    cleaned = CONCURRENT_PATTERN.sub("", cleaned)

    # Any other prose remains and causes a review-required error.
    expression = PrerequisiteExpressionParser(
        tokenize_prerequisites(cleaned)
    ).parse()
    return expression, minimum_grades, concurrent


def parse_prerequisite_groups(prerequisite_text):
    """Compatibility interface for existing prerequisite tests."""
    expression, _, _ = parse_prerequisite_details(prerequisite_text)
    return expression


def prerequisites_satisfied(expression, completed_courses):
    completed = normalize_course_list(completed_courses)

    def evaluate(node):
        if node is None or node == []:
            return True
        if isinstance(node, list):
            return all(
                any(normalize_course_code(option) in completed for option in group)
                for group in node
            )
        if not isinstance(node, tuple):
            raise UnsupportedPrerequisiteError("Invalid prerequisite expression.")
        if node[0] == "COURSE":
            return node[1] in completed
        if node[0] == "AND":
            return evaluate(node[1]) and evaluate(node[2])
        if node[0] == "OR":
            return evaluate(node[1]) or evaluate(node[2])
        raise UnsupportedPrerequisiteError("Unknown prerequisite operator.")

    return evaluate(expression)


def build_course_index(course_catalog):
    return {
        normalize_course_code(record["course_code"]): record
        for record in course_catalog
        if isinstance(record, dict)
        and normalize_course_code(record.get("course_code"))
    }


def get_course_credits(course, default_credits=None):
    credits = course.get("credits")
    if isinstance(credits, int) and not isinstance(credits, bool) and credits >= 0:
        return credits
    parsed = extract_credits(course.get("course_hours"))
    return parsed if parsed is not None else default_credits


def create_course_entry(code, catalog_record, credits):
    return {
        "course_code": code,
        "title": catalog_record.get("title", ""),
        "credits": credits,
        "notes": "",
    }


def _student_grades(records):
    """Read known letter grades without assuming missing grades are passes."""
    grades = {}
    for record in records or []:
        if not isinstance(record, dict):
            continue
        code = normalize_course_code(record.get("course_code"))
        grade = str(record.get("grade") or "").strip().upper()
        if code and grade in GRADE_RANK:
            grades[code] = grade
    return grades


def _evaluate_requirements(
    expression,
    available,
    completed,
    in_progress,
    grades,
    minimum_grades,
    allow_expected,
):
    """Return (eligible, conditional notes), respecting AND/OR grouping."""

    def evaluate(node):
        if node is None:
            return True, []

        operator = node[0]
        if operator == "COURSE":
            code = node[1]
            if code not in available:
                return False, []

            notes = []
            if code in in_progress and code not in completed:
                if not allow_expected:
                    return False, []
                notes.append(f"Expected completion of {code} must be verified")

            minimum = minimum_grades.get(code)
            if minimum:
                actual = grades.get(code)
                if actual is None:
                    notes.append(f"Verify {code} earned at least grade {minimum}")
                elif GRADE_RANK[actual] < GRADE_RANK[minimum]:
                    return False, []

            return True, notes

        if operator == "AND":
            left_ok, left_notes = evaluate(node[1])
            right_ok, right_notes = evaluate(node[2])
            return left_ok and right_ok, left_notes + right_notes

        if operator == "OR":
            left_ok, left_notes = evaluate(node[1])
            right_ok, right_notes = evaluate(node[2])
            if left_ok and right_ok:
                return (True, left_notes) if len(left_notes) <= len(right_notes) else (
                    True, right_notes
                )
            if left_ok:
                return True, left_notes
            if right_ok:
                return True, right_notes
            return False, []

        raise UnsupportedPrerequisiteError("Unknown prerequisite operator.")

    return evaluate(expression)


def build_course_plan(
    required_courses,
    degreeworks_data,
    course_catalog,
    offering_schedule,
    start_semester="Fall 2026",
    max_credits=12,
    include_summer=True,
    default_credits=None,
    current_semester="Fall 2026",
):
    """Create an exporter-compatible course plan and report limitations."""
    if not isinstance(max_credits, int) or isinstance(max_credits, bool) or max_credits <= 0:
        raise ValueError("max_credits must be a positive integer.")
    if not isinstance(include_summer, bool):
        raise ValueError("include_summer must be a boolean.")
    if not isinstance(required_courses, list):
        raise ValueError("required_courses must be a list.")
    if not isinstance(degreeworks_data, dict):
        raise ValueError("degreeworks_data must be a dictionary.")
    if not isinstance(course_catalog, list):
        raise ValueError("course_catalog must be a list.")
    if not isinstance(offering_schedule, dict):
        raise ValueError("offering_schedule must be a dictionary.")

    start_key = semester_sort_key(start_semester)
    current_key = semester_sort_key(current_semester)

    completed_records = degreeworks_data.get("completed_courses", [])
    in_progress_records = degreeworks_data.get("in_progress_courses", [])

    completed = normalize_course_list(completed_records)
    in_progress = normalize_course_list(in_progress_records) - completed
    grades = _student_grades(completed_records)
    catalog_index = build_course_index(course_catalog)

    offerings = {}
    all_terms = set()

    for code, terms in offering_schedule.items():
        code = normalize_course_code(code)
        if not code or not isinstance(terms, list):
            continue
        for term in terms:
            try:
                key = semester_sort_key(term)
            except ValueError:
                continue
            if key < start_key:
                continue
            if not include_summer and key[1] == SEMESTER_ORDER["summer"]:
                continue
            offerings.setdefault(code, set()).add(term)
            all_terms.add(term)

    semesters = sorted(all_terms, key=semester_sort_key)
    plan = [{"semester": term, "courses": []} for term in semesters]

    pending = []
    seen = set()
    for item in required_courses:
        code = normalize_course_code(
            item.get("course_code") if isinstance(item, dict) else item
        )
        if not code or code in seen:
            continue
        seen.add(code)
        if code not in completed and code not in in_progress:
            pending.append(code)

    parsed = {}
    errors = {}
    for code in pending:
        record = catalog_index.get(code)
        if record is None:
            continue
        try:
            parsed[code] = parse_prerequisite_details(record.get("prerequisites"))
        except UnsupportedPrerequisiteError as error:
            errors[code] = str(error)

    scheduled = set()
    unscheduled = []
    warnings = []
    conditional_count = 0

    for entry in plan:
        term = entry["semester"]
        term_key = semester_sort_key(term)
        credits_used = 0

        # A course taken during this semester cannot satisfy an earlier
        # prerequisite unless explicit concurrency support is implemented.
        available = completed | scheduled
        allow_expected = term_key > current_key
        if allow_expected:
            available |= in_progress

        for code in list(pending):
            if term not in offerings.get(code, set()):
                continue
            record = catalog_index.get(code)
            if record is None or code in errors:
                continue

            credits = get_course_credits(record, default_credits)
            if credits is None or credits_used + credits > max_credits:
                continue

            expression, minimum_grades, concurrent = parsed[code]

            eligible, notes = _evaluate_requirements(
                expression,
                available,
                completed,
                in_progress,
                grades,
                minimum_grades,
                allow_expected,
            )
            if not eligible:
                continue

            # Concurrency is recognized, but the scheduler does not yet
            # approve same-term enrollment automatically.
            if concurrent:
                notes.append(
                    "Concurrent enrollment policy requires advisor verification"
                )

            course_entry = create_course_entry(code, record, credits)
            if notes:
                course_entry["notes"] = "CONDITIONAL: " + "; ".join(
                    dict.fromkeys(notes)
                )
                conditional_count += 1

            entry["courses"].append(course_entry)
            credits_used += credits
            scheduled.add(code)
            pending.remove(code)

    for code in pending:
        record = catalog_index.get(code)
        if record is None:
            reason = "Course not found in the course catalog."
        elif code in errors:
            reason = "Prerequisite requires advisor review: " + errors[code]
        elif get_course_credits(record, default_credits) is None:
            reason = "Credit hours could not be determined."
        elif not offerings.get(code):
            reason = "No confirmed course offerings found."
        else:
            expression, minimum_grades, _ = parsed[code]
            possible, _ = _evaluate_requirements(
                expression,
                completed | scheduled | in_progress,
                completed,
                in_progress,
                grades,
                minimum_grades,
                True,
            )
            if not possible:
                reason = "Prerequisites are not satisfied."
            else:
                reason = (
                    "Could not fit course into an available semester "
                    "within the credit limit and planning window."
                )

        unscheduled.append({"course_code": code, "reason": reason})

    if in_progress:
        warnings.append(
            "In-progress courses are excluded from rescheduling. "
            "Future prerequisite eligibility assumes successful completion "
            "and must be verified."
        )
    if conditional_count:
        warnings.append(
            f"{conditional_count} scheduled course(s) have conditional "
            "prerequisite requirements requiring verification."
        )
    if unscheduled:
        warnings.append(
            f"{len(unscheduled)} required course(s) could not be scheduled."
        )

    return {
        "plan": plan,
        "unscheduled": unscheduled,
        "warnings": warnings,
    }
