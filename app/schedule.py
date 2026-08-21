from datetime import datetime, time, timedelta

from .attendance import live_sessions_for_student
from .models import ClassScheduleSlot, Enrollment


def parse_schedule_rows(days, times):
    # Mirrors parse_roster_rows: silently drops half-filled or invalid rows
    # rather than erroring, since these come from repeatable "add another" form rows.
    rows = []
    for day_raw, time_raw in zip(days, times):
        day_raw = (day_raw or "").strip()
        time_raw = (time_raw or "").strip()
        if not day_raw or not time_raw:
            continue
        try:
            day_of_week = int(day_raw)
            hours, minutes = time_raw.split(":")
            start_time = time(int(hours), int(minutes))
        except (ValueError, TypeError):
            continue
        if not 0 <= day_of_week <= 6:
            continue
        rows.append((day_of_week, start_time))
    return rows


def next_occurrence(slot, now):
    days_ahead = (slot.day_of_week - now.weekday()) % 7
    candidate = datetime.combine((now + timedelta(days=days_ahead)).date(), slot.start_time)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def next_class_relative_label(when, now=None):
    now = now or datetime.utcnow()
    time_label = when.strftime("%I:%M %p")
    if when.date() == now.date():
        return f"Today · {time_label}"
    if when.date() == (now + timedelta(days=1)).date():
        return f"Tomorrow · {time_label}"
    return f"{when.strftime('%a')} · {time_label}"


def next_class_for_student(student, now=None):
    now = now or datetime.utcnow()

    # A course that's live right now already has its own "scan now" banner;
    # don't also tell the student it's coming up.
    live_course_ids = {session.course_id for session in live_sessions_for_student(student)}

    course_ids = [
        enrollment.course_id
        for enrollment in Enrollment.query.filter_by(student_id=student.id).all()
        if enrollment.course_id not in live_course_ids
    ]
    if not course_ids:
        return None

    slots = ClassScheduleSlot.query.filter(ClassScheduleSlot.course_id.in_(course_ids)).all()

    soonest = None
    for slot in slots:
        occurrence = next_occurrence(slot, now)
        if soonest is None or occurrence < soonest["when"]:
            soonest = {"course": slot.course, "slot": slot, "when": occurrence}
    return soonest
