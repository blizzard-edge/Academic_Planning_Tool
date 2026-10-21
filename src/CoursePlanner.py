
"""SCPTAA_001 - Semester-by-semester course planning.

Builds a recommended plan using:
- Required courses from a graduate study plan
- DegreeWorks academic progress
- Course catalog prerequisites and credit hours
- Confirmed offerings from the four-year schedule

Unsupported prerequisite expressions require advisor review.
"""

import re

from openpyxl import load_workbook


SEMESTER_ORDER = {
    "spring": 0,
    "summer": 1,
    "fall": 2,
}

TERM_PREFIXES = {
    "SP": "Spring",
    "SU": "Summer",
    "FA": "Fall",
}

CONFIRMED_DELIVERY_CODES = {"F", "O", "D", "N"}

COURSE_CODE_PATTERN = re.compile(r"[A-Z]{4}\s+\d{4}[A-Z]?")

PREREQUISITE_TOKEN_PATTERN = re.compile(
    r"\s*(?:"
    r"(?P<course>[A-Z]{4}\s+\d{4}[A-Z]?)"
    r"|(?P<operator>AND|OR)\b"
    r"|(?P<parenthesis>[()])"
    r")",
    flags=re.IGNORECASE,
)


class UnsupportedPrerequisiteError(ValueError):
    """Raised when prerequisite language cannot be parsed safely."""


