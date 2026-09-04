from app.extensions import database
from app.models import Course, User


def make_lecturer(email="lecturer@example.com"):
    lecturer = User(email=email, role="admin", full_name="Lecturer")
    database.session.add(lecturer)
    database.session.commit()
    return lecturer


def login_as(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def get_course_page(app, course_kwargs):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro to CS", lecturer_id=lecturer.id, **course_kwargs)
        database.session.add(course)
        database.session.commit()
        lecturer_id, course_id = lecturer.id, course.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        return client.get(f"/courses/{course_id}")


def test_state_a_fresh_course_offers_set_location_or_skip_it(app):
    response = get_course_page(app, {})
    assert response.status_code == 200
    assert b"Set a room location" in response.data
    assert b"Start without a location" in response.data
    assert b"Use last room location" not in response.data
    assert b"location-picker-backdrop" in response.data


def test_state_b_location_on_with_remembered_spot_offers_one_tap_start(app):
    response = get_course_page(app, {
        "last_location_latitude": 5.1053,
        "last_location_longitude": -1.2466,
        "last_location_accuracy": 12.5,
    })
    assert response.status_code == 200
    assert b"Pick a different spot on the map" in response.data
    assert b"Start without a location instead" in response.data
    assert b"Use last room location" not in response.data


def test_state_c_location_off_with_nothing_remembered_offers_bare_start(app):
    response = get_course_page(app, {"requires_location": False})
    assert response.status_code == 200
    assert b"Set a room location" in response.data
    assert b"Start without a location" not in response.data
    assert b"Use last room location" not in response.data


def test_state_d_location_off_with_remembered_spot_offers_reenable(app):
    response = get_course_page(app, {
        "requires_location": False,
        "last_location_latitude": 5.1053,
        "last_location_longitude": -1.2466,
        "last_location_accuracy": 12.5,
    })
    assert response.status_code == 200
    assert b"Use last room location" in response.data
    assert b"Pick a different spot on the map" in response.data
