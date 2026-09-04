from app.extensions import database
from app.models import ClassSession, Course, Enrollment, User


def make_lecturer(email="lecturer@example.com"):
    lecturer = User(email=email, role="admin", full_name="Lecturer", qr_token="lecturer-token")
    database.session.add(lecturer)
    database.session.flush()
    return lecturer


def make_student(index_number="STU1", email="student@example.com"):
    student = User(email=email, role="student", full_name="Student One", index_number=index_number)
    database.session.add(student)
    database.session.flush()
    return student


def login_as(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def make_live_course(lecturer, student, **session_kwargs):
    course = Course(code="CS101", title="Intro", lecturer_id=lecturer.id)
    database.session.add(course)
    database.session.flush()
    database.session.add(
        Enrollment(course_id=course.id, index_number=student.index_number, student_id=student.id)
    )
    database.session.add(ClassSession(course_id=course.id, **session_kwargs))
    database.session.commit()
    return course


def test_scan_page_skips_the_location_step_when_the_session_has_no_location(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()
        make_live_course(lecturer, student)
        student_id = student.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(student_id))
        response = client.get("/l/lecturer-token")

    assert response.status_code == 200
    assert b"Tap below to mark yourself present." in response.data
    assert b"js/geo.js" not in response.data


def test_scan_page_asks_for_location_when_the_session_has_one(app):
    with app.app_context():
        lecturer = make_lecturer()
        student = make_student()
        make_live_course(lecturer, student, latitude=5.6037, longitude=-0.1870, location_accuracy=5.0)
        student_id = student.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(student_id))
        response = client.get("/l/lecturer-token")

    assert response.status_code == 200
    assert b"Confirm you're in the room to mark yourself present." in response.data
    assert b"js/geo.js" in response.data
