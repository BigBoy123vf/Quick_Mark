from collections import defaultdict
from datetime import datetime

from sqlalchemy import and_, exists, or_

from .devices import browser_name, device_label, operating_system
from .models import AttendanceRecord, ClassSession, Course, Enrollment, StudentDevice, User


def device_display(device):
    cores = f"{device.cpu_cores} cores" if device.cpu_cores else None
    memory = f"{device.device_memory:g} GB RAM" if device.device_memory else None
    hardware = " · ".join(part for part in (cores, memory) if part)
    return {
        "name": device.device_name or device_label(device.user_agent),
        "model": device.device_model,
        "os": operating_system(device.user_agent),
        "browser": browser_name(device.user_agent),
        "screen": device.screen,
        "hardware": hardware or None,
        "timezone": device.timezone,
        "ip": device.last_seen_ip or device.first_seen_ip,
        "last_seen": device.last_seen_at,
        "created_at": device.created_at,
        "removed": device.deleted_at is not None,
    }


def ended_sessions_count(course_id):
    return ClassSession.query.filter(
        ClassSession.course_id == course_id,
        ClassSession.ended_at.isnot(None),
        ClassSession.voided.is_(False),
    ).count()


def summary_from_counts(present, total):
    percentage = round(present / total * 100) if total else None
    return {"present": present, "total": total, "absent": total - present, "percentage": percentage}


def attendance_summary(course_id, student_id):
    total = ended_sessions_count(course_id)
    present = (
        AttendanceRecord.query.join(ClassSession, AttendanceRecord.session_id == ClassSession.id)
        .filter(
            ClassSession.course_id == course_id,
            ClassSession.ended_at.isnot(None),
            ClassSession.voided.is_(False),
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.status == "present",
        )
        .count()
    )
    return summary_from_counts(present, total)


def present_counts_by_student(course_id, ended_session_ids):
    # One pass over the course's present records, counted only within ended sessions.
    counts = {}
    if not ended_session_ids:
        return counts
    records = (
        AttendanceRecord.query.filter(
            AttendanceRecord.session_id.in_(ended_session_ids),
            AttendanceRecord.status == "present",
        ).all()
    )
    for record in records:
        counts[record.student_id] = counts.get(record.student_id, 0) + 1
    return counts


def student_courses_with_history(student):
    enrollments = (
        Enrollment.query.filter_by(student_id=student.id)
        .join(Course, Enrollment.course_id == Course.id)
        .order_by(Course.code)
        .all()
    )
    if not enrollments:
        return []

    course_ids = [enrollment.course_id for enrollment in enrollments]
    # A live session shows up as soon as this student scans, so the present
    # mark is visible immediately; live sessions they haven't scanned stay
    # hidden — absence only exists once the lecturer ends the session.
    marked_present_in_session = exists().where(
        and_(
            AttendanceRecord.session_id == ClassSession.id,
            AttendanceRecord.student_id == student.id,
            AttendanceRecord.status == "present",
        )
    )
    sessions = (
        ClassSession.query.filter(
            ClassSession.course_id.in_(course_ids),
            ClassSession.voided.is_(False),
            or_(ClassSession.ended_at.isnot(None), marked_present_in_session),
        )
        .order_by(ClassSession.started_at.desc())
        .all()
    )

    session_ids = [session.id for session in sessions]
    present_session_ids = set()
    if session_ids:
        present_session_ids = {
            record.session_id
            for record in AttendanceRecord.query.filter(
                AttendanceRecord.student_id == student.id,
                AttendanceRecord.session_id.in_(session_ids),
                AttendanceRecord.status == "present",
            ).all()
        }

    sessions_by_course = defaultdict(list)
    for session in sessions:
        sessions_by_course[session.course_id].append(session)

    result = []
    for enrollment in enrollments:
        course_sessions = sessions_by_course[enrollment.course_id]
        present_count = sum(1 for session in course_sessions if session.id in present_session_ids)
        summary = summary_from_counts(present_count, len(course_sessions))
        history = [(session, session.id in present_session_ids) for session in course_sessions]
        result.append((enrollment.course, summary, history))
    return result


