from app.extensions import database
from app.models import ClassSession, Course, User


def make_lecturer(email="lecturer@example.com"):
    lecturer = User(email=email, role="admin", full_name="Lecturer")
    database.session.add(lecturer)
    database.session.commit()
    return lecturer


def login_as(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def test_starting_a_session_with_a_manually_picked_point_and_no_accuracy_succeeds(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro to CS", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.commit()
        lecturer_id, course_id = lecturer.id, course.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        response = client.post(
            f"/courses/{course_id}/sessions/start",
            data={"latitude": "5.1053", "longitude": "-1.2466", "accuracy": ""},
        )
        assert response.status_code == 302

    with app.app_context():
        session = ClassSession.query.filter_by(course_id=course_id).first()
        assert session is not None
        assert session.latitude == 5.1053
        assert session.longitude == -1.2466
        assert session.location_accuracy is None


def test_starting_a_session_remembers_the_location_on_the_course(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro to CS", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.commit()
        lecturer_id, course_id = lecturer.id, course.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        client.post(
            f"/courses/{course_id}/sessions/start",
            data={"latitude": "5.1053", "longitude": "-1.2466", "accuracy": "12.5"},
        )

    with app.app_context():
        course = Course.query.get(course_id)
        assert course.last_location_latitude == 5.1053
        assert course.last_location_longitude == -1.2466
        assert course.last_location_accuracy == 12.5


def test_a_later_session_overwrites_the_courses_remembered_location(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro to CS", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.commit()
        lecturer_id, course_id = lecturer.id, course.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))

        client.post(
            f"/courses/{course_id}/sessions/start",
            data={"latitude": "5.1053", "longitude": "-1.2466", "accuracy": "12.5"},
        )
        with app.app_context():
            live_session = ClassSession.query.filter_by(course_id=course_id).first()
            live_session.ended_at = live_session.started_at
            database.session.commit()

        client.post(
            f"/courses/{course_id}/sessions/start",
            data={"latitude": "5.2", "longitude": "-1.3", "accuracy": ""},
        )

    with app.app_context():
        course = Course.query.get(course_id)
        assert course.last_location_latitude == 5.2
        assert course.last_location_longitude == -1.3
        assert course.last_location_accuracy is None


def test_starting_a_session_with_no_location_creates_a_null_location_session_and_turns_it_off(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro to CS", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.commit()
        lecturer_id, course_id = lecturer.id, course.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        response = client.post(
            f"/courses/{course_id}/sessions/start",
            data={"no_location": "1", "latitude": "", "longitude": "", "accuracy": ""},
        )
        assert response.status_code == 302

    with app.app_context():
        session = ClassSession.query.filter_by(course_id=course_id).first()
        assert session is not None
        assert session.latitude is None
        assert session.longitude is None
        course = Course.query.get(course_id)
        assert course.requires_location is False


def test_starting_without_location_preserves_a_previously_remembered_location(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro to CS", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.commit()
        lecturer_id, course_id = lecturer.id, course.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))

        client.post(
            f"/courses/{course_id}/sessions/start",
            data={"latitude": "5.1053", "longitude": "-1.2466", "accuracy": "12.5"},
        )
        with app.app_context():
            live_session = ClassSession.query.filter_by(course_id=course_id).first()
            live_session.ended_at = live_session.started_at
            database.session.commit()

        client.post(
            f"/courses/{course_id}/sessions/start",
            data={"no_location": "1", "latitude": "", "longitude": "", "accuracy": ""},
        )

    with app.app_context():
        course = Course.query.get(course_id)
        assert course.requires_location is False
        assert course.last_location_latitude == 5.1053
        assert course.last_location_longitude == -1.2466


def test_starting_with_a_location_turns_requires_location_back_on(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro to CS", lecturer_id=lecturer.id, requires_location=False)
        database.session.add(course)
        database.session.commit()
        lecturer_id, course_id = lecturer.id, course.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        client.post(
            f"/courses/{course_id}/sessions/start",
            data={"latitude": "5.1053", "longitude": "-1.2466", "accuracy": ""},
        )

    with app.app_context():
        course = Course.query.get(course_id)
        assert course.requires_location is True
