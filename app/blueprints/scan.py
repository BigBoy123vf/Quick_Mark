import time
from datetime import datetime

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_required

from ..attendance import live_courses_for_student, record_scan
from ..devices import DEVICE_COOKIE_NAME
from ..extensions import limiter
from ..models import MAX_DEVICES, Course, StudentDevice, User
from ..utils import parse_coordinate, parse_int

scan_bp = Blueprint("scan", __name__)


def scan_rate_key():
    # Rate-limit each student account, not the shared campus IP everyone scans behind.
    if current_user.is_authenticated:
        return f"scan-user-{current_user.id}"
    return get_remote_address()


@scan_bp.route("/scan")
@login_required
def scanner():
    if current_user.role != "student":
        return redirect(url_for("main.dashboard"))
    device_uuid = request.cookies.get(DEVICE_COOKIE_NAME)
    registered = StudentDevice.find_by_uuid(current_user.id, device_uuid)
    active_count = StudentDevice.count_active(current_user.id)
    at_limit = not registered and active_count >= MAX_DEVICES
    return render_template("scan/scanner.html", active_tab="scan", at_limit=at_limit)


@scan_bp.route("/l/<token>")
def scan(token):
    lecturer = User.query.filter_by(qr_token=token, role="admin").first_or_404()
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.path))
    if current_user.role != "student":
        flash("This is your student check-in link. Students who open it sign in and mark attendance.", "success")
        return redirect(url_for("courses.index"))

    live_courses = live_courses_for_student(lecturer, current_user)

    chosen_id = parse_int(request.args.get("course"))
    if chosen_id is not None:
        chosen = next((course for course in live_courses if course.id == chosen_id), None)
        if chosen:
            return render_template("scan/mark.html", lecturer=lecturer, course=chosen, active_tab="scan")

    if not live_courses:
        return render_template("scan/mark.html", lecturer=lecturer, no_live=True, active_tab="scan")
    if len(live_courses) == 1:
        return render_template("scan/mark.html", lecturer=lecturer, course=live_courses[0], active_tab="scan")
    return render_template("scan/pick.html", lecturer=lecturer, courses=live_courses, active_tab="scan")


@scan_bp.route("/l/<token>/mark", methods=["POST"])
@login_required
@limiter.limit("12 per minute", key_func=scan_rate_key)
def mark(token):
    lecturer = User.query.filter_by(qr_token=token, role="admin").first_or_404()
    if current_user.role != "student":
        abort(403)

    course = Course.query.filter_by(
        id=parse_int(request.form.get("course_id")), lecturer_id=lecturer.id
    ).first_or_404()

    started = time.monotonic()
    result = record_scan(
        current_user,
        course,
        parse_coordinate(request.form.get("latitude")),
        parse_coordinate(request.form.get("longitude")),
        parse_coordinate(request.form.get("accuracy")),
        request.cookies.get(DEVICE_COOKIE_NAME),
    )
    current_app.logger.info(
        "scan course=%s student=%s status=%s ms=%.1f",
        course.id,
        current_user.id,
        result.status,
        (time.monotonic() - started) * 1000,
    )
    return render_template(
        "scan/result.html",
        course=course,
        result=result,
        marked_at=datetime.utcnow(),
        active_tab="scan",
    )
