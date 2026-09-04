import csv
import io
from datetime import datetime

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..attendance import anomaly_student_ids, apply_manual_override, get_live_session, mark_absentees, revert_manual_override
from ..extensions import database
from ..models import AttendanceRecord, ClassScheduleSlot, ClassSession, Course, Enrollment, User
from ..permissions import lecturer_required
from ..qr import build_qr_svg
from ..schedule import parse_schedule_rows
from ..utils import parse_coordinate
from ..stats import (
    course_attendance_matrix,
    course_roster_stats,
    course_sessions_overview,
    courses_overview,
    roster_names_for_course,
    session_breakdown,
)

courses_bp = Blueprint("courses", __name__, url_prefix="/courses")

ROSTER_HEADER_VALUES = {"index", "indexnumber", "indexno"}


def lecturer_scan_url():
    current_user.ensure_qr_token()
    database.session.commit()
    return request.host_url.rstrip("/") + url_for("scan.scan", token=current_user.qr_token)


def get_owned_course_or_404(course_id):
    course = Course.query.get_or_404(course_id)
    if course.lecturer_id != current_user.id:
        abort(403)
    return course


def csv_download_response(content, filename):
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def read_roster_input():
    text = request.form.get("roster_text", "").lstrip("\ufeff")
    upload = request.files.get("roster_file")
    if upload and upload.filename:
        # utf-8-sig strips the BOM Excel puts at the start of its CSV exports,
        # which would otherwise corrupt the first index number.
        text = text + "\n" + upload.read().decode("utf-8-sig", errors="ignore")
    return text


def parse_roster_rows(text):
    rows = []
    for fields in csv.reader(io.StringIO(text)):
        if not fields:
            continue
        index_number = fields[0].strip().upper()
        if not index_number or index_number.lower().replace(" ", "") in ROSTER_HEADER_VALUES:
            continue
        full_name = fields[1].strip() if len(fields) > 1 and fields[1].strip() else None
        rows.append((index_number, full_name))
    return rows


def apply_roster(course, text):
    added = 0
    skipped = 0
    for index_number, full_name in parse_roster_rows(text):
        existing = Enrollment.query.filter_by(
            course_id=course.id, index_number=index_number
        ).first()
        if existing:
            # Re-uploads carry name corrections; a row without a name changes nothing.
            if full_name and existing.full_name != full_name:
                existing.full_name = full_name
            skipped += 1
            continue
        student = User.query.filter_by(index_number=index_number).first()
        database.session.add(
            Enrollment(
                course_id=course.id,
                index_number=index_number,
                full_name=full_name,
                student_id=student.id if student else None,
            )
        )
        added += 1
    database.session.commit()
    return added, skipped


@courses_bp.route("/")
@lecturer_required
def index():
    overview = courses_overview(current_user.id)
    return render_template(
        "courses/list.html",
        overview=overview,
        live_count=sum(1 for row in overview if row["live"]),
        enrolled_total=sum(row["enrolled"] for row in overview),
    )


@courses_bp.route("/new", methods=["GET", "POST"])
@lecturer_required
def new():
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        title = request.form.get("title", "").strip()

        error = None
        if not code:
            error = "Enter a course code."
        elif not title:
            error = "Enter a course title."
        elif Course.query.filter_by(lecturer_id=current_user.id, code=code).first():
            error = "You already have a course with that code."

        if error:
            flash(error, "error")
            return render_template("courses/new.html", code=code, title=title)

        course = Course(
            code=code,
            title=title,
            lecturer_id=current_user.id,
        )
        database.session.add(course)
        database.session.flush()
        for day_of_week, start_time in parse_schedule_rows(
            request.form.getlist("schedule_day"), request.form.getlist("schedule_time")
        ):
            database.session.add(
                ClassScheduleSlot(course_id=course.id, day_of_week=day_of_week, start_time=start_time)
            )
        database.session.commit()
        flash("Course created.", "success")
        return redirect(url_for("courses.detail", course_id=course.id))

    return render_template("courses/new.html")


