import secrets
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import database

MAX_DEVICES = 2


class User(UserMixin, database.Model):
    __tablename__ = "users"

    id = database.Column(database.Integer, primary_key=True)
    email = database.Column(database.String(255), unique=True, nullable=False, index=True)
    password_hash = database.Column(database.String(255))
    google_id = database.Column(database.String(255), unique=True)
    full_name = database.Column(database.String(255))
    role = database.Column(database.String(20), nullable=False, default="student")

    # Populated on a student's first sign-in to link them to course rosters.
    index_number = database.Column(database.String(50), unique=True)
    # A lecturer's single personal QR value; students scan it to reach the live class.
    qr_token = database.Column(database.String(64), unique=True)
    # Ties a student account to the one phone it registered on (device lock).
    device_id = database.Column(database.String(255))

    created_at = database.Column(database.DateTime, default=datetime.utcnow, nullable=False)

    taught_courses = database.relationship("Course", back_populates="lecturer")
    attendance_records = database.relationship(
        "AttendanceRecord", back_populates="student", foreign_keys="AttendanceRecord.student_id"
    )
    student_devices = database.relationship("StudentDevice", back_populates="student", cascade="all, delete-orphan")

    def set_password(self, plain_password):
        self.password_hash = generate_password_hash(plain_password)

    def check_password(self, plain_password):
        return bool(self.password_hash) and check_password_hash(self.password_hash, plain_password)

    @property
    def is_admin(self):
        return self.role == "admin"

    def ensure_qr_token(self):
        # Lecturers get a personal QR token the first time one is needed.
        if not self.qr_token:
            while True:
                token = secrets.token_urlsafe(9)
                if not User.query.filter_by(qr_token=token).first():
                    self.qr_token = token
                    break
        return self.qr_token


class Course(database.Model):
    __tablename__ = "courses"

    id = database.Column(database.Integer, primary_key=True)
    code = database.Column(database.String(50), nullable=False)
    title = database.Column(database.String(255), nullable=False)
    lecturer_id = database.Column(database.Integer, database.ForeignKey("users.id"), nullable=False)
    created_at = database.Column(database.DateTime, default=datetime.utcnow, nullable=False)
    # The room location from the most recent session, GPS or map-picked, so the
    # next session start can offer "use last room location" instead of re-picking.
    last_location_latitude = database.Column(database.Float)
    last_location_longitude = database.Column(database.Float)
    last_location_accuracy = database.Column(database.Float)
    # Sticky per course: flips off on a "start without a location" submit, flips
    # back on the moment the lecturer picks or reuses a location.
    requires_location = database.Column(database.Boolean, default=True, nullable=False)

    lecturer = database.relationship("User", back_populates="taught_courses")
    enrollments = database.relationship(
        "Enrollment", back_populates="course", cascade="all, delete-orphan"
    )
    sessions = database.relationship(
        "ClassSession", back_populates="course", cascade="all, delete-orphan"
    )
    schedule_slots = database.relationship(
        "ClassScheduleSlot",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="ClassScheduleSlot.day_of_week, ClassScheduleSlot.start_time",
    )


class ClassScheduleSlot(database.Model):
    __tablename__ = "class_schedule_slots"

    id = database.Column(database.Integer, primary_key=True)
    course_id = database.Column(database.Integer, database.ForeignKey("courses.id"), nullable=False)
    # 0 = Monday .. 6 = Sunday, matching Python's date.weekday().
    day_of_week = database.Column(database.Integer, nullable=False)
    start_time = database.Column(database.Time, nullable=False)
    created_at = database.Column(database.DateTime, default=datetime.utcnow, nullable=False)

    course = database.relationship("Course", back_populates="schedule_slots")


class Enrollment(database.Model):
    __tablename__ = "enrollments"

    id = database.Column(database.Integer, primary_key=True)
    course_id = database.Column(database.Integer, database.ForeignKey("courses.id"), nullable=False)
    index_number = database.Column(database.String(50), nullable=False)
    full_name = database.Column(database.String(255))
    # Filled once the matching student signs in and links their index number.
    student_id = database.Column(database.Integer, database.ForeignKey("users.id"))

    course = database.relationship("Course", back_populates="enrollments")
    student = database.relationship("User")

    __table_args__ = (database.UniqueConstraint("course_id", "index_number"),)