def relative_activity_label(when, now=None):
    now = now or datetime.utcnow()
    if when.date() == now.date():
        return when.strftime("%H:%M")
    if 0 <= (now.date() - when.date()).days <= 6:
        return when.strftime("%a")
    return when.strftime("%d %b")


def recent_activity(course_data, limit=5):
    # Flattens each course's (session, attended) history into one feed, newest first.
    events = []
    for course, _summary, history in course_data:
        for session, attended in history:
            events.append({
                "course": course,
                "attended": attended,
                "when": session.started_at,
                "when_label": relative_activity_label(session.started_at),
            })
    events.sort(key=lambda event: event["when"], reverse=True)
    return events[:limit]


def student_course_history(course_id, student_id):
    sessions = (
        ClassSession.query.filter(
            ClassSession.course_id == course_id,
            ClassSession.ended_at.isnot(None),
            ClassSession.voided.is_(False),
        )
        .order_by(ClassSession.started_at.desc())
        .all()
    )
    session_ids = [session.id for session in sessions]
    present_session_ids = set()
    if session_ids:
        present_session_ids = {
            record.session_id
            for record in AttendanceRecord.query.filter(
                AttendanceRecord.student_id == student_id,
                AttendanceRecord.session_id.in_(session_ids),
                AttendanceRecord.status == "present",
            ).all()
        }
    return [(session, session.id in present_session_ids) for session in sessions]


def course_roster_stats(course):
    enrollments = (
        Enrollment.query.filter_by(course_id=course.id)
        .order_by(Enrollment.index_number)
        .all()
    )
    ended_session_ids = {
        session_id
        for (session_id,) in ClassSession.query.with_entities(ClassSession.id)
        .filter(
            ClassSession.course_id == course.id,
            ClassSession.ended_at.isnot(None),
            ClassSession.voided.is_(False),
        )
        .all()
    }
    total_ended = len(ended_session_ids)
    present_counts = present_counts_by_student(course.id, ended_session_ids)
    summaries = {
        enrollment.student_id: summary_from_counts(
            present_counts.get(enrollment.student_id, 0), total_ended
        )
        for enrollment in enrollments
        if enrollment.student_id
    }
    return enrollments, summaries


def course_sessions_overview(course):
    sessions = (
        ClassSession.query.filter_by(course_id=course.id)
        .order_by(ClassSession.started_at.desc())
        .all()
    )
    overview = []
    for session in sessions:
        present = AttendanceRecord.query.filter_by(
            session_id=session.id, status="present"
        ).count()
        overview.append((session, present))
    return overview


def session_breakdown(session):
    present = AttendanceRecord.query.filter_by(session_id=session.id, status="present").all()
    absent = AttendanceRecord.query.filter_by(session_id=session.id, status="absent").all()
    return present, absent


def roster_names_for_course(course_id):
    # Lecturer views show the name as uploaded on the roster, not whatever the
    # student typed at sign-up; account name stays the fallback.
    return {
        enrollment.student_id: enrollment.full_name
        for enrollment in Enrollment.query.filter_by(course_id=course_id)
        if enrollment.student_id and enrollment.full_name
    }


def course_attendance_matrix(course):
    sessions = (
        ClassSession.query.filter(
            ClassSession.course_id == course.id,
            ClassSession.voided.is_(False),
        )
        .order_by(ClassSession.started_at)
        .all()
    )
    enrollments = (
        Enrollment.query.filter_by(course_id=course.id)
        .order_by(Enrollment.index_number)
        .all()
    )
    records = (
        AttendanceRecord.query.join(ClassSession, AttendanceRecord.session_id == ClassSession.id)
        .filter(ClassSession.course_id == course.id)
        .all()
    )
    status_by_student_session = {
        (record.student_id, record.session_id): record.status for record in records
    }
    ended_session_ids = {session.id for session in sessions if session.ended_at is not None}
    total_ended = len(ended_session_ids)
    present_counts = {}
    for record in records:
        if record.status == "present" and record.session_id in ended_session_ids:
            present_counts[record.student_id] = present_counts.get(record.student_id, 0) + 1

    rows = []
    for enrollment in enrollments:
        cells = []
        for session in sessions:
            status = status_by_student_session.get((enrollment.student_id, session.id))
            cells.append("Present" if status == "present" else ("Absent" if status == "absent" else "-"))

        if enrollment.student_id:
            present = present_counts.get(enrollment.student_id, 0)
            total = total_ended
            percentage = round(present / total * 100) if total else None
        else:
            present, total, percentage = 0, total_ended, None

        roster_name = enrollment.full_name or (
            enrollment.student.full_name if enrollment.student_id else None
        )
        rows.append(
            {
                "index_number": enrollment.index_number,
                "name": roster_name,
                "cells": cells,
                "present": present,
                "total": total,
                "percentage": percentage,
            }
        )
    return sessions, rows


