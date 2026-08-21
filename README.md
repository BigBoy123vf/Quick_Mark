# QuickMark — QR Attendance System

A Progressive Web App that records student attendance per class session using a fixed QR code. Students scan with their phone browser — no app install, no roll call, no paper sheets.

---

## How It Works

Every attendance mark is tied to a **specific class session** (one meeting of one course), never just to the day. A student in a 9am course and a 2pm course on the same day is tracked separately for each.

1. **Lecturer starts a session.** Opening the session captures the room's GPS location and opens the scan window.
2. **The QR code goes up.** Each lecturer has one fixed QR code (projected or printed) — it never changes, so there's nothing to reprint each week.
3. **Students scan.** A scan is accepted only if the student is signed in, physically in the room, on their registered phone, and the class is live. They see "Present" and are done.
4. **Lecturer ends the session.** Everyone enrolled who didn't scan is automatically marked absent for that class.

Because the QR code is fixed, the **start/end step is what gives a scan meaning**: it decides which class the scan counts for, where the room is, and when scanning is allowed.

## Preventing Attendance Fraud

Four checks work together so no single weak point can be exploited:

| Check | What it stops |
|---|---|
| **Device lock** — each student account is tied to the phone it first registered on; a new phone is flagged for review, not auto-trusted | Account sharing |
| **Location check** — the scan must come from inside the classroom radius, and scans with GPS accuracy too poor to trust are rejected | Scanning from a dorm or off campus |
| **Live time window** — the code only accepts scans while the session is live, within a configurable window (default 2 hours) | Photographing the code and scanning later |
| **One-device-many-accounts alert** — the same phone marking attendance for several students is flagged | Scanning in for absent friends |

**Flags are reviewed by a person, never auto-blocked** — a student with a genuinely lost phone isn't unfairly locked out. Every suspicious event lands in a structured anomaly log (type, severity, device, IP) with a mark-as-reviewed workflow for the lecturer.

## Roles & Features

### Student
- Sign in with Google or email + password; on first login, enter your index number once to link the account to the class roster.
- See enrolled courses with attendance percentage for each.
- Scan the class QR code to be marked present.
- Full attendance history — every class attended and missed, per course.
- Dismissible "next class" widget showing the next scheduled session, when the lecturer has set weekly day/time slots for the course.
- Manage registered devices from Settings.

### Lecturer / Admin
- Create courses and upload the enrolled student list (paste or CSV — Excel exports with headers and BOMs are handled).
- Set weekly day/time slots per course to power the student's "next class" widget.
- Start and end class sessions; discard a session opened by accident (voided sessions never count against students).
- One personal QR code that covers all of the lecturer's courses.
- Per-session present/absent lists and per-student attendance percentages across the course.
- Manually mark an absent student present after a session ends, with a required reason; reversible via undo.
- Export attendance to a spreadsheet (whole course or single session).
- Review flagged scans, low-attendance students, and shared-device alerts.

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.13, Flask |
| Database | PostgreSQL (SQLite for local dev), SQLAlchemy, Flask-Migrate |
| Auth | Flask-Login sessions; Google OAuth (Authlib) and email + password (hashed) |
| QR generation | `qrcode` |
| QR scanning | `html5-qrcode` via the phone camera |
| Location check | Browser Geolocation API + Haversine distance |
| Device lock | Private device ID in a secure HTTP-only cookie |
| Rate limiting | Flask-Limiter on login |
| Frontend | Jinja2 templates, vanilla HTML/CSS/JS — runs in any phone browser |
| Hosting | Railway (gunicorn) |

## Project Structure

```
app/
├── __init__.py        # App factory
├── config.py          # Env-driven config (fails loud without SECRET_KEY in prod)
├── models.py          # User, Course, ClassScheduleSlot, Enrollment,
│                      # ClassSession, AttendanceRecord, Anomaly, StudentDevice
├── attendance.py      # Scan validation pipeline + absentee marking
├── location.py        # Haversine distance / geofence check
├── devices.py         # Device fingerprinting and lock
├── schedule.py         # Weekly schedule slots + next-class lookup
├── permissions.py       # Role-required route decorators
├── utils.py            # Shared validation helpers
├── qr.py               # QR code generation
├── stats.py            # Attendance percentages
├── blueprints/
│   ├── auth.py        # Register, login, Google OAuth, index linking
│   ├── courses.py     # Courses, rosters, sessions, schedule, overrides, exports
│   ├── scan.py        # QR landing page + scan endpoint
│   ├── anomalies.py   # Flag review
│   ├── review.py      # Low attendance / shared devices
│   └── main.py        # Dashboards, history, settings, health check
├── templates/         # Jinja2 templates
└── static/            # CSS + JS
migrations/            # Alembic migrations
seed.py                # Demo data for local development
run.py                 # Entry point
```

## Running Locally

Requires Python 3.13.

```bash
# 1. Clone and enter the project
git clone <repo-url> && cd <repo>

# 2. Create a virtualenv and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env        # edit SECRET_KEY at minimum

# 4. Create the database schema
flask --app run.py db upgrade

# 5. (Optional) load demo data
python seed.py

# 6. Run
python run.py               # http://127.0.0.1:5000
```

With seed data loaded, two demo accounts are available (password `password123`):

- `student@demo.com` — student view
- `lecturer@demo.com` — lecturer console

> **Note:** GPS checks need real browser geolocation, so the scan flow is best tested on a phone. The demo seed uses University of Cape Coast campus coordinates as the classroom location.

## Configuration

All settings come from environment variables (`.env` locally, service variables on Railway):

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | — | Session signing. **Required in production** — the app refuses to start without it. |
| `DATABASE_URL` | `sqlite:///attendance.db` | PostgreSQL in production; `postgres://` URLs are normalised automatically. |
| `STAFF_SIGNUP_CODE` | *(unset)* | When set, lecturer registration requires this code. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | *(unset)* | Enables Google sign-in. |
| `SCAN_WINDOW_MINUTES` | `120` | How long after session start scans are accepted. |
| `CLASSROOM_RADIUS_M` | `200` | Geofence radius around the captured room location. |
| `GPS_ACCURACY_LIMIT_M` | `50` | Scans with worse GPS accuracy than this are rejected. |

## Deployment

The app is set up for Railway (`railway.json`): on each deploy it runs pending migrations, then starts gunicorn with a `/health` healthcheck. Any host that can run a Flask/gunicorn app against PostgreSQL works the same way:

```bash
flask --app run.py db upgrade && gunicorn --bind 0.0.0.0:$PORT run:app
```

Production hardening is built in: secure/HTTP-only/SameSite session cookies, hashed passwords, login rate limiting, constant-time staff-code comparison, and a hard failure if `SECRET_KEY` is missing.

## Roadmap

- Rotating / refreshing QR codes
- Automatic low-attendance alerts to students
- Student-initiated attendance correction requests
- Auto-starting sessions from the weekly schedule (currently the schedule only powers the student's "next class" widget; the lecturer still taps Start to open scanning)
