from urllib.parse import urlsplit

from datetime import datetime

from flask import Blueprint, abort, current_app, flash, jsonify, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..attendance import live_sessions_for_student
from ..devices import DEVICE_COOKIE_NAME
from ..extensions import database
from ..models import Enrollment, MAX_DEVICES, StudentDevice
from ..stats import (
    attendance_summary,
    recent_activity,
    student_course_history,
    student_courses_with_history,
)
from ..utils import MINIMUM_PASSWORD_LENGTH

main_bp = Blueprint("main", __name__)


def clean_hint_text(value, max_length):
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed[:max_length] or None


def clean_hint_int(value, low, high):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def clean_hint_float(value, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def safe_referrer_or(default):
    referrer = request.referrer
    if referrer and urlsplit(referrer).netloc == urlsplit(request.host_url).netloc:
        return referrer
    return default

# Hero QR motif. 0 = empty module, 1 = structural module, 2 = a "live" scan-in module.
# The three corners stay solid so it reads as a real QR finder pattern.
HERO_QR_PATTERN = [
    [1, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1],
    [1, 0, 1, 0, 0, 1, 0, 0, 1, 0, 1],
    [1, 1, 1, 0, 1, 2, 0, 0, 1, 1, 1],
    [0, 0, 0, 0, 2, 0, 1, 0, 0, 0, 0],
    [1, 0, 1, 1, 0, 2, 1, 0, 1, 0, 1],
    [0, 1, 0, 1, 1, 0, 0, 2, 0, 1, 0],
    [1, 1, 0, 0, 2, 1, 0, 1, 1, 0, 1],
    [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
    [1, 1, 1, 0, 1, 0, 2, 1, 1, 0, 0],
    [1, 0, 1, 0, 0, 1, 0, 1, 0, 2, 0],
    [1, 1, 1, 0, 1, 1, 0, 0, 1, 0, 1],
]


@main_bp.route("/")
def index():
    return render_template("index.html", hero_grid=HERO_QR_PATTERN)


@main_bp.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "admin":
        return redirect(url_for("courses.index"))
    if not current_user.index_number:
        return redirect(url_for("auth.link_index"))
    return redirect(url_for("main.history"))


@main_bp.route("/history")
@login_required
def history():
    if current_user.role != "student":
        return redirect(url_for("main.dashboard"))
    if not current_user.index_number:
        return redirect(url_for("auth.link_index"))
    course_data = student_courses_with_history(current_user)
    totals = {
        "present": sum(s["present"] for _, s, _ in course_data),
        "absent": sum(s["absent"] for _, s, _ in course_data),
    }
    response = make_response(render_template(
        "student/history.html",
        course_data=course_data,
        totals=totals,
        recent=recent_activity(course_data),
        live_now=live_sessions_for_student(current_user),
        active_tab="history",
    ))
    # Never serve this page from a browser cache — a scan moments ago must show.
    response.headers["Cache-Control"] = "no-store"
    return response


@main_bp.route("/me/password", methods=["POST"])
@login_required
def change_password():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    error = None
    if not current_user.check_password(current_password):
        error = "Your current password is incorrect."
    elif len(new_password) < MINIMUM_PASSWORD_LENGTH:
        error = f"Use a new password of at least {MINIMUM_PASSWORD_LENGTH} characters."
    elif new_password != confirm_password:
        error = "The new passwords don't match."

    if error:
        flash(error, "error")
    else:
        current_user.set_password(new_password)
        database.session.commit()
        flash("Password updated.", "success")
    return redirect(safe_referrer_or(url_for("main.history")))


@main_bp.route("/me/courses/<int:course_id>")
@login_required
def my_course(course_id):
    if current_user.role != "student":
        return redirect(url_for("main.dashboard"))
    enrollment = Enrollment.query.filter_by(
        course_id=course_id, student_id=current_user.id
    ).first_or_404()
    return render_template(
        "dashboard/student_course.html",
        course=enrollment.course,
        summary=attendance_summary(course_id, current_user.id),
        history=student_course_history(course_id, current_user.id),
    )


@main_bp.route("/devices")
@login_required
def list_devices():
    if current_user.role != "student":
        abort(403)
    current_uuid = request.cookies.get(DEVICE_COOKIE_NAME)
    devices = StudentDevice.get_active(current_user.id)
    return jsonify({
        "devices": [
            {
                "id": device.id,
                "name": device.device_name or "Unknown device",
                "is_current": bool(current_uuid and device.device_uuid == current_uuid),
                "added": device.created_at.strftime("%-d %b %Y") if device.created_at else None,
            }
            for device in devices
        ],
        "count": len(devices),
        "max": MAX_DEVICES,
    })


@main_bp.route("/devices/info", methods=["POST"])
@login_required
def device_info():
    if current_user.role != "student":
        abort(403)
    device = StudentDevice.find_by_uuid(current_user.id, request.cookies.get(DEVICE_COOKIE_NAME))
    if not device:
        return jsonify({"stored": False})

    payload = request.get_json(silent=True) or {}
    device.device_model = clean_hint_text(payload.get("model"), 120) or device.device_model
    device.platform_version = clean_hint_text(payload.get("platformVersion"), 40) or device.platform_version
    device.screen = clean_hint_text(payload.get("screen"), 40) or device.screen
    device.timezone = clean_hint_text(payload.get("timezone"), 60) or device.timezone
    device.cpu_cores = clean_hint_int(payload.get("cpuCores"), 1, 256) or device.cpu_cores
    device.device_memory = clean_hint_float(payload.get("deviceMemory"), 0.25, 1024) or device.device_memory
    database.session.commit()
    return jsonify({"stored": True})


@main_bp.route("/devices/<int:device_id>/delete", methods=["POST"])
@login_required
def delete_device(device_id):
    if current_user.role != "student":
        abort(403)
    device = StudentDevice.query.filter_by(
        id=device_id, student_id=current_user.id, deleted_at=None
    ).first_or_404()

    was_current = request.cookies.get(DEVICE_COOKIE_NAME) == device.device_uuid

    device.deleted_at = datetime.utcnow()
    database.session.commit()

    resp = make_response(jsonify({
        "success": True,
        "was_current": was_current,
        "remaining": StudentDevice.count_active(current_user.id),
    }))
    if was_current:
        resp.delete_cookie(
            DEVICE_COOKIE_NAME, samesite="Lax", secure=current_app.config["SESSION_COOKIE_SECURE"]
        )
    return resp


@main_bp.route("/health")
def health():
    return {"status": "ok"}
