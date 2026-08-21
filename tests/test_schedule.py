from datetime import datetime, time

from app.extensions import database
from app.models import ClassScheduleSlot, ClassSession, Course, Enrollment, User
from app.schedule import next_class_for_student, next_class_relative_label, parse_schedule_rows


def make_lecturer():
    lecturer = User(email="lecturer@example.com", role="admin", full_name="Lecturer")
    database.session.add(lecturer)
    database.session.flush()
    return lecturer


def make_student():
    student = User(
        email="student@example.com",
        role="student",
        full_name="Student",
        index_number="STU1",
    )
    database.session.add(student)
    database.session.flush()
    return student


def enroll(course, student):
    database.session.add(
        Enrollment(course_id=course.id, index_number=student.index_number, student_id=student.id)
    )


def test_returns_the_soonest_upcoming_slot_across_enrolled_courses(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()

        far_course = Course(code="FAR101", title="Far Course", lecturer_id=lecturer.id)
        near_course = Course(code="NEAR101", title="Near Course", lecturer_id=lecturer.id)
        database.session.add_all([far_course, near_course])
        database.session.flush()

        enroll(far_course, student)
        enroll(near_course, student)

        database.session.add_all(
            [
                # Friday, later in the week.
                ClassScheduleSlot(course_id=far_course.id, day_of_week=4, start_time=time(9, 0)),
                # Tuesday, the soonest slot from a Monday-morning "now".
                ClassScheduleSlot(course_id=near_course.id, day_of_week=1, start_time=time(10, 0)),
            ]
        )
        database.session.commit()

        now = datetime(2026, 8, 24, 9, 0)  # a Monday
        result = next_class_for_student(student, now=now)

        assert result is not None
        assert result["course"].code == "NEAR101"
        assert result["when"] == datetime(2026, 8, 25, 10, 0)


def test_skips_a_course_that_already_has_a_live_session(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()

        course = Course(code="LIVE101", title="Live Course", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.flush()

        enroll(course, student)
        database.session.add(ClassScheduleSlot(course_id=course.id, day_of_week=1, start_time=time(10, 0)))
        database.session.add(ClassSession(course_id=course.id))
        database.session.commit()

        result = next_class_for_student(student, now=datetime(2026, 8, 24, 9, 0))

        assert result is None


def test_returns_none_when_no_enrolled_course_has_a_schedule(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()

        course = Course(code="NOSKED101", title="Unscheduled Course", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.flush()
        enroll(course, student)
        database.session.commit()

        result = next_class_for_student(student, now=datetime(2026, 8, 24, 9, 0))

        assert result is None


def test_wraps_to_next_week_when_todays_slot_already_passed(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()

        course = Course(code="MON101", title="Monday Course", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.flush()
        enroll(course, student)
        # Monday 9am slot, but "now" is already past that on the same Monday.
        database.session.add(ClassScheduleSlot(course_id=course.id, day_of_week=0, start_time=time(9, 0)))
        database.session.commit()

        result = next_class_for_student(student, now=datetime(2026, 8, 24, 10, 0))

        assert result["when"] == datetime(2026, 8, 31, 9, 0)


def test_parse_schedule_rows_pairs_days_with_times():
    rows = parse_schedule_rows(["0", "4"], ["09:00", "14:30"])

    assert rows == [(0, time(9, 0)), (4, time(14, 30))]


def test_parse_schedule_rows_skips_incomplete_rows():
    # A day chosen with no time set (or vice versa) is a half-filled "add another" row.
    rows = parse_schedule_rows(["0", ""], ["", "14:30"])

    assert rows == []


def test_parse_schedule_rows_skips_invalid_values():
    rows = parse_schedule_rows(["7", "not-a-day"], ["09:00", "09:00"])

    assert rows == []


def test_relative_label_for_later_today():
    label = next_class_relative_label(datetime(2026, 8, 24, 14, 0), now=datetime(2026, 8, 24, 9, 0))

    assert label == "Today · 02:00 PM"


def test_relative_label_for_tomorrow():
    label = next_class_relative_label(datetime(2026, 8, 25, 9, 0), now=datetime(2026, 8, 24, 20, 0))

    assert label == "Tomorrow · 09:00 AM"


def test_relative_label_for_a_later_weekday():
    label = next_class_relative_label(datetime(2026, 8, 28, 9, 0), now=datetime(2026, 8, 24, 9, 0))

    assert label == "Fri · 09:00 AM"
