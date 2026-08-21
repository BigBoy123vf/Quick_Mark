from datetime import time as time_type

from app.extensions import database
from app.models import ClassScheduleSlot, Course, User


def make_lecturer(email="lecturer@example.com"):
    lecturer = User(email=email, role="admin", full_name="Lecturer")
    database.session.add(lecturer)
    database.session.commit()
    return lecturer


def login_as(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def test_creating_a_course_with_schedule_rows_saves_the_slots(app):
    with app.app_context():
        lecturer = make_lecturer()
        lecturer_id = lecturer.id

    with app.test_client() as client:
        login_as(client, lecturer)
        response = client.post(
            "/courses/new",
            data={
                "code": "CS101",
                "title": "Intro to CS",
                "schedule_day": ["0", "2"],
                "schedule_time": ["09:00", "14:00"],
            },
        )
        assert response.status_code == 302

    with app.app_context():
        course = Course.query.filter_by(lecturer_id=lecturer_id, code="CS101").first()
        assert course is not None
        slots = sorted((slot.day_of_week, slot.start_time) for slot in course.schedule_slots)
        assert len(slots) == 2


def test_adding_a_schedule_slot_from_the_course_detail_page(app):
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
            f"/courses/{course_id}/schedule",
            data={"day_of_week": "1", "start_time": "10:30"},
        )
        assert response.status_code == 302

    with app.app_context():
        slots = ClassScheduleSlot.query.filter_by(course_id=course_id).all()
        assert len(slots) == 1
        assert slots[0].day_of_week == 1


def test_deleting_a_schedule_slot(app):
    with app.app_context():
        lecturer = make_lecturer()
        course = Course(code="CS101", title="Intro to CS", lecturer_id=lecturer.id)
        database.session.add(course)
        database.session.flush()
        slot = ClassScheduleSlot(course_id=course.id, day_of_week=1, start_time=time_type(10, 30))
        database.session.add(slot)
        database.session.commit()
        lecturer_id, course_id, slot_id = lecturer.id, course.id, slot.id

    with app.test_client() as client:
        with app.app_context():
            login_as(client, User.query.get(lecturer_id))
        response = client.post(f"/courses/{course_id}/schedule/{slot_id}/delete")
        assert response.status_code == 302

    with app.app_context():
        assert ClassScheduleSlot.query.get(slot_id) is None


def test_cannot_add_a_schedule_slot_to_another_lecturers_course(app):
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
        response = client.post(
            f"/courses/{course_id}/schedule",
            data={"day_of_week": "1", "start_time": "10:30"},
        )
        assert response.status_code == 403
