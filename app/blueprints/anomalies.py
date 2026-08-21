from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload

from ..attendance import ANOMALY_SEVERITIES, ANOMALY_TYPES, anomalies_for_lecturer
from ..extensions import database
from ..models import Anomaly, ClassSession
from ..permissions import lecturer_required

anomalies_bp = Blueprint("anomalies", __name__, url_prefix="/anomalies")

PAGE_SIZE = 25


def apply_filters(query, status, severity, anomaly_type):
    if status == "unreviewed":
        query = query.filter(Anomaly.reviewed.is_(False))
    elif status == "reviewed":
        query = query.filter(Anomaly.reviewed.is_(True))
    if severity in ANOMALY_SEVERITIES:
        query = query.filter(Anomaly.severity == severity)
    if anomaly_type in ANOMALY_TYPES:
        query = query.filter(Anomaly.anomaly_type == anomaly_type)
    return query


@anomalies_bp.route("/")
@lecturer_required
def index():
    filters = {
        "status": request.args.get("status", "unreviewed"),
        "severity": request.args.get("severity", "all"),
        "type": request.args.get("type", "all"),
    }
    page = max(request.args.get("page", 1, type=int), 1)

    scoped = anomalies_for_lecturer(current_user.id)
    pagination = (
        apply_filters(scoped, filters["status"], filters["severity"], filters["type"])
        .options(
            joinedload(Anomaly.student),
            joinedload(Anomaly.reviewed_by),
            joinedload(Anomaly.session).joinedload(ClassSession.course),
        )
        .order_by(Anomaly.detected_at.desc())
        .paginate(page=page, per_page=PAGE_SIZE, error_out=False)
    )

    # Headline stats stay unfiltered so they always describe the whole log.
    stats = {
        "unreviewed": scoped.filter(Anomaly.reviewed.is_(False)).count(),
        "critical": scoped.filter(
            Anomaly.reviewed.is_(False), Anomaly.severity == "critical"
        ).count(),
        "last_day": scoped.filter(
            Anomaly.detected_at >= datetime.utcnow() - timedelta(hours=24)
        ).count(),
    }

    return render_template(
        "anomalies/list.html",
        anomalies=pagination.items,
        pagination=pagination,
        stats=stats,
        filters=filters,
        anomaly_types=ANOMALY_TYPES,
        severities=ANOMALY_SEVERITIES,
    )


@anomalies_bp.route("/<int:anomaly_id>/review", methods=["POST"])
@lecturer_required
def review(anomaly_id):
    anomaly = (
        anomalies_for_lecturer(current_user.id)
        .filter(Anomaly.id == anomaly_id)
        .first_or_404()
    )
    if not anomaly.reviewed:
        anomaly.reviewed = True
        anomaly.reviewed_by_id = current_user.id
        anomaly.reviewed_at = datetime.utcnow()
        note = request.form.get("note", "").strip()
        anomaly.reviewer_notes = note[:500] if note else None
        database.session.commit()
        flash("Anomaly marked as reviewed.", "success")

    return redirect(url_for(
        "anomalies.index",
        status=request.form.get("status", "unreviewed"),
        severity=request.form.get("severity", "all"),
        type=request.form.get("type", "all"),
        page=request.form.get("page", 1),
    ))
