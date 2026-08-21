from datetime import datetime, timedelta

from app.attendance import apply_manual_override, revert_manual_override
from app.extensions import database
from app.models import AttendanceRecord, ClassSession, Course, Enrollment, User


def make_lecturer(email="lecturer@example.com"):
    lecturer = User(email=email, role="admin", full_name="Lecturer")
    database.session.add(lecturer)
    database.session.flush()
    return lecturer


def make_student(index_number="STU1", email="student@example.com"):
    student = User(email=email, role="student", full_name="Student One", index_number=index_number)
    database.session.add(student)
    database.session.flush()
    return student


def make_course_with_student(lecturer, student):
    course = Course(code="CS101", title="Intro", lecturer_id=lecturer.id)
    database.session.add(course)
    database.session.flush()
    database.session.add(
        Enrollment(course_id=course.id, index_number=student.index_number, student_id=student.id)
    )
    return course


def test_marks_an_absent_record_present_with_a_reason(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()
        course = make_course_with_student(lecturer, student)
        session = ClassSession(
            course_id=course.id,
            started_at=datetime(2026, 8, 1, 9, 0),
            ended_at=datetime(2026, 8, 1, 10, 0),
        )
        database.session.add(session)
        database.session.flush()
        record = AttendanceRecord(session_id=session.id, student_id=student.id, status="absent")
        database.session.add(record)
        database.session.commit()

        result = apply_manual_override(record, session, lecturer, "Phone died, confirmed in room")

        assert result.ok is True
        assert record.status == "present"
        assert record.override_reason == "Phone died, confirmed in room"
        assert record.overridden_by_id == lecturer.id
        assert record.overridden_at is not None


def test_rejects_override_while_session_is_live(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()
        course = make_course_with_student(lecturer, student)
        session = ClassSession(course_id=course.id)
        database.session.add(session)
        database.session.flush()
        record = AttendanceRecord(session_id=session.id, student_id=student.id, status="absent")
        database.session.add(record)
        database.session.commit()

        result = apply_manual_override(record, session, lecturer, "Some reason")

        assert result.ok is False
        assert record.status == "absent"


def test_rejects_override_without_a_reason(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()
        course = make_course_with_student(lecturer, student)
        session = ClassSession(
            course_id=course.id,
            started_at=datetime(2026, 8, 1, 9, 0),
            ended_at=datetime(2026, 8, 1, 10, 0),
        )
        database.session.add(session)
        database.session.flush()
        record = AttendanceRecord(session_id=session.id, student_id=student.id, status="absent")
        database.session.add(record)
        database.session.commit()

        result = apply_manual_override(record, session, lecturer, "   ")

        assert result.ok is False
        assert record.status == "absent"


def test_rejects_override_of_a_record_already_present(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()
        course = make_course_with_student(lecturer, student)
        session = ClassSession(
            course_id=course.id,
            started_at=datetime(2026, 8, 1, 9, 0),
            ended_at=datetime(2026, 8, 1, 10, 0),
        )
        database.session.add(session)
        database.session.flush()
        record = AttendanceRecord(
            session_id=session.id, student_id=student.id, status="present", scanned_at=datetime(2026, 8, 1, 9, 5)
        )
        database.session.add(record)
        database.session.commit()

        result = apply_manual_override(record, session, lecturer, "Some reason")

        assert result.ok is False
        # A real scan's timestamp must never be touched by a rejected override attempt.
        assert record.scanned_at == datetime(2026, 8, 1, 9, 5)


def test_revert_undoes_an_override_back_to_absent(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()
        course = make_course_with_student(lecturer, student)
        session = ClassSession(
            course_id=course.id,
            started_at=datetime(2026, 8, 1, 9, 0),
            ended_at=datetime(2026, 8, 1, 10, 0),
        )
        database.session.add(session)
        database.session.flush()
        record = AttendanceRecord(session_id=session.id, student_id=student.id, status="absent")
        database.session.add(record)
        database.session.commit()
        apply_manual_override(record, session, lecturer, "Phone died")

        result = revert_manual_override(record)

        assert result.ok is True
        assert record.status == "absent"
        assert record.override_reason is None
        assert record.overridden_by_id is None
        assert record.overridden_at is None


def test_revert_refuses_to_touch_a_real_scan(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()
        course = make_course_with_student(lecturer, student)
        session = ClassSession(course_id=course.id)
        database.session.add(session)
        database.session.flush()
        real_scan_time = datetime(2026, 8, 1, 9, 5)
        record = AttendanceRecord(
            session_id=session.id, student_id=student.id, status="present", scanned_at=real_scan_time
        )
        database.session.add(record)
        database.session.commit()

        result = revert_manual_override(record)

        assert result.ok is False
        assert record.status == "present"
        assert record.scanned_at == real_scan_time
