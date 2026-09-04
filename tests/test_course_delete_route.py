from app.extensions import database
from app.models import ClassSession, Course, Enrollment, User


def make_lecturer(email="lecturer@example.com"):
    lecturer = User(email=email, role="admin", full_name="Lecturer")
    database.session.add(lecturer)
    database.session.commit()
    return lecturer


def login_as(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def test_deleting_a_course_removes_it_and_its_roster(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro to CS", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.flush()
        database.session.add(Enrollment(course_id=course.id, index_number="PS/ITC/21/0001"))
        database.session.commit()
        lecturer_id, course_id = lecturer.id, course.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        response = client.post(f"/courses/{course_id}/delete")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/courses/")

    with app.app_context():
        assert Course.query.get(course_id) is None
        assert Enrollment.query.filter_by(course_id=course_id).count() == 0


def test_cannot_delete_another_lecturers_course(app):
    with app.app_context():
        owner = make_lecturer("owner@example.com")
        other = make_lecturer("other@example.com")
        course = Course(code="CS101", title="Intro to CS", lecturer_id=owner.id)
        database.session.add(course)
        database.session.commit()
        other_id, course_id = other.id, course.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(other_id))
        response = client.post(f"/courses/{course_id}/delete")
        assert response.status_code == 403

    with app.app_context():
        assert Course.query.get(course_id) is not None


def test_cannot_delete_a_course_with_a_live_session(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro to CS", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.flush()
        database.session.add(
            ClassSession(course_id=course.id, latitude=1.0, longitude=1.0, location_accuracy=5.0)
        )
        database.session.commit()
        lecturer_id, course_id = lecturer.id, course.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        response = client.post(f"/courses/{course_id}/delete")
        assert response.status_code == 302
        assert response.headers["Location"].endswith(f"/courses/{course_id}")

    with app.app_context():
        assert Course.query.get(course_id) is not None


def test_export_nudge_hidden_for_a_course_with_no_data(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro to CS", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.commit()
        lecturer_id, course_id = lecturer.id, course.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        response = client.get(f"/courses/{course_id}")
        assert b"Export a CSV backup" not in response.data
        assert b"Delete this course" in response.data


def test_export_nudge_shown_for_a_course_with_a_roster(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro to CS", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.flush()
        database.session.add(Enrollment(course_id=course.id, index_number="PS/ITC/21/0001"))
        database.session.commit()
        lecturer_id, course_id = lecturer.id, course.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        response = client.get(f"/courses/{course_id}")
        assert b"Export a CSV backup" in response.data