class ClassSession(database.Model):
    __tablename__ = "class_sessions"

    id = database.Column(database.Integer, primary_key=True)
    course_id = database.Column(database.Integer, database.ForeignKey("courses.id"), nullable=False)
    started_at = database.Column(database.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = database.Column(database.DateTime)
    latitude = database.Column(database.Float)
    longitude = database.Column(database.Float)
    location_accuracy = database.Column(database.Float)
    # A discarded session is kept for audit but excluded from every attendance count.
    voided = database.Column(database.Boolean, default=False, nullable=False)

    course = database.relationship("Course", back_populates="sessions")
    records = database.relationship(
        "AttendanceRecord", back_populates="session", cascade="all, delete-orphan"
    )
    anomalies = database.relationship(
        "Anomaly", back_populates="session", cascade="all, delete-orphan"
    )

    # At most one live (un-ended, un-voided) session per course, enforced by the
    # database so two near-simultaneous Start taps can't both open a session.
    __table_args__ = (
        database.Index(
            "uq_one_live_session_per_course",
            "course_id",
            unique=True,
            postgresql_where=database.text("ended_at IS NULL AND NOT voided"),
            sqlite_where=database.text("ended_at IS NULL AND NOT voided"),
        ),
    )

    @property
    def is_live(self):
        return self.ended_at is None


class AttendanceRecord(database.Model):
    __tablename__ = "attendance_records"

    id = database.Column(database.Integer, primary_key=True)
    session_id = database.Column(
        database.Integer, database.ForeignKey("class_sessions.id"), nullable=False
    )
    student_id = database.Column(database.Integer, database.ForeignKey("users.id"), nullable=False)
    status = database.Column(database.String(20), nullable=False, default="present")
    scanned_at = database.Column(database.DateTime)
    latitude = database.Column(database.Float)
    longitude = database.Column(database.Float)
    device_id = database.Column(database.String(255))

    # Set only when a lecturer manually marks an absent student present by
    # hand (e.g. a dead phone or failed GPS fix); a real scan leaves these null.
    override_reason = database.Column(database.String(255))
    overridden_by_id = database.Column(database.Integer, database.ForeignKey("users.id"))
    overridden_at = database.Column(database.DateTime)

    session = database.relationship("ClassSession", back_populates="records")
    student = database.relationship("User", back_populates="attendance_records", foreign_keys=[student_id])
    overridden_by = database.relationship("User", foreign_keys=[overridden_by_id])

    # A student can be marked at most once per class session.
    __table_args__ = (database.UniqueConstraint("session_id", "student_id"),)


class Anomaly(database.Model):
    __tablename__ = "anomalies"

    id = database.Column(database.Integer, primary_key=True)
    # Optional: device events logged at sign-in have no session context.
    session_id = database.Column(
        database.Integer, database.ForeignKey("class_sessions.id"), nullable=True
    )
    student_id = database.Column(database.Integer, database.ForeignKey("users.id"), nullable=False)
    anomaly_type = database.Column(database.String(60), nullable=False, index=True)
    severity = database.Column(database.String(10), nullable=False, default="info")
    reason = database.Column(database.String(255), nullable=False)
    device_id = database.Column(database.String(255))
    ip_address = database.Column(database.String(45))
    # Detector-specific facts, e.g. geofence distances or the other account on a shared device.
    details = database.Column(database.JSON)
    detected_at = database.Column(database.DateTime, default=datetime.utcnow, nullable=False)

    reviewed = database.Column(database.Boolean, nullable=False, default=False)
    reviewed_by_id = database.Column(database.Integer, database.ForeignKey("users.id"))
    reviewed_at = database.Column(database.DateTime)
    reviewer_notes = database.Column(database.String(500))

    session = database.relationship("ClassSession", back_populates="anomalies")
    student = database.relationship("User", foreign_keys=[student_id])
    reviewed_by = database.relationship("User", foreign_keys=[reviewed_by_id])

    __table_args__ = (
        database.Index("ix_anomalies_reviewed_detected", "reviewed", "detected_at"),
        database.Index("ix_anomalies_student_detected", "student_id", "detected_at"),
    )


class StudentDevice(database.Model):
    __tablename__ = "student_devices"

    id = database.Column(database.Integer, primary_key=True)
    student_id = database.Column(
        database.Integer,
        database.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_uuid = database.Column(database.String(64), unique=True, nullable=False)
    device_name = database.Column(database.String(120))
    user_agent = database.Column(database.String(300))
    first_seen_ip = database.Column(database.String(45))
    last_seen_ip = database.Column(database.String(45))
    last_seen_at = database.Column(database.DateTime)
    created_at = database.Column(database.DateTime, default=datetime.utcnow, nullable=False)
    deleted_at = database.Column(database.DateTime, index=True)

    # Client-reported hints, captured by JS after sign-in to help identify the phone.
    device_model = database.Column(database.String(120))
    platform_version = database.Column(database.String(40))
    screen = database.Column(database.String(40))
    cpu_cores = database.Column(database.Integer)
    device_memory = database.Column(database.Float)
    timezone = database.Column(database.String(60))

    student = database.relationship("User", back_populates="student_devices")

    @staticmethod
    def get_active(student_id):
        return (
            StudentDevice.query.filter_by(student_id=student_id, deleted_at=None)
            .order_by(StudentDevice.created_at.asc())
            .all()
        )

    @staticmethod
    def count_active(student_id):
        return StudentDevice.query.filter_by(student_id=student_id, deleted_at=None).count()

    @staticmethod
    def find_by_uuid(student_id, device_uuid):
        if not device_uuid:
            return None
        return StudentDevice.query.filter_by(
            student_id=student_id, device_uuid=device_uuid, deleted_at=None
        ).first()
