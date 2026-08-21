from flask import Blueprint, render_template
from flask_login import current_user

from ..permissions import lecturer_required
from ..stats import LOW_ATTENDANCE_THRESHOLD, low_attendance_by_course, student_device_summary

review_bp = Blueprint("review", __name__, url_prefix="/review")


@review_bp.route("/low-attendance")
@lecturer_required
def low_attendance():
    by_course = low_attendance_by_course(current_user.id, LOW_ATTENDANCE_THRESHOLD)
    total = sum(len(students) for _, students in by_course)
    return render_template(
        "review/low_attendance.html",
        by_course=by_course,
        threshold=LOW_ATTENDANCE_THRESHOLD,
        total=total,
    )


@review_bp.route("/devices")
@lecturer_required
def student_devices():
    rows = student_device_summary(current_user.id)
    return render_template("review/devices.html", rows=rows)