def normalize_course_code(value):
    """Normalize course codes and remove known encoding artifacts."""
    if not isinstance(value, str):
        return ""

    cleaned = value.replace("\u00c2", "").replace("\u00a0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().upper()

    return cleaned


def extract_credits(course_hours):
    """Extract credits from catalog notation such as (3-3-4)."""
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
    """Return a chronological sorting key for a semester."""
    if not isinstance(semester, str):
        raise ValueError("Semester must be a string.")

    match = re.fullmatch(
        r"\s*(Spring|Summer|Fall)\s+(\d{4})\s*",
        semester,
        flags=re.IGNORECASE,
    )

    if not match:
        raise ValueError(
            f"Invalid semester '{semester}'. "
            "Expected a value such as 'Fall 2026'."
        )

    return (
        int(match.group(2)),
        SEMESTER_ORDER[match.group(1).lower()],
    )


def generate_semesters(start_semester, count):
    """Generate consecutive semesters."""
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError("Semester count must be a positive integer.")

    year, season_index = semester_sort_key(start_semester)
    seasons = ["Spring", "Summer", "Fall"]

    semesters = []

    for offset in range(count):
        position = season_index + offset

        semesters.append(
            f"{seasons[position % 3]} {year + position // 3}"
        )

    return semesters


def parse_schedule_heading(heading):
    """Convert schedule headings such as FA26 to Fall 2026."""
    if not isinstance(heading, str):
        return None

    match = re.fullmatch(
        r"(SP|SU|FA)(\d{2})",
        heading.strip().upper(),
    )

    if not match:
        return None

    return (
        f"{TERM_PREFIXES[match.group(1)]} "
        f"{2000 + int(match.group(2))}"
    )


def is_discontinued_cell(cell):
    """Identify the observed grey fill for discontinued offerings."""
    fill = cell.fill

    return (
        fill.patternType == "solid"
        and fill.fgColor.type == "theme"
        and fill.fgColor.theme == 1
        and abs(fill.fgColor.tint - 0.5) < 0.01
    )


def has_confirmed_offering(value):
    """Accept only confirmed delivery codes, not uncertain offerings."""
    if not isinstance(value, str):
        return False

    normalized = value.strip().upper()

    if not normalized or "?" in normalized:
        return False

    codes = [part.strip() for part in normalized.split(",")]

    return bool(codes) and all(
        code in CONFIRMED_DELIVERY_CODES
        for code in codes
    )


def load_course_offerings(workbook_path, start_semester="Fall 2026"):
    """Read confirmed future offerings from the four-year schedule."""
    start_key = semester_sort_key(start_semester)

    workbook = load_workbook(
        workbook_path,
        read_only=False,
        data_only=True,
    )

    try:
        sheet = workbook.active
        semester_columns = {}

        for column in range(3, sheet.max_column + 1):
            semester = parse_schedule_heading(
                sheet.cell(3, column).value
            )

            if semester and semester_sort_key(semester) >= start_key:
                semester_columns[column] = semester

        offerings = {}

        for row in range(4, sheet.max_row + 1):
            code = normalize_course_code(
                sheet.cell(row, 1).value
            )

            if not COURSE_CODE_PATTERN.fullmatch(code):
                continue

            for column, semester in semester_columns.items():
                cell = sheet.cell(row, column)

                if is_discontinued_cell(cell):
                    continue

                if not has_confirmed_offering(cell.value):
                    continue

                terms = offerings.setdefault(code, [])

                if semester not in terms:
                    terms.append(semester)

        return offerings

    finally:
        workbook.close()


def normalize_course_list(courses):
    """Convert course records or strings to normalized course codes."""
    result = set()

    for course in courses or []:
        if isinstance(course, dict):
            code = normalize_course_code(
                course.get("course_code")
            )
        else:
            code = normalize_course_code(course)

        if code:
            result.add(code)

    return result


def tokenize_prerequisites(prerequisite_text):
    """Tokenize a supported prerequisite expression.

    Supported syntax:
        COURSE
        COURSE AND COURSE
        COURSE OR COURSE
        Parenthesized combinations

    Other language is rejected rather than guessed.
    """
    text = normalize_course_code(prerequisite_text)

    if not text:
        return []

    tokens = []
    position = 0

    while position < len(text):
        if text[position:].isspace():
            break

        match = PREREQUISITE_TOKEN_PATTERN.match(
            text,
            position,
        )

        if match is None:
            raise UnsupportedPrerequisiteError(
                "Unsupported prerequisite language near: "
                + repr(text[position:position + 50])
            )

        if match.group("course"):
            tokens.append(
                ("COURSE", normalize_course_code(
                    match.group("course")
                ))
            )

        elif match.group("operator"):
            operator = match.group("operator").upper()
            tokens.append((operator, operator))

        elif match.group("parenthesis"):
            symbol = match.group("parenthesis")
            tokens.append((symbol, symbol))

        position = match.end()

    return tokens


class PrerequisiteExpressionParser:
    """Recursive-descent parser: AND has higher precedence than OR."""

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

        token = self.tokens[self.position]
        self.position += 1

        return token[1]

    def parse(self):
        if not self.tokens:
            return None

        expression = self.parse_or()

        if self.peek() is not None:
            raise UnsupportedPrerequisiteError(
                "Unexpected token after prerequisite expression."
            )

        return expression

    def parse_or(self):
        left = self.parse_and()

        while self.peek() == "OR":
            self.consume("OR")
            right = self.parse_and()
            left = ("OR", left, right)

        return left

    def parse_and(self):
        left = self.parse_atom()

        while self.peek() == "AND":
            self.consume("AND")
            right = self.parse_atom()
            left = ("AND", left, right)

        return left

    def parse_atom(self):
        token_type = self.peek()

        if token_type == "COURSE":
            return ("COURSE", self.consume("COURSE"))

        if token_type == "(":
            self.consume("(")
            expression = self.parse_or()
            self.consume(")")
            return expression

        raise UnsupportedPrerequisiteError(
            f"Expected a course or opening parenthesis, "
            f"found {token_type}."
        )


def parse_prerequisite_groups(prerequisite_text):
    """Parse prerequisites into a boolean expression tree.

    Returns None for missing prerequisites.

    Tree examples:
        ("COURSE", "CPSC 1000")

        ("OR",
            ("COURSE", "CPSC 1000"),
            ("COURSE", "CPSC 2000"))

    The function retains its previous name for compatibility
    with existing caller code.
    """
    if prerequisite_text is None:
        return None

    if not isinstance(prerequisite_text, str):
        raise UnsupportedPrerequisiteError(
            "Prerequisites must be text or None."
        )

    tokens = tokenize_prerequisites(prerequisite_text)

    return PrerequisiteExpressionParser(tokens).parse()


def prerequisites_satisfied(
    prerequisite_groups,
    completed_courses,
):
    """Evaluate prerequisites against completed courses."""
    completed = normalize_course_list(completed_courses)

    def evaluate(node):
        if node is None or node == []:
            return True

        # Support the older list-of-OR-groups representation.
        if isinstance(node, list):
            return all(
                any(
                    normalize_course_code(option) in completed
                    for option in group
                )
                for group in node
            )

        if not isinstance(node, tuple):
            raise UnsupportedPrerequisiteError(
                "Invalid prerequisite expression."
            )

        if node[0] == "COURSE":
            return node[1] in completed

        if node[0] == "AND":
            return evaluate(node[1]) and evaluate(node[2])

        if node[0] == "OR":
            return evaluate(node[1]) or evaluate(node[2])

        raise UnsupportedPrerequisiteError(
            "Unknown prerequisite operator."
        )

    return evaluate(prerequisite_groups)


def build_course_index(course_catalog):
    """Index catalog records by normalized course code."""
    index = {}

    for course in course_catalog:
        if not isinstance(course, dict):
            continue

        code = normalize_course_code(
            course.get("course_code")
        )

        if code:
            index[code] = course

    return index


def get_course_credits(course, default_credits=None):
    """Determine credits without inventing unknown values."""
    credits = course.get("credits")

    if (
        isinstance(credits, int)
        and not isinstance(credits, bool)
        and credits >= 0
    ):
        return credits

    parsed = extract_credits(
        course.get("course_hours")
    )

    if parsed is not None:
        return parsed

    return default_credits


def create_course_entry(code, catalog_record, credits):
    """Create a course record compatible with the Excel exporter."""
    return {
        "course_code": code,
        "title": catalog_record.get("title", ""),
        "credits": credits,
        "notes": "",
    }


def build_course_plan(
    required_courses,
    degreeworks_data,
    course_catalog,
    offering_schedule,
    start_semester="Fall 2026",
    max_credits=12,
    include_summer=True,
    default_credits=None,
):
    """Build a recommended semester-by-semester plan.

    Returns a dictionary with:
        plan: semester records for the Excel exporter
        unscheduled: required courses that could not be placed
        warnings: conditions requiring attention
    """
    if (
        not isinstance(max_credits, int)
        or isinstance(max_credits, bool)
        or max_credits <= 0
    ):
        raise ValueError(
            "max_credits must be a positive integer."
        )

    if not isinstance(include_summer, bool):
        raise ValueError(
            "include_summer must be a boolean."
        )

    if not isinstance(degreeworks_data, dict):
        raise ValueError(
            "degreeworks_data must be a dictionary."
        )

    if not isinstance(offering_schedule, dict):
        raise ValueError(
            "offering_schedule must be a dictionary."
        )

    if not isinstance(course_catalog, list):
        raise ValueError(
            "course_catalog must be a list."
        )

    if not isinstance(required_courses, list):
        raise ValueError(
            "required_courses must be a list."
        )

    start_key = semester_sort_key(start_semester)

    completed = normalize_course_list(
        degreeworks_data.get(
            "completed_courses", []
        )
    )

    in_progress = normalize_course_list(
        degreeworks_data.get(
            "in_progress_courses", []
        )
    )

    catalog_index = build_course_index(
        course_catalog
    )

    normalized_offerings = {}

    for code, terms in offering_schedule.items():
        normalized_code = normalize_course_code(code)

        if not normalized_code or not isinstance(terms, list):
            continue

        normalized_offerings.setdefault(
            normalized_code, set()
        ).update(
            term for term in terms
            if isinstance(term, str)
        )

    all_terms = set()

    for terms in normalized_offerings.values():
        for term in terms:
            try:
                term_key = semester_sort_key(term)
            except ValueError:
                continue

            if term_key < start_key:
                continue

            if (
                not include_summer
                and term_key[1] == SEMESTER_ORDER["summer"]
            ):
                continue

            all_terms.add(term)

    semesters = sorted(
        all_terms,
        key=semester_sort_key,
    )

    plan = [
        {
            "semester": semester,
            "courses": [],
        }
        for semester in semesters
    ]

    pending = []
    seen = set()

    for course in required_courses:
        if isinstance(course, dict):
            code = normalize_course_code(
                course.get("course_code")
            )
        else:
            code = normalize_course_code(course)

        if not code or code in seen:
            continue

        seen.add(code)

        if code not in completed and code not in in_progress:
            pending.append(code)

    scheduled = set()
    warnings = []
    unscheduled = []

    # Cache prerequisite parse results so invalid expressions
    # cannot be accidentally treated as empty requirements.
    prerequisite_cache = {}
    prerequisite_errors = {}

    for code in pending:
        catalog_record = catalog_index.get(code)

        if catalog_record is None:
            continue

        try:
            prerequisite_cache[code] = (
                parse_prerequisite_groups(
                    catalog_record.get("prerequisites")
                )
            )
        except UnsupportedPrerequisiteError as error:
            prerequisite_errors[code] = str(error)

    for semester_entry in plan:
        semester = semester_entry["semester"]
        semester_credits = 0

        # Prerequisites must have been completed before this
        # semester; courses taken together do not count.
        available_at_start = completed | scheduled

        for code in list(pending):
            if semester not in normalized_offerings.get(
                code, set()
            ):
                continue

            catalog_record = catalog_index.get(code)

            if catalog_record is None:
                continue

            if code in prerequisite_errors:
                continue

            credits = get_course_credits(
                catalog_record,
                default_credits=default_credits,
            )

            if credits is None:
                continue

            if semester_credits + credits > max_credits:
                continue

            expression = prerequisite_cache.get(code)

            if not prerequisites_satisfied(
                expression,
                available_at_start,
            ):
                continue

            semester_entry["courses"].append(
                create_course_entry(
                    code,
                    catalog_record,
                    credits,
                )
            )

            semester_credits += credits
            scheduled.add(code)
            pending.remove(code)

    for code in pending:
        catalog_record = catalog_index.get(code)

        if catalog_record is None:
            reason = (
                "Course not found in the course catalog."
            )

        elif code in prerequisite_errors:
            reason = (
                "Prerequisite requires advisor review: "
                + prerequisite_errors[code]
            )

        elif get_course_credits(
            catalog_record,
            default_credits=default_credits,
        ) is None:
            reason = (
                "Credit hours could not be determined."
            )

        elif not normalized_offerings.get(code):
            reason = (
                "No confirmed course offerings found."
            )

        elif not prerequisites_satisfied(
            prerequisite_cache.get(code),
            completed | scheduled,
        ):
            reason = (
                "Prerequisites are not satisfied."
            )

        else:
            reason = (
                "Could not fit course into an available "
                "semester within the credit limit "
                "and planning window."
            )

        unscheduled.append({
            "course_code": code,
            "reason": reason,
        })

    if in_progress:
        warnings.append(
            "In-progress courses were excluded from future "
            "scheduling. Their completion must be verified "
            "before graduation."
        )

    if unscheduled:
        warnings.append(
            f"{len(unscheduled)} required course(s) "
            "could not be scheduled."
        )

    return {
        "plan": plan,
        "unscheduled": unscheduled,
        "warnings": warnings,
    }
