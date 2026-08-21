import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.attendance import record_scan
from app.extensions import database
from app.models import (
    AttendanceRecord,
    ClassSession,
    Course,
    Enrollment,
    StudentDevice,
    User,
)

# How many people scan at once, and the p95 latency ceiling (ms) a scan must
# stay under. Both overridable from the shell so you can crank the load.
SCAN_LOAD_N = int(os.environ.get("SCAN_LOAD_N", "100"))
P95_MAX_MS = float(os.environ.get("P95_MAX_MS", "250"))

ROOM_LATITUDE = 5.6037
ROOM_LONGITUDE = -0.1870


def make_lecturer(email):
    lecturer = User(email=email, role="admin", full_name="Lecturer")
    lecturer.qr_token = email.split("@")[0]
    database.session.add(lecturer)
    database.session.flush()
    return lecturer


def make_live_course(lecturer, code):
    course = Course(code=code, title=f"Course {code}", lecturer_id=lecturer.id)
    database.session.add(course)
    database.session.flush()
    session = ClassSession(
        course_id=course.id,
        latitude=ROOM_LATITUDE,
        longitude=ROOM_LONGITUDE,
        location_accuracy=5.0,
    )
    database.session.add(session)
    database.session.flush()
    return course, session


def make_student(course, index_number, email):
    student = User(
        email=email,
        role="student",
        full_name=f"Student {index_number}",
        index_number=index_number,
    )
    database.session.add(student)
    database.session.flush()
    device_uuid = f"device-{index_number}"
    database.session.add(
        StudentDevice(student_id=student.id, device_uuid=device_uuid, device_name="Phone")
    )
    database.session.add(
        Enrollment(course_id=course.id, index_number=index_number, student_id=student.id)
    )
    database.session.flush()
    return student.id, device_uuid


def fire_scan(app, student_id, course_id, device_uuid, barrier):
    # Each thread runs in its own app context so it gets its own DB session,
    # then all threads release from the barrier together for true contention.
    barrier.wait()
    started = time.perf_counter()
    with app.app_context():
        student = database.session.get(User, student_id)
        course = database.session.get(Course, course_id)
        result = record_scan(
            student, course, ROOM_LATITUDE, ROOM_LONGITUDE, 5.0, device_uuid
        )
        status = result.status
        database.session.remove()
    elapsed_ms = (time.perf_counter() - started) * 1000
    return status, elapsed_ms


def percentile(values, fraction):
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def report_latency(label, latencies):
    p50 = percentile(latencies, 0.50)
    p95 = percentile(latencies, 0.95)
    p99 = percentile(latencies, 0.99)
    print(
        f"\n[{label}] n={len(latencies)}  "
        f"p50={p50:.1f}ms  p95={p95:.1f}ms  p99={p99:.1f}ms  max={max(latencies):.1f}ms"
    )
    return p95


def test_same_student_and_session_yields_exactly_one_record(app):
    with app.app_context():
        lecturer = make_lecturer("dup@school.test")
        course, session = make_live_course(lecturer, "DUP101")
        student_id, device_uuid = make_student(course, "IDX-DUP", "dup.student@school.test")
        database.session.commit()
        course_id = course.id
        session_id = session.id

    barrier = threading.Barrier(SCAN_LOAD_N)
    with ThreadPoolExecutor(max_workers=SCAN_LOAD_N) as pool:
        outcomes = list(
            pool.map(
                lambda _: fire_scan(app, student_id, course_id, device_uuid, barrier),
                range(SCAN_LOAD_N),
            )
        )

    statuses = [status for status, _ in outcomes]
    latencies = [ms for _, ms in outcomes]
    report_latency("same-student x%d" % SCAN_LOAD_N, latencies)

    with app.app_context():
        record_count = AttendanceRecord.query.filter_by(session_id=session_id).count()

    assert record_count == 1, f"DUPLICATE: {record_count} records for one student+session"
    assert statuses.count("present") == 1, f"expected 1 'present', got {statuses.count('present')}"
    assert statuses.count("already") == SCAN_LOAD_N - 1


def test_many_students_two_lecturers_concurrent(app):
    with app.app_context():
        lecturer_one = make_lecturer("lec1@school.test")
        lecturer_two = make_lecturer("lec2@school.test")
        course_one, session_one = make_live_course(lecturer_one, "TEN101")
        course_two, session_two = make_live_course(lecturer_two, "TEN202")

        scans = []
        session_by_course = {course_one.id: session_one.id, course_two.id: session_two.id}
        for number in range(SCAN_LOAD_N):
            course = course_one if number % 2 == 0 else course_two
            student_id, device_uuid = make_student(
                course, f"IDX-{number}", f"student{number}@school.test"
            )
            scans.append((student_id, course.id, device_uuid))
        database.session.commit()

    barrier = threading.Barrier(SCAN_LOAD_N)
    with ThreadPoolExecutor(max_workers=SCAN_LOAD_N) as pool:
        outcomes = list(
            pool.map(
                lambda scan: fire_scan(app, scan[0], scan[1], scan[2], barrier),
                scans,
            )
        )

    statuses = [status for status, _ in outcomes]
    latencies = [ms for _, ms in outcomes]
    p95 = report_latency("distinct-students-2-tenants x%d" % SCAN_LOAD_N, latencies)

    with app.app_context():
        total = AttendanceRecord.query.count()
        per_session = {
            session_id: AttendanceRecord.query.filter_by(session_id=session_id).count()
            for session_id in session_by_course.values()
        }

    assert statuses.count("present") == SCAN_LOAD_N, "every distinct student should be marked once"
    assert total == SCAN_LOAD_N, f"expected {SCAN_LOAD_N} records, got {total} (duplicate or leak)"
    assert sum(per_session.values()) == SCAN_LOAD_N, "records leaked across tenants"
    assert p95 < P95_MAX_MS, f"p95 {p95:.1f}ms exceeded threshold {P95_MAX_MS}ms"