@courses_bp.route("/<int:course_id>")
@lecturer_required
def detail(course_id):
    course = get_owned_course_or_404(course_id)
    enrollments, summaries = course_roster_stats(course)
    return render_template(
        "courses/detail.html",
        course=course,
        enrollments=enrollments,
        summaries=summaries,
        sessions=course_sessions_overview(course),
        live_session=get_live_session(course),
        qr_svg=build_qr_svg(lecturer_scan_url()),
    )


@courses_bp.route("/qr")
@lecturer_required
def my_qr():
    scan_url = lecturer_scan_url()
    return render_template(
        "courses/my_qr.html",
        scan_url=scan_url,
        qr_svg=build_qr_svg(scan_url),
    )


@courses_bp.route("/<int:course_id>/sessions/<int:session_id>")
@lecturer_required
def session_detail(course_id, session_id):
    course = get_owned_course_or_404(course_id)
    session = ClassSession.query.filter_by(id=session_id, course_id=course.id).first_or_404()
    present, absent = session_breakdown(session)
    return render_template(
        "courses/session.html",
        course=course,
        session=session,
        present=present,
        absent=absent,
        roster_names=roster_names_for_course(course.id),
        students_with_anomalies=anomaly_student_ids(session.id),
    )


@courses_bp.route("/<int:course_id>/export")
@lecturer_required
def export_course(course_id):
    course = get_owned_course_or_404(course_id)
    sessions, rows = course_attendance_matrix(course)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    session_headers = [session.started_at.strftime("%Y-%m-%d %H:%M") for session in sessions]
    writer.writerow(["Index number", "Name", *session_headers, "Present", "Total", "Attendance %"])
    for row in rows:
        percentage = "" if row["percentage"] is None else row["percentage"]
        writer.writerow(
            [row["index_number"], row["name"] or "", *row["cells"], row["present"], row["total"], percentage]
        )

    return csv_download_response(buffer.getvalue(), f"{course.code}_attendance.csv")


@courses_bp.route("/<int:course_id>/sessions/<int:session_id>/export")
@lecturer_required
def export_session(course_id, session_id):
    course = get_owned_course_or_404(course_id)
    session = ClassSession.query.filter_by(id=session_id, course_id=course.id).first_or_404()
    present, absent = session_breakdown(session)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    students_with_anomalies = anomaly_student_ids(session.id)
    roster_names = roster_names_for_course(course.id)
    writer.writerow(["Index number", "Name", "Status", "Scanned at (UTC)", "Anomaly", "Override reason"])
    for record in present:
        anomaly = "Yes" if record.student_id in students_with_anomalies else ""
        scanned_at = record.scanned_at.strftime("%Y-%m-%d %H:%M") if record.scanned_at else ""
        display_name = roster_names.get(record.student_id) or record.student.full_name
        writer.writerow([record.student.index_number, display_name, "Present", scanned_at, anomaly, record.override_reason or ""])
    for record in absent:
        display_name = roster_names.get(record.student_id) or record.student.full_name
        writer.writerow([record.student.index_number, display_name, "Absent", "", "", ""])

    filename = f"{course.code}_{session.started_at.strftime('%Y%m%d_%H%M')}.csv"
    return csv_download_response(buffer.getvalue(), filename)


