from datetime import datetime, timedelta

from flask import current_app, has_request_context, request
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import IntegrityError

from .devices import hash_device_token
from .extensions import database
from .location import haversine_metres
from .models import MAX_DEVICES, Anomaly, AttendanceRecord, ClassSession, Course, Enrollment, StudentDevice

# Every anomaly row carries one of these type codes; the value is the display label.
ANOMALY_TYPES = {
    "proxy_scan_suspected": "Same device used for several students",
    "new_device": "New device signed in to this account",
    "shared_device": "Signed in on another student's registered phone",
    "geofence_far": "Scan attempted from outside the room",
}

ANOMALY_SEVERITIES = ("info", "warn", "critical")


class ScanResult:
    def __init__(self, status, message, reason=None, code=None):
        self.status = status  # 'present', 'already', or 'rejected'
        self.message = message
        self.reason = reason
        self.code = code  # machine-readable tag so the UI can offer a matching action

    @property
    def accepted(self):
        return self.status in ("present", "already")


def get_live_session(course):
    return ClassSession.query.filter_by(course_id=course.id, ended_at=None, voided=False).first()


def is_enrolled(course, student):
    if Enrollment.query.filter_by(course_id=course.id, student_id=student.id).first():
        return True
    if student.index_number:
        return bool(
            Enrollment.query.filter_by(
                course_id=course.id, index_number=student.index_number
            ).first()
        )
    return False


def live_courses_for_student(lecturer, student):
    # Courses this lecturer has live right now that the student is on the roster for.
    live_sessions = (
        ClassSession.query.join(Course, ClassSession.course_id == Course.id)
        .filter(
            Course.lecturer_id == lecturer.id,
            ClassSession.ended_at.is_(None),
            ClassSession.voided.is_(False),
        )
        .all()
    )
    return [session.course for session in live_sessions if is_enrolled(session.course, student)]


def live_sessions_for_student(student):
    # Live sessions the student can still check in to: enrolled, not yet marked.
    already_marked = exists().where(
        and_(
            AttendanceRecord.session_id == ClassSession.id,
            AttendanceRecord.student_id == student.id,
        )
    )
    live_sessions = (
        ClassSession.query.filter(
            ClassSession.ended_at.is_(None),
            ClassSession.voided.is_(False),
            ~already_marked,
        )
        .all()
    )
    return [session for session in live_sessions if is_enrolled(session.course, student)]


def anomalies_for_lecturer(lecturer_id):
    # Session-bound anomalies belong to the session's course owner; sessionless
    # device events surface to every lecturer the student takes a course with.
    lecturer_course_ids = select(Course.id).where(Course.lecturer_id == lecturer_id)
    enrolled_with_lecturer = exists().where(
        and_(
            Enrollment.student_id == Anomaly.student_id,
            Enrollment.course_id.in_(lecturer_course_ids),
        )
    )
    return Anomaly.query.outerjoin(ClassSession, Anomaly.session_id == ClassSession.id).filter(
        or_(
            ClassSession.course_id.in_(lecturer_course_ids),
            and_(Anomaly.session_id.is_(None), enrolled_with_lecturer),
        )
    )


def count_anomalies(lecturer_id):
    # Sidebar badge — only what still needs a look.
    return anomalies_for_lecturer(lecturer_id).filter(Anomaly.reviewed.is_(False)).count()


def log_anomaly(anomaly_type, severity, student, session=None, device_hash=None, details=None):
    # Best-effort audit insert — a logging failure must never break a scan or sign-in.
    try:
        database.session.add(
            Anomaly(
                anomaly_type=anomaly_type,
                severity=severity,
                reason=ANOMALY_TYPES.get(anomaly_type, anomaly_type),
                student_id=student.id,
                session_id=session.id if session else None,
                device_id=device_hash,
                ip_address=request.remote_addr if has_request_context() else None,
                details=details,
            )
        )
        database.session.commit()
    except Exception:
        database.session.rollback()
        current_app.logger.warning("Anomaly logging failed (%s)", anomaly_type, exc_info=True)


def anomaly_student_ids(session_id):
    return {
        student_id
        for (student_id,) in Anomaly.query.with_entities(Anomaly.student_id)
        .filter_by(session_id=session_id)
        .all()
    }


def find_enrollment(course, student):
    enrollment = Enrollment.query.filter_by(course_id=course.id, student_id=student.id).first()
    if enrollment:
        return enrollment
    if student.index_number:
        enrollment = Enrollment.query.filter_by(
            course_id=course.id, index_number=student.index_number
        ).first()
        if enrollment and not enrollment.student_id:
            enrollment.student_id = student.id
            database.session.commit()
        return enrollment
    return None


def detect_proxy_scan(student, session, device_hash):
    # Someone scanning in for a classmate: the same phone already marked another student.
    if not device_hash:
        return None
    return AttendanceRecord.query.filter(
        AttendanceRecord.session_id == session.id,
        AttendanceRecord.device_id == device_hash,
        AttendanceRecord.student_id != student.id,
    ).first()


