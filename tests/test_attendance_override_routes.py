from datetime import datetime

from app.extensions import database
from app.models import AttendanceRecord, ClassSession, Course, Enrollment, User


def make_lecturer(email="lecturer@example.com"):
    lecturer = User(email=email, role="admin", full_name="Lecturer")
    database.session.add(lecturer)
    database.session.commit()
    return lecturer


def make_student(index_number="STU1", email="student@example.com"):
    student = User(email=email, role="student", full_name="Student One", index_number=index_number)
    database.session.add(student)
    database.session.commit()
    return student


def login_as(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def make_ended_session_with_absent_record(lecturer, student):
    course = Course(code="CS101", title="Intro", lecturer_id=lecturer.id)
    database.session.add(course)
    database.session.flush()
    database.session.add(
        Enrollment(course_id=course.id, index_number=student.index_number, student_id=student.id)
    )
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
    return course, session, record


def test_lecturer_can_mark_an_absent_student_present_with_a_reason(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()
        course, session, record = make_ended_session_with_absent_record(lecturer, student)
        lecturer_id, course_id, session_id, record_id = lecturer.id, course.id, session.id, record.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        response = client.post(
            f"/courses/{course_id}/sessions/{session_id}/records/{record_id}/override",
            data={"reason": "Phone died, confirmed in room"},
        )
        assert response.status_code == 302

    with app.app_context():
        updated = AttendanceRecord.query.get(record_id)
        assert updated.status == "present"
        assert updated.override_reason == "Phone died, confirmed in room"
        assert updated.overridden_by_id == lecturer_id


def test_override_without_a_reason_leaves_record_absent(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()
        course, session, record = make_ended_session_with_absent_record(lecturer, student)
        lecturer_id, course_id, session_id, record_id = lecturer.id, course.id, session.id, record.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        client.post(f"/courses/{course_id}/sessions/{session_id}/records/{record_id}/override", data={"reason": ""})

    with app.app_context():
        assert AttendanceRecord.query.get(record_id).status == "absent"


def test_another_lecturer_cannot_override_a_record_on_someone_elses_course(app):
    with app.app_context():
        owner = make_lecturer("owner@example.com")
        other = make_lecturer("other@example.com")
        student = make_student()
        course, session, record = make_ended_session_with_absent_record(owner, student)
        other_id, course_id, session_id, record_id = other.id, course.id, session.id, record.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(other_id))
        response = client.post(
            f"/courses/{course_id}/sessions/{session_id}/records/{record_id}/override",
            data={"reason": "Some reason"},
        )
        assert response.status_code == 403


def test_lecturer_can_revert_an_override_back_to_absent(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()
        course, session, record = make_ended_session_with_absent_record(lecturer, student)
        lecturer_id, course_id, session_id, record_id = lecturer.id, course.id, session.id, record.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        client.post(
            f"/courses/{course_id}/sessions/{session_id}/records/{record_id}/override",
            data={"reason": "Phone died"},
        )
        response = client.post(f"/courses/{course_id}/sessions/{session_id}/records/{record_id}/revert-override")
        assert response.status_code == 302

    with app.app_context():
        updated = AttendanceRecord.query.get(record_id)
        assert updated.status == "absent"
        assert updated.overridden_by_id is None