@courses_bp.route("/<int:course_id>/sessions/start", methods=["POST"])
@lecturer_required
def start_session(course_id):
    course = get_owned_course_or_404(course_id)

    if get_live_session(course):
        flash("A session is already live for this course.", "warning")
        return redirect(url_for("courses.detail", course_id=course.id))

    no_location = request.form.get("no_location") == "1"
    if no_location:
        session = ClassSession(course_id=course.id)
        course.requires_location = False
        # last_location_* stays untouched, so re-enabling later can offer it back.
    else:
        latitude = parse_coordinate(request.form.get("latitude"))
        longitude = parse_coordinate(request.form.get("longitude"))
        accuracy = parse_coordinate(request.form.get("accuracy"))

        if latitude is None or longitude is None:
            flash("Couldn't read the room location. Pick a spot on the map and try again.", "error")
            return redirect(url_for("courses.detail", course_id=course.id))

        session = ClassSession(
            course_id=course.id,
            latitude=latitude,
            longitude=longitude,
            location_accuracy=accuracy,
        )
        course.requires_location = True
        # Remember this spot so the next session start can offer it as a one-tap default.
        course.last_location_latitude = latitude
        course.last_location_longitude = longitude
        course.last_location_accuracy = accuracy

    database.session.add(session)
    try:
        database.session.commit()
    except IntegrityError:
        # A second Start tap raced this one; the first session won.
        database.session.rollback()
        flash("A session is already live for this course.", "warning")
        return redirect(url_for("courses.detail", course_id=course.id))
    flash("Session started — students can scan now.", "success")
    return redirect(url_for("courses.detail", course_id=course.id))


@courses_bp.route("/<int:course_id>/sessions/<int:session_id>/end", methods=["POST"])
@lecturer_required
def end_session(course_id, session_id):
    course = get_owned_course_or_404(course_id)
    session = ClassSession.query.filter_by(id=session_id, course_id=course.id).first_or_404()

    if session.is_live:
        session.ended_at = datetime.utcnow()
        database.session.commit()
        mark_absentees(session)
        flash("Session ended. Enrolled students who didn't scan are marked absent.", "success")
    return redirect(url_for("courses.detail", course_id=course.id))


@courses_bp.route("/<int:course_id>/sessions/<int:session_id>/discard", methods=["POST"])
@lecturer_required
def discard_session(course_id, session_id):
    course = get_owned_course_or_404(course_id)
    session = ClassSession.query.filter_by(id=session_id, course_id=course.id).first_or_404()

    present_count = AttendanceRecord.query.filter_by(
        session_id=session.id, status="present"
    ).count()

    if present_count == 0:
        database.session.delete(session)
        database.session.commit()
        flash("Session discarded — it never counted, so it's been removed.", "success")
    else:
        if session.is_live:
            session.ended_at = datetime.utcnow()
        session.voided = True
        database.session.commit()
        flash("Session voided — it no longer counts toward attendance but is kept for your records.", "success")
    return redirect(url_for("courses.detail", course_id=course.id))


@courses_bp.route("/<int:course_id>/sessions/<int:session_id>/records/<int:record_id>/override", methods=["POST"])
@lecturer_required
def override_attendance(course_id, session_id, record_id):
    course = get_owned_course_or_404(course_id)
    session = ClassSession.query.filter_by(id=session_id, course_id=course.id).first_or_404()
    record = AttendanceRecord.query.filter_by(id=record_id, session_id=session.id).first_or_404()

    result = apply_manual_override(record, session, current_user, request.form.get("reason"))
    flash(result.message, "success" if result.ok else "error")
    return redirect(url_for("courses.session_detail", course_id=course.id, session_id=session.id))


@courses_bp.route("/<int:course_id>/sessions/<int:session_id>/records/<int:record_id>/revert-override", methods=["POST"])
@lecturer_required
def revert_attendance_override(course_id, session_id, record_id):
    course = get_owned_course_or_404(course_id)
    session = ClassSession.query.filter_by(id=session_id, course_id=course.id).first_or_404()
    record = AttendanceRecord.query.filter_by(id=record_id, session_id=session.id).first_or_404()

    result = revert_manual_override(record)
    flash(result.message, "success" if result.ok else "error")
    return redirect(url_for("courses.session_detail", course_id=course.id, session_id=session.id))


