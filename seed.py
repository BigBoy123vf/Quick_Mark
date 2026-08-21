"""
Dev seed — wipes and recreates all tables, then inserts demo data.
Run: .venv/bin/python seed.py

Test logins (both password123):
  student@demo.com   — Ama Mensah   (student)
  lecturer@demo.com  — Dr. Kwame Asante (admin)
"""
import random
import secrets
from datetime import datetime, timedelta

from app import create_app
from app.extensions import database
from app.models import Anomaly, AttendanceRecord, ClassSession, Course, Enrollment, StudentDevice, User

app = create_app()

# University of Cape Coast campus coordinates, reused as each class's room location.
CAMPUS_LATITUDE = 5.1053
CAMPUS_LONGITUDE = -1.2813

# Deterministic so every run produces the same demo data.
RANDOM_SEED = 20260629

# email, full_name
LECTURERS = [
    ("lecturer@demo.com", "Dr. Kwame Asante"),
    ("efua.boateng@demo.com", "Dr. Efua Boateng"),
    ("yaw.darko@demo.com", "Prof. Yaw Darko"),
]

# email, full_name, index_number, attendance_reliability (chance of being present)
STUDENTS = [
    ("student@demo.com", "Ama Mensah", "PS/ITC/21/0042", 0.8),
    ("kojo.owusu@demo.com", "Kojo Owusu", "PS/ITC/21/0017", 0.95),
    ("abena.sarpong@demo.com", "Abena Sarpong", "PS/ITC/21/0023", 0.6),
    ("kofi.adjei@demo.com", "Kofi Adjei", "PS/ITC/21/0031", 0.7),
    ("esi.appiah@demo.com", "Esi Appiah", "PS/ITC/21/0055", 0.45),
    ("yaa.frimpong@demo.com", "Yaa Frimpong", "PS/ITC/21/0061", 0.88),
    ("nana.acheampong@demo.com", "Nana Acheampong", "PS/ITC/21/0072", 0.5),
    ("akua.bediako@demo.com", "Akua Bediako", "PS/ITC/21/0088", 0.92),
    ("kwesi.boakye@demo.com", "Kwesi Boakye", "PS/ITC/21/0110", 0.4),
    ("adjoa.nyame@demo.com", "Adjoa Nyame", "PS/ITC/21/0117", 0.55),
]

