from datetime import datetime, timedelta

from app.extensions import database
from app.models import AttendanceRecord, ClassSession, Course, Enrollment, User
from app.stats import count_low_attendance_students


def make_lecturer(email="lecturer@example.com"):
    lecturer = User(email=email, role="admin", full_name="Lecturer")
    database.session.add(lecturer)
    database.session.flush()
    return lecturer


def make_student(index_number, email):
    student = User(email=email, role="student", full_name=index_number, index_number=index_number)
    database.session.add(student)
    database.session.flush()
    return student


def enroll(course, student):
    enrollment = Enrollment(course_id=course.id, index_number=student.index_number, student_id=student.id)
    database.session.add(enrollment)
    return enrollment


def add_ended_session(course, started_at):
    session = ClassSession(course_id=course.id, started_at=started_at, ended_at=started_at + timedelta(hours=1))
    database.session.add(session)
    database.session.flush()
    return session


def mark_present(session, student):
    database.session.add(AttendanceRecord(session_id=session.id, student_id=student.id, status="present"))


def test_counts_students_below_threshold_across_a_lecturers_courses(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.flush()

        low_student = make_student("STU1", "low@example.com")
        high_student = make_student("STU2", "high@example.com")
        enroll(course, low_student)
        enroll(course, high_student)

        session_one = add_ended_session(course, datetime(2026, 8, 1, 9, 0))
        session_two = add_ended_session(course, datetime(2026, 8, 8, 9, 0))
        # low_student: 0/2 present -> 0%. high_student: 2/2 present -> 100%.
        mark_present(session_one, high_student)
        mark_present(session_two, high_student)
        database.session.commit()

        assert count_low_attendance_students(lecturer.id) == 1


def test_does_not_count_another_lecturers_students(app):
    with app.app_context():
        owner = make_lecturer("owner@example.com")
        other = make_lecturer("other@example.com")
        course = Course(code="CS101", title="Intro", lecturer_id=owner.id)
        database.session.add(course)
        database.session.flush()

        student = make_student("STU1", "low@example.com")
        enroll(course, student)
        session = add_ended_session(course, datetime(2026, 8, 1, 9, 0))
        # Student has 0/1 present -> 0%, well below threshold, but belongs to `owner`, not `other`.
        database.session.commit()

        assert count_low_attendance_students(other.id) == 0


def test_ignores_students_with_no_ended_sessions_yet(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.flush()

        student = make_student("STU1", "new@example.com")
        enroll(course, student)
        database.session.commit()

        assert count_low_attendance_students(lecturer.id) == 0
