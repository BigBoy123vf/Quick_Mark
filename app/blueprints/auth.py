import secrets
from datetime import datetime

from authlib.integrations.base_client import OAuthError
from sqlalchemy.exc import IntegrityError
from flask import (
    Blueprint,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from ..attendance import log_anomaly
from ..devices import (
    DEVICE_COOKIE_MAX_AGE,
    DEVICE_COOKIE_NAME,
    device_label,
    generate_device_token,
    hash_device_token,
)
from ..extensions import database, limiter, oauth
from ..models import MAX_DEVICES, Enrollment, StudentDevice, User
from ..utils import MINIMUM_PASSWORD_LENGTH

auth_bp = Blueprint("auth", __name__)


def is_safe_next_url(target):
    return bool(target) and target.startswith("/") and not target.startswith("//")


def destination_after_login(user, next_url=None):
    # Linking the index number always comes first for a fresh student account.
    if user.role == "student" and not user.index_number:
        return url_for("auth.link_index")
    if next_url is None:
        next_url = request.values.get("next")
    if is_safe_next_url(next_url):
        return next_url
    return url_for("main.dashboard")


def apply_student_device_lock(user, response):
    incoming_uuid = request.cookies.get(DEVICE_COOKIE_NAME)
    ip = request.remote_addr or ""
    user_agent_string = request.user_agent.string or ""

    # Known device — just refresh activity timestamps
    if incoming_uuid:
        existing = StudentDevice.find_by_uuid(user.id, incoming_uuid)
        if existing:
            existing.last_seen_at = datetime.utcnow()
            existing.last_seen_ip = ip
            database.session.commit()
            return

    # Migration path: old single hash-based device_id on the user row
    if user.device_id and incoming_uuid and hash_device_token(incoming_uuid) == user.device_id:
        database.session.add(StudentDevice(
            student_id=user.id,
            device_uuid=incoming_uuid,
            device_name=device_label(user_agent_string),
            user_agent=user_agent_string[:300],
            first_seen_ip=ip,
            last_seen_ip=ip,
            last_seen_at=datetime.utcnow(),
        ))
        user.device_id = None
        database.session.commit()
        return

    # New device — assign a UUID. A cookie UUID already registered (to another
    # student, or as a removed device) can't be reused, so mint a fresh one.
    new_uuid = incoming_uuid or generate_device_token()
    if incoming_uuid:
        conflicting = StudentDevice.query.filter_by(device_uuid=incoming_uuid).first()
        if conflicting:
            new_uuid = generate_device_token()
            if conflicting.student_id != user.id and conflicting.deleted_at is None:
                log_anomaly(
                    "shared_device",
                    "warn",
                    user,
                    device_hash=hash_device_token(incoming_uuid),
                    details={
                        "device": device_label(user_agent_string),
                        "shared_with": conflicting.student.full_name,
                        "shared_with_index": conflicting.student.index_number,
                    },
                )
    response.set_cookie(
        DEVICE_COOKIE_NAME,
        new_uuid,
        max_age=DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=current_app.config["SESSION_COOKIE_SECURE"],
    )

    active_count = StudentDevice.count_active(user.id)
    if active_count < MAX_DEVICES:
        database.session.add(StudentDevice(
            student_id=user.id,
            device_uuid=new_uuid,
            device_name=device_label(user_agent_string),
            user_agent=user_agent_string[:300],
            first_seen_ip=ip,
            last_seen_ip=ip,
            last_seen_at=datetime.utcnow(),
        ))
        database.session.commit()
        # An additional phone on the account is worth a note in the audit log.
        if active_count >= 1:
            log_anomaly(
                "new_device",
                "info",
                user,
                device_hash=hash_device_token(new_uuid),
                details={"device": device_label(user_agent_string)},
            )
    # else: at limit — cookie is set so the device is tracked, but it isn't registered.
    # The scan route will block scanning until the student removes an old device.


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    selected_role = request.values.get("role", "student")

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "student")
        staff_code = request.form.get("staff_code", "").strip()

        error = None
        if not full_name:
            error = "Enter your full name."
        elif "@" not in email:
            error = "Enter a valid email address."
        elif len(password) < MINIMUM_PASSWORD_LENGTH:
            error = f"Use a password of at least {MINIMUM_PASSWORD_LENGTH} characters."
        elif role not in ("student", "admin"):
            error = "Choose whether you're a student or a lecturer."
        elif role == "admin" and not staff_code_is_valid(staff_code):
            error = "That staff code isn't right."
        elif User.query.filter_by(email=email).first():
            error = "An account with that email already exists."

        if error:
            flash(error, "error")
            return render_template("auth/register.html", selected_role=role, full_name=full_name, email=email)

        user = User(full_name=full_name, email=email, role=role)
        user.set_password(password)
        database.session.add(user)
        database.session.commit()

        login_user(user)
        response = make_response(redirect(destination_after_login(user)))
        if user.role == "student":
            apply_student_device_lock(user, response)
        return response

    return render_template("auth/register.html", selected_role=selected_role)