# Per-student phones for the Student devices page. Real UA strings so the
# OS/browser parsers produce believable fingerprints. removed_weeks marks
# an old phone the student switched away from.
STUDENT_DEVICES = {
    "student@demo.com": [
        dict(name="iPhone", model="iPhone 13", screen="390×844 @3x", cores=6, memory=4,
             ip="196.61.44.23", weeks_old=14,
             ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"),
    ],
    "kojo.owusu@demo.com": [
        dict(name="Android phone", model="Samsung Galaxy A54", screen="393×852 @2.75x", cores=8, memory=6,
             ip="154.160.9.87", weeks_old=13,
             ua="Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36"),
    ],
    "abena.sarpong@demo.com": [
        dict(name="Android phone", model="Tecno Spark 10", screen="360×800 @2x", cores=8, memory=4,
             ip="41.66.201.118", weeks_old=14, removed_weeks=3,
             ua="Mozilla/5.0 (Linux; Android 13; TECNO KI5q) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36"),
        dict(name="Android phone", model="Samsung Galaxy A15", screen="393×873 @2.75x", cores=8, memory=6,
             ip="196.61.44.108", weeks_old=3,
             ua="Mozilla/5.0 (Linux; Android 14; SM-A155F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"),
    ],
    "kofi.adjei@demo.com": [
        dict(name="Android phone", model="Infinix Note 30", screen="393×873 @2.72x", cores=8, memory=8,
             ip="154.160.22.140", weeks_old=12,
             ua="Mozilla/5.0 (Linux; Android 13; Infinix X6833B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36 OPR/76.2.4027.73374"),
        dict(name="iPhone", model="iPhone 11", screen="414×896 @2x", cores=6, memory=4,
             ip="41.66.201.35", weeks_old=6,
             ua="Mozilla/5.0 (iPhone; CPU iPhone OS 16_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"),
    ],
    "esi.appiah@demo.com": [
        dict(name="Android phone", model="itel A58", screen="360×780 @1.5x", cores=4, memory=2,
             ip="41.66.220.7", weeks_old=15, removed_weeks=9,
             ua="Mozilla/5.0 (Linux; Android 12; itel A662L) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36"),
        dict(name="Android phone", model="Tecno Camon 20", screen="393×873 @2.72x", cores=8, memory=8,
             ip="196.61.44.19", weeks_old=9, removed_weeks=1,
             ua="Mozilla/5.0 (Linux; Android 13; TECNO CK6n) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"),
        dict(name="Android phone", model="Samsung Galaxy A25", screen="393×873 @2.75x", cores=8, memory=6,
             ip="154.160.31.66", weeks_old=1,
             ua="Mozilla/5.0 (Linux; Android 14; SM-A256E) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36"),
    ],
    "yaa.frimpong@demo.com": [
        dict(name="Android phone", model="Infinix Hot 40i", screen="393×873 @2.72x", cores=8, memory=4,
             ip="154.160.14.201", weeks_old=11,
             ua="Mozilla/5.0 (Linux; Android 13; Infinix X6528) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36"),
    ],
    "nana.acheampong@demo.com": [
        dict(name="Android phone", model="Samsung Galaxy M14", screen="412×892 @2.63x", cores=8, memory=4,
             ip="196.61.47.12", weeks_old=10,
             ua="Mozilla/5.0 (Linux; Android 13; SM-M146B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/24.0 Chrome/117.0.0.0 Mobile Safari/537.36"),
    ],
    "akua.bediako@demo.com": [
        dict(name="Android phone", model="Xiaomi Redmi Note 12", screen="393×873 @2.75x", cores=8, memory=6,
             ip="41.66.213.90", weeks_old=13,
             ua="Mozilla/5.0 (Android 14; Mobile; rv:126.0) Gecko/126.0 Firefox/126.0"),
    ],
    "kwesi.boakye@demo.com": [
        dict(name="Android phone", model="Tecno Pop 8", screen="360×800 @2x", cores=4, memory=3,
             ip="154.160.40.55", weeks_old=8,
             ua="Mozilla/5.0 (Linux; Android 13; TECNO BG6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36"),
    ],
    "adjoa.nyame@demo.com": [
        dict(name="iPhone", model="iPhone XR", screen="414×896 @2x", cores=6, memory=3,
             ip="196.61.44.61", weeks_old=12,
             ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"),
    ],
}

# Roster entries with no matching account yet (tests the unlinked-enrollment path).
UNLINKED_ROSTER = [
    ("PS/ITC/21/0099", "Selorm Agbeko"),
    ("PS/ITC/21/0104", "Hannah Otieno"),
]

# code, title, lecturer_email, [enrolled student emails], ended_session_count, has_live_session
COURSES = [
    ("CSCD 101", "Introduction to Computing", "lecturer@demo.com",
     ["student@demo.com", "kojo.owusu@demo.com", "abena.sarpong@demo.com",
      "kofi.adjei@demo.com", "esi.appiah@demo.com", "kwesi.boakye@demo.com",
      "adjoa.nyame@demo.com"], 10, True),
    ("CSCD 205", "Data Structures and Algorithms", "lecturer@demo.com",
     ["student@demo.com", "kojo.owusu@demo.com", "yaa.frimpong@demo.com",
      "nana.acheampong@demo.com", "kwesi.boakye@demo.com",
      "adjoa.nyame@demo.com"], 6, False),
    ("MATH 105", "Calculus I", "efua.boateng@demo.com",
     ["student@demo.com", "abena.sarpong@demo.com", "kofi.adjei@demo.com",
      "esi.appiah@demo.com", "akua.bediako@demo.com"], 10, False),
    ("PHYS 101", "Physics for Scientists", "yaw.darko@demo.com",
     ["student@demo.com", "kojo.owusu@demo.com", "yaa.frimpong@demo.com",
      "nana.acheampong@demo.com", "akua.bediako@demo.com"], 8, False),
    ("STAT 201", "Introduction to Statistics", "efua.boateng@demo.com",
     ["kojo.owusu@demo.com", "abena.sarpong@demo.com", "yaa.frimpong@demo.com",
      "akua.bediako@demo.com"], 7, False),
]


def make_session(course_id, weeks_ago, live=False):
    started_at = datetime.utcnow() - timedelta(weeks=weeks_ago, hours=1)
    session = ClassSession(
        course_id=course_id,
        started_at=started_at,
        ended_at=None if live else started_at + timedelta(hours=1),
        latitude=CAMPUS_LATITUDE,
        longitude=CAMPUS_LONGITUDE,
        location_accuracy=15.0,
    )
    return session


with app.app_context():
    random.seed(RANDOM_SEED)
    database.drop_all()
    database.create_all()

    users_by_email = {}

    for email, full_name in LECTURERS:
        lecturer = User(
            email=email,
            full_name=full_name,
            role="admin",
            qr_token=secrets.token_urlsafe(9),
        )
        lecturer.set_password("password123")
        database.session.add(lecturer)
        users_by_email[email] = lecturer

    for email, full_name, index_number, _reliability in STUDENTS:
        student = User(
            email=email,
            full_name=full_name,
            role="student",
            index_number=index_number,
            device_id=secrets.token_hex(16),
        )
        student.set_password("password123")
        database.session.add(student)
        users_by_email[email] = student

    database.session.flush()

    reliability_by_email = {email: rel for email, _name, _idx, rel in STUDENTS}

    for code, title, lecturer_email, enrolled_emails, ended_count, has_live in COURSES:
        course = Course(
            code=code,
            title=title,
            lecturer_id=users_by_email[lecturer_email].id,
        )
        database.session.add(course)
        database.session.flush()

        for email in enrolled_emails:
            student = users_by_email[email]
            database.session.add(Enrollment(
                course_id=course.id,
                index_number=student.index_number,
                full_name=student.full_name,
                student_id=student.id,
            ))

        for index_number, full_name in UNLINKED_ROSTER:
            database.session.add(Enrollment(
                course_id=course.id,
                index_number=index_number,
                full_name=full_name,
                student_id=None,
            ))

        # Oldest first so weeks_ago counts down toward the most recent class.
        for weeks_ago in range(ended_count, 0, -1):
            session = make_session(course.id, weeks_ago)
            database.session.add(session)
            database.session.flush()

            for email in enrolled_emails:
                student = users_by_email[email]
                present = random.random() < reliability_by_email[email]
                record = AttendanceRecord(
                    session_id=session.id,
                    student_id=student.id,
                    status="present" if present else "absent",
                    scanned_at=session.started_at + timedelta(minutes=random.randint(2, 20)) if present else None,
                    latitude=CAMPUS_LATITUDE if present else None,
                    longitude=CAMPUS_LONGITUDE if present else None,
                    device_id=student.device_id if present else None,
                )
                database.session.add(record)

        if has_live:
            database.session.add(make_session(course.id, 0, live=True))

    # Registered phones for the Student devices page.
    for email, phone_specs in STUDENT_DEVICES.items():
        owner = users_by_email[email]
        for spec in phone_specs:
            created_at = datetime.utcnow() - timedelta(weeks=spec["weeks_old"])
            deleted_at = (
                datetime.utcnow() - timedelta(weeks=spec["removed_weeks"])
                if spec.get("removed_weeks") is not None else None
            )
            last_seen_at = deleted_at or datetime.utcnow() - timedelta(hours=random.randint(2, 40))
            database.session.add(StudentDevice(
                student_id=owner.id,
                device_uuid=secrets.token_urlsafe(32),
                device_name=spec["name"],
                user_agent=spec["ua"],
                first_seen_ip=spec["ip"],
                last_seen_ip=spec["ip"],
                last_seen_at=last_seen_at,
                created_at=created_at,
                deleted_at=deleted_at,
                device_model=spec["model"],
                screen=spec["screen"],
                cpu_cores=spec["cores"],
                device_memory=spec["memory"],
                timezone="Africa/Accra",
            ))

    # A handful of device anomalies for the lecturer's review audit log.
    database.session.flush()
    cscd101 = Course.query.filter_by(code="CSCD 101").first()
    cscd101_sessions = (
        ClassSession.query.filter_by(course_id=cscd101.id)
        .filter(ClassSession.ended_at.isnot(None))
        .order_by(ClassSession.started_at.desc())
        .all()
    )
    abena = users_by_email["abena.sarpong@demo.com"]
    kofi = users_by_email["kofi.adjei@demo.com"]
    esi = users_by_email["esi.appiah@demo.com"]
    lecturer = users_by_email["lecturer@demo.com"]

    # Unreviewed: an extra phone signed in to Abena's account (no session context).
    database.session.add(Anomaly(
        anomaly_type="new_device",
        severity="info",
        session_id=None,
        student_id=abena.id,
        reason="New device signed in to this account",
        device_id=secrets.token_hex(16),
        ip_address="196.61.44.108",
        details={"device": "Android phone"},
        detected_at=cscd101_sessions[0].started_at + timedelta(minutes=3),
    ))
    # Unreviewed: Kofi's mark came from a phone that had already marked Esi.
    database.session.add(Anomaly(
        anomaly_type="proxy_scan_suspected",
        severity="warn",
        session_id=cscd101_sessions[0].id,
        student_id=kofi.id,
        reason="Same device used for several students",
        device_id=esi.device_id,
        ip_address="196.61.44.72",
        details={"shared_with": esi.full_name, "shared_with_index": esi.index_number},
        detected_at=cscd101_sessions[0].started_at + timedelta(minutes=11),
    ))
    # Reviewed with a note: Esi tried to scan from outside the room.
    database.session.add(Anomaly(
        anomaly_type="geofence_far",
        severity="info",
        session_id=cscd101_sessions[1].id,
        student_id=esi.id,
        reason="Scan attempted from outside the room",
        device_id=esi.device_id,
        ip_address="196.61.44.19",
        details={"distance_m": 214, "radius_m": 50, "accuracy_m": 22},
        detected_at=cscd101_sessions[1].started_at + timedelta(minutes=7),
        reviewed=True,
        reviewed_by_id=lecturer.id,
        reviewed_at=cscd101_sessions[1].started_at + timedelta(hours=3),
        reviewer_notes="Was in the corridor — spoke to her after class.",
    ))
    # Reviewed without a note.
    database.session.add(Anomaly(
        anomaly_type="new_device",
        severity="info",
        session_id=None,
        student_id=kofi.id,
        reason="New device signed in to this account",
        device_id=secrets.token_hex(16),
        ip_address="41.66.201.35",
        details={"device": "iPhone"},
        detected_at=cscd101_sessions[2].started_at + timedelta(minutes=1),
        reviewed=True,
        reviewed_by_id=lecturer.id,
        reviewed_at=cscd101_sessions[1].started_at + timedelta(hours=1),
    ))

    nana = users_by_email["nana.acheampong@demo.com"]
    kwesi = users_by_email["kwesi.boakye@demo.com"]
    adjoa = users_by_email["adjoa.nyame@demo.com"]
    ama = users_by_email["student@demo.com"]
    cscd205 = Course.query.filter_by(code="CSCD 205").first()
    cscd205_latest = (
        ClassSession.query.filter_by(course_id=cscd205.id)
        .order_by(ClassSession.started_at.desc())
        .first()
    )
    cscd101_live = ClassSession.query.filter_by(course_id=cscd101.id, ended_at=None).first()

    # Fresh, unreviewed entries on the live session — these land in "Last 24 hours".
    database.session.add(Anomaly(
        anomaly_type="geofence_far",
        severity="info",
        session_id=cscd101_live.id,
        student_id=kwesi.id,
        reason="Scan attempted from outside the room",
        device_id=secrets.token_hex(16),
        ip_address="154.160.40.55",
        details={"distance_m": 386, "radius_m": 50, "accuracy_m": 18},
        detected_at=datetime.utcnow() - timedelta(minutes=42),
    ))
    database.session.add(Anomaly(
        anomaly_type="proxy_scan_suspected",
        severity="warn",
        session_id=cscd101_live.id,
        student_id=adjoa.id,
        reason="Same device used for several students",
        device_id=ama.device_id,
        ip_address="196.61.44.23",
        details={"shared_with": ama.full_name, "shared_with_index": ama.index_number},
        detected_at=datetime.utcnow() - timedelta(minutes=27),
    ))
    # Unreviewed: Nana far outside the room in Data Structures.
    database.session.add(Anomaly(
        anomaly_type="geofence_far",
        severity="info",
        session_id=cscd205_latest.id,
        student_id=nana.id,
        reason="Scan attempted from outside the room",
        device_id=secrets.token_hex(16),
        ip_address="196.61.47.12",
        details={"distance_m": 1408, "radius_m": 50, "accuracy_m": 31},
        detected_at=cscd205_latest.started_at + timedelta(minutes=16),
    ))
    # Unreviewed: an extra phone on Kofi's account two days ago.
    database.session.add(Anomaly(
        anomaly_type="new_device",
        severity="info",
        session_id=None,
        student_id=kofi.id,
        reason="New device signed in to this account",
        device_id=secrets.token_hex(16),
        ip_address="41.66.201.35",
        details={"device": "iPhone"},
        detected_at=datetime.utcnow() - timedelta(days=2, hours=5),
    ))
    # Reviewed with a note: Esi's latest phone switch was legitimate.
    database.session.add(Anomaly(
        anomaly_type="new_device",
        severity="info",
        session_id=None,
        student_id=esi.id,
        reason="New device signed in to this account",
        device_id=secrets.token_hex(16),
        ip_address="154.160.31.66",
        details={"device": "Android phone"},
        detected_at=datetime.utcnow() - timedelta(days=6, hours=2),
        reviewed=True,
        reviewed_by_id=lecturer.id,
        reviewed_at=datetime.utcnow() - timedelta(days=5, hours=20),
        reviewer_notes="Confirmed — her old phone's screen broke.",
    ))

    database.session.commit()

    print("Database reset and seeded.")
    print(f"  {User.query.filter_by(role='admin').count()} lecturers, "
          f"{User.query.filter_by(role='student').count()} students, "
          f"{Course.query.count()} courses, "
          f"{ClassSession.query.count()} sessions, "
          f"{AttendanceRecord.query.count()} attendance records, "
          f"{Anomaly.query.count()} anomalies")
    print()
    print("Test logins (password123):")
    print("  Student : student@demo.com   (Ama Mensah)")
    print("  Lecturer: lecturer@demo.com  (Dr. Kwame Asante)")