def record_scan(student, course, latitude, longitude, accuracy, device_uuid):
    config = current_app.config

    # Every sign-in sets the device cookie, so a scan without one means it was
    # stripped to dodge the device checks. Signing in again restores it.
    if not device_uuid:
        return ScanResult(
            "rejected",
            "We couldn't identify this device. Sign out, sign back in, and scan again.",
        )

    # One lookup covers both the device check and the cap: a scan from an
    # unregistered device is blocked only when the student is already at the cap.
    active_devices = StudentDevice.get_active(student.id)
    device_registered = any(device.device_uuid == device_uuid for device in active_devices)
    if not device_registered and len(active_devices) >= MAX_DEVICES:
        return ScanResult(
            "rejected",
            "This device isn't registered to your account. Remove one of your other devices to scan from here.",
            code="device_limit",
        )

    if not find_enrollment(course, student):
        return ScanResult("rejected", "You're not on this course's roster.")

    session = get_live_session(course)
    if not session:
        return ScanResult("rejected", "There's no live session for this class right now.")

    window_end = session.started_at + timedelta(minutes=config["SCAN_WINDOW_MINUTES"])
    if datetime.utcnow() > window_end:
        return ScanResult("rejected", "The scan window for this class has closed.")

    if AttendanceRecord.query.filter_by(session_id=session.id, student_id=student.id).first():
        return ScanResult("already", "You're already marked present for this class.")

    if latitude is None or longitude is None or accuracy is None:
        return ScanResult("rejected", "We couldn't read your location. Allow location access and try again.")

    if accuracy > config["GPS_ACCURACY_LIMIT_M"]:
        return ScanResult("rejected", "Your GPS signal is too weak to trust. Move into the open and try again.")

    if session.latitude is None or session.longitude is None:
        return ScanResult("rejected", "This session doesn't have a room location set.")

    device_hash = hash_device_token(device_uuid)

    distance = haversine_metres(latitude, longitude, session.latitude, session.longitude)
    # GPS error cuts both ways: a student truly in the room can read tens of
    # metres out. Allow the radius plus both fixes' reported accuracy (each
    # already capped by the accuracy gate / the same limit).
    session_accuracy = min(session.location_accuracy or 0.0, config["GPS_ACCURACY_LIMIT_M"])
    allowed_distance = config["CLASSROOM_RADIUS_M"] + accuracy + session_accuracy
    if distance > allowed_distance:
        log_anomaly(
            "geofence_far",
            "info",
            student,
            session=session,
            device_hash=device_hash,
            details={
                "distance_m": round(distance),
                "allowed_m": round(allowed_distance),
                "radius_m": round(config["CLASSROOM_RADIUS_M"]),
                "accuracy_m": round(accuracy),
            },
        )
        return ScanResult(
            "rejected",
            f"You're not inside the classroom — your phone places you about {round(distance)} m from the room.",
        )

    database.session.add(
        AttendanceRecord(
            session_id=session.id,
            student_id=student.id,
            status="present",
            scanned_at=datetime.utcnow(),
            latitude=latitude,
            longitude=longitude,
            device_id=device_hash,
        )
    )
    try:
        database.session.commit()
    except IntegrityError:
        database.session.rollback()
        existing_record = AttendanceRecord.query.filter_by(
            session_id=session.id, student_id=student.id
        ).first()
        if existing_record and existing_record.status == "absent":
            # The session ended mid-scan and mark_absentees won the race; the
            # scan passed every check while live, so the student is present.
            existing_record.status = "present"
            existing_record.scanned_at = datetime.utcnow()
            existing_record.latitude = latitude
            existing_record.longitude = longitude
            existing_record.device_id = device_hash
            database.session.commit()
        else:
            # A near-simultaneous double-scan already inserted the record.
            return ScanResult("already", "You're already marked present for this class.")

    # Checked after commit so two same-phone scans landing together can't both
    # slip past a pre-insert check that saw an empty table.
    proxy_record = detect_proxy_scan(student, session, device_hash)
    if proxy_record:
        log_anomaly(
            "proxy_scan_suspected",
            "warn",
            student,
            session=session,
            device_hash=device_hash,
            details={
                "shared_with": proxy_record.student.full_name,
                "shared_with_index": proxy_record.student.index_number,
            },
        )

    return ScanResult("present", "You're marked present.")


class OverrideResult:
    def __init__(self, ok, message):
        self.ok = ok
        self.message = message


def apply_manual_override(record, session, lecturer, reason):
    # A lecturer marking an absent student present by hand — e.g. a dead phone
    # or failed GPS fix. Requires a reason and only ever touches an absent
    # record on a finished session, so a real scan can never be overwritten.
    reason = (reason or "").strip()
    if session.voided or session.is_live:
        return OverrideResult(False, "You can only mark someone present after the session has ended.")
    if record.status != "absent":
        return OverrideResult(False, "That student is already marked present.")
    if not reason:
        return OverrideResult(False, "Enter a reason for the manual override.")

    record.status = "present"
    record.override_reason = reason
    record.overridden_by_id = lecturer.id
    record.overridden_at = datetime.utcnow()
    database.session.commit()
    return OverrideResult(True, f"{record.student.full_name} marked present.")


def revert_manual_override(record):
    # Undoes a manual override back to absent. Only acts on a record that
    # actually carries an override — never on a real scan.
    if not record.overridden_by_id:
        return OverrideResult(False, "This record wasn't manually overridden.")

    record.status = "absent"
    record.override_reason = None
    record.overridden_by_id = None
    record.overridden_at = None
    database.session.commit()
    return OverrideResult(True, "Manual override undone — back to absent.")


def mark_absentees(session):
    # On session end, enrolled students with a linked account and no record are absent.
    recorded_ids = {
        record.student_id
        for record in AttendanceRecord.query.filter_by(session_id=session.id).all()
    }
    enrollments = Enrollment.query.filter(
        Enrollment.course_id == session.course_id,
        Enrollment.student_id.isnot(None),
    ).all()
    for enrollment in enrollments:
        if enrollment.student_id in recorded_ids:
            continue
        # Savepoint per row: a scan committing mid-loop only skips its own row
        # instead of failing the whole absentee commit.
        try:
            with database.session.begin_nested():
                database.session.add(
                    AttendanceRecord(
                        session_id=session.id,
                        student_id=enrollment.student_id,
                        status="absent",
                    )
                )
                database.session.flush()
        except IntegrityError:
            pass
    database.session.commit()