def courses_overview(lecturer_id):
    # One row per course for the Courses register: enrolment, average attendance,
    # and whether a session is live right now (with its present count).
    courses = Course.query.filter_by(lecturer_id=lecturer_id).order_by(Course.code).all()
    result = []
    for course in courses:
        enrollments, summaries = course_roster_stats(course)
        percentages = [
            summary["percentage"] for summary in summaries.values() if summary["percentage"] is not None
        ]
        average = round(sum(percentages) / len(percentages)) if percentages else None
        live_session = ClassSession.query.filter_by(
            course_id=course.id, ended_at=None, voided=False
        ).first()
        present = 0
        if live_session:
            present = AttendanceRecord.query.filter_by(
                session_id=live_session.id, status="present"
            ).count()
        result.append({
            "course": course,
            "enrolled": len(enrollments),
            "live": live_session is not None,
            "present": present,
            "average": average,
        })
    result.sort(key=lambda row: (not row["live"], row["course"].code))
    return result


# Below this attendance percentage, a student is flagged as at-risk.
LOW_ATTENDANCE_THRESHOLD = 75


def low_attendance_by_course(lecturer_id, threshold=LOW_ATTENDANCE_THRESHOLD):
    courses = Course.query.filter_by(lecturer_id=lecturer_id).order_by(Course.code).all()
    result = []
    for course in courses:
        enrollments, summaries = course_roster_stats(course)
        at_risk = []
        for enrollment in enrollments:
            summary = summaries.get(enrollment.student_id)
            if not summary or summary["percentage"] is None or summary["percentage"] >= threshold:
                continue
            history = student_course_history(course.id, enrollment.student_id)
            marks = [present for _session, present in reversed(history)]
            at_risk.append({"enrollment": enrollment, "summary": summary, "marks": marks})
        if at_risk:
            result.append((course, at_risk))
    return result


def count_low_attendance_students(lecturer_id, threshold=LOW_ATTENDANCE_THRESHOLD):
    # Sidebar badge — same at-risk definition as low_attendance_by_course, but
    # skips the per-student session-history lookup the full list needs to draw
    # its dots, since a badge only needs the count.
    courses = Course.query.filter_by(lecturer_id=lecturer_id).all()
    count = 0
    for course in courses:
        _enrollments, summaries = course_roster_stats(course)
        count += sum(
            1
            for summary in summaries.values()
            if summary["percentage"] is not None and summary["percentage"] < threshold
        )
    return count


def student_device_summary(lecturer_id):
    enrollments = (
        Enrollment.query.join(Course, Enrollment.course_id == Course.id)
        .filter(Course.lecturer_id == lecturer_id, Enrollment.student_id.isnot(None))
        .all()
    )
    student_ids = list({enrollment.student_id for enrollment in enrollments})
    if not student_ids:
        return []

    students = {student.id: student for student in User.query.filter(User.id.in_(student_ids)).all()}
    all_devices = (
        StudentDevice.query.filter(StudentDevice.student_id.in_(student_ids))
        .order_by(StudentDevice.student_id, StudentDevice.created_at)
        .all()
    )
    devices_by_student = defaultdict(list)
    for device in all_devices:
        devices_by_student[device.student_id].append(device)

    rows = []
    for student_id in student_ids:
        student = students.get(student_id)
        if not student:
            continue
        student_devices = devices_by_student[student_id]
        active = [device for device in student_devices if device.deleted_at is None]
        removed = [device for device in student_devices if device.deleted_at is not None]
        rows.append({
            "student": student,
            "active_count": len(active),
            "total_count": len(student_devices),
            "switch_count": len(removed),
            "devices": [device_display(device) for device in student_devices],
        })

    rows.sort(key=lambda row: row["switch_count"], reverse=True)
    return rows
