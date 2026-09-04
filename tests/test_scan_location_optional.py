from app.attendance import record_scan
from app.extensions import database
from app.models import AttendanceRecord, ClassSession, Course, Enrollment, StudentDevice, User

ROOM_LATITUDE = 5.6037
ROOM_LONGITUDE = -0.1870


def make_lecturer(email="lecturer@example.com"):
    lecturer = User(email=email, role="admin", full_name="Lecturer")
    database.session.add(lecturer)
    database.session.flush()
    return lecturer


def make_student(index_number="STU1", email="student@example.com"):
    student = User(email=email, role="student", full_name="Student One", index_number=index_number)
    database.session.add(student)
    database.session.flush()
    device_uuid = f"device-{index_number}"
    database.session.add(StudentDevice(student_id=student.id, device_uuid=device_uuid, device_name="Phone"))
    database.session.flush()
    return student, device_uuid


def make_course_with_student(lecturer, student, **session_kwargs):
    course = Course(code="CS101", title="Intro", lecturer_id=lecturer.id)
    database.session.add(course)
    database.session.flush()
    database.session.add(
        Enrollment(course_id=course.id, index_number=student.index_number, student_id=student.id)
    )
    session = ClassSession(course_id=course.id, **session_kwargs)
    database.session.add(session)
    database.session.flush()
    return course, session


def test_scan_marks_present_with_no_location_when_session_has_no_location(app):
    with app.app_context():
        lecturer = make_lecturer()
        student, device_uuid = make_student()
        course, session = make_course_with_student(lecturer, student)
        database.session.commit()

        result = record_scan(student, course, None, None, None, device_uuid)

        assert result.status == "present"
        record = AttendanceRecord.query.filter_by(session_id=session.id, student_id=student.id).first()
        assert record is not None
        assert record.latitude is None
        assert record.longitude is None


def test_scan_rejects_missing_location_when_session_requires_it(app):
    with app.app_context():
        lecturer = make_lecturer()
        student, device_uuid = make_student()
        course, session = make_course_with_student(
            lecturer, student, latitude=ROOM_LATITUDE, longitude=ROOM_LONGITUDE, location_accuracy=5.0
        )
        database.session.commit()

        result = record_scan(student, course, None, None, None, device_uuid)

        assert result.status == "rejected"
        assert AttendanceRecord.query.filter_by(session_id=session.id, student_id=student.id).first() is None


def test_scan_still_enforces_the_geofence_when_session_has_a_location(app):
    with app.app_context():
        lecturer = make_lecturer()
        student, device_uuid = make_student()
        course, session = make_course_with_student(
            lecturer, student, latitude=ROOM_LATITUDE, longitude=ROOM_LONGITUDE, location_accuracy=5.0
        )
        database.session.commit()

        # A point roughly a kilometre away, well outside any reasonable room radius.
        far_latitude = ROOM_LATITUDE + 0.01
        result = record_scan(student, course, far_latitude, ROOM_LONGITUDE, 5.0, device_uuid)

        assert result.status == "rejected"
        assert AttendanceRecord.query.filter_by(session_id=session.id, student_id=student.id).first() is None


def test_scan_still_marks_present_inside_the_geofence_when_session_has_a_location(app):
    with app.app_context():
        lecturer = make_lecturer()
        student, device_uuid = make_student()
        course, session = make_course_with_student(
            lecturer, student, latitude=ROOM_LATITUDE, longitude=ROOM_LONGITUDE, location_accuracy=5.0
        )
        database.session.commit()

        result = record_scan(student, course, ROOM_LATITUDE, ROOM_LONGITUDE, 5.0, device_uuid)

        assert result.status == "present"
        record = AttendanceRecord.query.filter_by(session_id=session.id, student_id=student.id).first()
        assert record is not None
        assert record.latitude == ROOM_LATITUDE
        assert record.longitude == ROOM_LONGITUDE