@courses_bp.route("/<int:course_id>/enrollments/<int:enrollment_id>/unlink", methods=["POST"])
@lecturer_required
def unlink_enrollment(course_id, enrollment_id):
    course = get_owned_course_or_404(course_id)
    enrollment = Enrollment.query.filter_by(id=enrollment_id, course_id=course.id).first_or_404()
    student = enrollment.student

    if not student:
        flash("That roster entry isn't linked to an account.", "warning")
        return redirect(url_for("courses.detail", course_id=course.id))

    # The index links the whole account, so detach every roster entry it matched.
    # Attendance records are kept: they count again if the right student re-links.
    Enrollment.query.filter_by(
        student_id=student.id, index_number=enrollment.index_number
    ).update({"student_id": None})
    student.index_number = None
    database.session.commit()

    flash(
        f"{enrollment.index_number} is unlinked from {student.full_name}'s account. "
        "The right student can now link it from their own account.",
        "success",
    )
    return redirect(url_for("courses.detail", course_id=course.id))


@courses_bp.route("/<int:course_id>/enrollments/<int:enrollment_id>/remove", methods=["POST"])
@lecturer_required
def remove_enrollment(course_id, enrollment_id):
    course = get_owned_course_or_404(course_id)
    enrollment = Enrollment.query.filter_by(id=enrollment_id, course_id=course.id).first_or_404()
    index_number = enrollment.index_number

    # Off the roster means out of this course's records too, otherwise the
    # session lists keep showing phantom absences for someone not in the class.
    if enrollment.student_id:
        course_session_ids = select(ClassSession.id).where(ClassSession.course_id == course.id)
        AttendanceRecord.query.filter(
            AttendanceRecord.student_id == enrollment.student_id,
            AttendanceRecord.session_id.in_(course_session_ids),
        ).delete(synchronize_session=False)

    database.session.delete(enrollment)
    database.session.commit()
    flash(f"{index_number} removed from the roster.", "success")
    return redirect(url_for("courses.detail", course_id=course.id))


@courses_bp.route("/<int:course_id>/schedule", methods=["POST"])
@lecturer_required
def add_schedule_slot(course_id):
    course = get_owned_course_or_404(course_id)
    rows = parse_schedule_rows([request.form.get("day_of_week")], [request.form.get("start_time")])
    if not rows:
        flash("Pick a day and a time for the class slot.", "error")
        return redirect(url_for("courses.detail", course_id=course.id))

    day_of_week, start_time = rows[0]
    database.session.add(
        ClassScheduleSlot(course_id=course.id, day_of_week=day_of_week, start_time=start_time)
    )
    database.session.commit()
    flash("Class time added.", "success")
    return redirect(url_for("courses.detail", course_id=course.id))


@courses_bp.route("/<int:course_id>/schedule/<int:slot_id>/delete", methods=["POST"])
@lecturer_required
def delete_schedule_slot(course_id, slot_id):
    course = get_owned_course_or_404(course_id)
    slot = ClassScheduleSlot.query.filter_by(id=slot_id, course_id=course.id).first_or_404()
    database.session.delete(slot)
    database.session.commit()
    flash("Class time removed.", "success")
    return redirect(url_for("courses.detail", course_id=course.id))


@courses_bp.route("/<int:course_id>/roster", methods=["POST"])
@lecturer_required
def upload_roster(course_id):
    course = get_owned_course_or_404(course_id)
    added, skipped = apply_roster(course, read_roster_input())
    flash(f"Roster updated — {added} added, {skipped} already on the list.", "success")
    return redirect(url_for("courses.detail", course_id=course.id))


@courses_bp.route("/<int:course_id>/delete", methods=["POST"])
@lecturer_required
def delete_course(course_id):
    course = get_owned_course_or_404(course_id)

    if get_live_session(course):
        flash("End or discard the live session before deleting this course.", "error")
        return redirect(url_for("courses.detail", course_id=course.id))

    code = course.code
    database.session.delete(course)
    database.session.commit()
    flash(f"{code} deleted, along with its roster and attendance history.", "success")
    return redirect(url_for("courses.index"))