def staff_code_is_valid(submitted_code):
    # A shared staff code gates lecturer sign-up. Empty/unset = open (local dev).
    required_code = current_app.config.get("STAFF_SIGNUP_CODE", "")
    return not required_code or secrets.compare_digest(submitted_code, required_code)


def login_attempt_key():
    # Throttle per IP + email so one guessed-at account can't lock out a whole
    # campus network sharing an IP address.
    email = request.form.get("email", "").strip().lower()
    return f"{request.remote_addr}:{email}"


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit(
    "10 per minute",
    methods=["POST"],
    key_func=login_attempt_key,
    # A failed login re-renders the form (200); a success redirects (302).
    deduct_when=lambda response: response.status_code == 200,
)
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        next_url = request.values.get("next")
        if not user or not user.check_password(password):
            flash("Email or password is incorrect.", "error")
            return render_template("auth/login.html", email=email, next_url=next_url)

        login_user(user)
        response = make_response(redirect(destination_after_login(user)))
        if user.role == "student":
            apply_student_device_lock(user, response)
        return response

    return render_template("auth/login.html", next_url=request.args.get("next"))


@auth_bp.route("/link-index", methods=["GET", "POST"])
@login_required
def link_index():
    if current_user.role != "student":
        return redirect(url_for("main.dashboard"))
    if current_user.index_number:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        index_number = request.form.get("index_number", "").strip().upper()

        error = None
        if not index_number:
            error = "Enter your index number."
        elif User.query.filter_by(index_number=index_number).first():
            error = "That index number is already linked to another account."

        if error:
            flash(error, "error")
            return render_template("auth/link_index.html", index_number=index_number)

        matches = Enrollment.query.filter_by(index_number=index_number).all()
        matches.sort(key=lambda enrollment: enrollment.course.code)

        # First submit shows what the index matched so a typo gets caught here,
        # not weeks later as an empty history.
        if request.form.get("confirmed") != "yes":
            return render_template(
                "auth/link_index.html",
                index_number=index_number,
                confirming=True,
                matches=matches,
            )

        current_user.index_number = index_number
        Enrollment.query.filter_by(index_number=index_number).update(
            {"student_id": current_user.id}
        )
        try:
            database.session.commit()
        except IntegrityError:
            # Another account confirmed the same index in the same instant.
            database.session.rollback()
            flash("That index number is already linked to another account.", "error")
            return render_template("auth/link_index.html", index_number=index_number)
        flash("Your index number is linked.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("auth/link_index.html")


@auth_bp.route("/google/login")
def google_login():
    session["google_intent"] = "login"
    session["google_next"] = request.args.get("next", "")
    redirect_uri = url_for("auth.google_callback", _external=True)
    # select_account makes Google show its account chooser instead of
    # silently reusing whichever Gmail is already signed in.
    return oauth.google.authorize_redirect(redirect_uri, prompt="select_account")


@auth_bp.route("/google/register", methods=["POST"])
def google_register():
    # Same gate as the email path: lecturer sign-up needs the staff code.
    role = request.form.get("role", "student")
    if role != "admin":
        role = "student"
    elif not staff_code_is_valid(request.form.get("staff_code", "").strip()):
        flash("That staff code isn't right.", "error")
        return redirect(url_for("auth.register", role="admin"))

    session["google_intent"] = "register"
    session["google_role"] = role
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri, prompt="select_account")


@auth_bp.route("/google/callback")
def google_callback():
    # Raised when the user cancels the Google prompt or the state is stale.
    try:
        token = oauth.google.authorize_access_token()
    except OAuthError:
        flash("Google sign-in was cancelled. Try again.", "error")
        return redirect(url_for("auth.login"))
    user_info = token.get("userinfo")
    if not user_info:
        flash("Google sign-in failed. Try again.", "error")
        return redirect(url_for("auth.login"))

    google_id = user_info["sub"]
    email = user_info["email"].lower()
    full_name = user_info.get("name", "")

    intent = session.pop("google_intent", "login")
    next_url = session.pop("google_next", "")
    role = session.pop("google_role", "student")

    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.google_id = google_id
            database.session.commit()

    if user:
        login_user(user)
        response = make_response(redirect(destination_after_login(user, next_url)))
        if user.role == "student":
            apply_student_device_lock(user, response)
        return response

    if intent == "register":
        new_user = User(full_name=full_name, email=email, role=role, google_id=google_id)
        database.session.add(new_user)
        database.session.commit()
        login_user(new_user)
        response = make_response(redirect(destination_after_login(new_user)))
        if new_user.role == "student":
            apply_student_device_lock(new_user, response)
        return response

    flash("No account found for that Google address. Create one below.", "error")
    return redirect(url_for("auth.register"))


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You're signed out.", "success")
    return redirect(url_for("main.index"))
