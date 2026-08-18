#!/usr/bin/env python3
"""
JNTUACEA - Student Academic Record Book (Attendance Portal)
Single-file web app. Python 3 standard library only. SQLite storage.

Run:  python3 app.py
Default admin login : admin / admin123  (change it from Admin > Settings)
Student login      : Roll Number / Roll Number (default password)
"""

import os
import re
import io
import csv
import json
import math
import time
import html
import random
import sqlite3
import hashlib
import secrets
from datetime import datetime, date, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote, unquote
from http.cookies import SimpleCookie

# ---------------------------------------------------------------- config ----
BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, 'attendance.db')
PORT = int(os.environ.get('PORT', '8000'))
IST = timezone(timedelta(hours=5, minutes=30))
COLLEGE = 'JNTUA College of Engineering Ananthapuramu'
COLLEGE_SHORT = 'JNTUACEA'

BRANCHES = {
    'CSE': 'Computer Science & Engineering',
    'ECE': 'Electronics & Communication Engineering',
    'EEE': 'Electrical & Electronics Engineering',
    'ME': 'Mechanical Engineering',
    'CE': 'Civil Engineering',
}
BRANCH_CODE = {'CE': '01', 'EEE': '02', 'ME': '03', 'ECE': '04', 'CSE': '05'}
YEAR_ROMAN = {1: 'I', 2: 'II', 3: 'III', 4: 'IV'}
PORTAL_URL = 'https://jntuaceastudents.classattendance.in'
BRIDGE_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')


# ---------------------------------------------------------------- database --
def conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def q1(sql, args=()):
    con = conn()
    try:
        return con.execute(sql, args).fetchone()
    finally:
        con.close()


def qall(sql, args=()):
    con = conn()
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def run(sql, args=()):
    con = conn()
    try:
        cur = con.execute(sql, args)
        con.commit()
        return cur
    finally:
        con.close()


def sha(txt):
    return hashlib.sha256(txt.encode()).hexdigest()


def guess_from_roll(roll):
    """Best-effort branch + year from a JNTUA-style roll (e.g. 23001A0204)."""
    branch, year = 'CSE', 2
    try:
        if roll[:2].isdigit():
            intake = 2000 + int(roll[:2])
            if 2010 <= intake <= 2099:
                now = now_ist()
                yr = now.year - intake + (1 if now.month >= 8 else 0)
                year = max(1, min(4, yr))
        code = roll[6:8] if len(roll) >= 8 else ''
        for b, c in BRANCH_CODE.items():
            if code == c:
                branch = b
                break
    except Exception:
        pass
    return branch, year


def dob_matches(password, dob):
    """Login password vs stored DOB — tolerant of separators & ddmmyyyy/yyyymmdd order."""
    if not dob:
        return False
    p = re.sub(r'[^0-9]', '', password or '')
    d = re.sub(r'[^0-9]', '', dob)
    if not p or not d:
        return False
    if p == d:
        return True
    if len(p) == 8 and len(d) == 8:
        swapped = d[6:8] + d[4:6] + d[0:4]  # yyyymmdd -> ddmmyyyy
        if p == swapped:
            return True
    return False


def now_ist():
    return datetime.now(IST)


def today_str():
    return now_ist().strftime('%Y-%m-%d')


def db_init():
    con = conn()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS students(
      roll TEXT PRIMARY KEY, name TEXT NOT NULL, branch TEXT NOT NULL,
      year INTEGER NOT NULL, section TEXT NOT NULL DEFAULT 'A',
      password TEXT NOT NULL, email TEXT DEFAULT '', dob TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS subjects(
      id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, name TEXT NOT NULL,
      branch TEXT NOT NULL, year INTEGER NOT NULL, section TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS attendance(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      roll TEXT NOT NULL, subject_id INTEGER NOT NULL, date TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'P', marked_by TEXT DEFAULT 'admin',
      marked_at TEXT DEFAULT '',
      UNIQUE(roll, subject_id, date));
    CREATE TABLE IF NOT EXISTS sessions(
      token TEXT PRIMARY KEY, role TEXT NOT NULL, roll TEXT DEFAULT '',
      created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS settings(
      key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS selfmark(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject_id INTEGER NOT NULL, date TEXT NOT NULL,
      open_until TEXT DEFAULT '', enabled INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS sync_log(
      id INTEGER PRIMARY KEY AUTOINCREMENT, roll TEXT NOT NULL,
      at TEXT NOT NULL, ok INTEGER DEFAULT 0, message TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS bridge_cookies(
      token TEXT PRIMARY KEY, cookies TEXT NOT NULL, updated_at TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS att_summary(
      roll TEXT NOT NULL, key TEXT NOT NULL, subject_name TEXT NOT NULL,
      total INTEGER NOT NULL, present INTEGER NOT NULL, updated_at TEXT DEFAULT '',
      PRIMARY KEY(roll, key));
    """)
    if not con.execute("SELECT 1 FROM settings WHERE key='admin_pass'").fetchone():
        con.execute("INSERT INTO settings(key,value) VALUES('admin_pass', ?)", (sha('admin123'),))
    # migration: add dob column to existing databases
    cols = [r['name'] for r in con.execute("PRAGMA table_info(students)").fetchall()]
    if 'dob' not in cols:
        con.execute("ALTER TABLE students ADD COLUMN dob TEXT NOT NULL DEFAULT ''")
    con.commit()
    con.close()
    seed_demo()


def seed_demo():
    if q1("SELECT COUNT(*) c FROM students")['c'] > 0:
        return
    names = [
        'Abhishek Reddy', 'Akhila S', 'Anil Kumar', 'Bhavana M', 'Charan Teja',
        'Deepika R', 'Divya Sri', 'Ganesh P', 'Harika V', 'Harsha Vardhan',
        'Jahnavi K', 'Karthik N', 'Kavya B', 'Lakshmi Priya', 'Madhu Babu',
        'Manoj Kumar', 'Naveen G', 'Nikitha S', 'Pavan Kalyan', 'Pooja M',
        'Praveen Kumar', 'Ravi Teja', 'Sai Krishna', 'Sandhya R', 'Sravani T',
        'Suresh B', 'Swathi M', 'Tejaswi N', 'Uday Kiran', 'Vamsi Krishna',
        'Venkatesh P', 'Vijay Kumar', 'Yaswanth R', 'Aishwarya D', 'Bhanu Prakash',
        'Chaitanya K', 'Deepthi S', 'Eswar Reddy', 'Farhana S', 'Gayathri V',
    ]
    students = []
    # CSE II year A (rolls 22A51A0501..20), CSE II year B, ECE II year A, CSE I year A
    for i in range(20):
        students.append(('22A51A05%02d' % (i + 1), names[i], 'CSE', 2, 'A'))
    for i in range(10):
        students.append(('22A51A05%02d' % (i + 21), names[i + 20], 'CSE', 2, 'B'))
    for i in range(8):
        students.append(('22A51A04%02d' % (i + 1), names[i + 30], 'ECE', 2, 'A'))
    for i in range(6):
        students.append(('23A51A05%02d' % (i + 1), names[i + 10], 'CSE', 1, 'A'))
    con = conn()
    for idx, (roll, nm, br, yr, sec) in enumerate(students):
        dob = '%04d-%02d-%02d' % (2003 + (idx % 3), (idx * 7) % 12 + 1, (idx * 13) % 28 + 1)
        con.execute("INSERT OR IGNORE INTO students(roll,name,branch,year,section,password,dob) VALUES(?,?,?,?,?,?,?)",
                    (roll, nm, br, yr, sec, sha(roll), dob))
    subjects = [
        ('19A05402', 'Operating Systems', 'CSE', 2),
        ('19A05403', 'Database Management Systems', 'CSE', 2),
        ('19A05404', 'Design & Analysis of Algorithms', 'CSE', 2),
        ('19A05405', 'Formal Languages & Automata Theory', 'CSE', 2),
        ('19A05406', 'Probability & Statistics', 'CSE', 2),
        ('19A05407', 'Managerial Economics & Financial Analysis', 'CSE', 2),
        ('19A04402', 'Analog & Digital Communications', 'ECE', 2),
        ('19A04403', 'Signals & Systems', 'ECE', 2),
        ('19A04404', 'Electronic Circuits II', 'ECE', 2),
        ('19A05401', 'Data Structures', 'CSE', 1),
        ('19A05402', 'Mathematics - II', 'CSE', 1),
        ('19A05403', 'Applied Physics', 'CSE', 1),
        ('19A05404', 'Python Programming', 'CSE', 1),
    ]
    for code, nm, br, yr in subjects:
        con.execute("INSERT INTO subjects(code,name,branch,year,section) VALUES(?,?,?,?,'')",
                    (code, nm, br, yr))
    con.commit()

    # demo attendance: last ~40 weekdays
    rnd = random.Random(42)
    d = date.today()
    days = []
    while len(days) < 40:
        if d.weekday() < 6:  # include Sunday too for demo richness (colleges often work Sat)
            days.append(d)
        d -= timedelta(days=1)
    days = sorted(days)
    sub_rows = con.execute("SELECT * FROM subjects").fetchall()
    for st in con.execute("SELECT * FROM students").fetchall():
        my_subs = [s for s in sub_rows if s['branch'] == st['branch'] and s['year'] == st['year']]
        for s in my_subs:
            for day in days:
                status = 'P' if rnd.random() < 0.88 else 'A'
                con.execute(
                    "INSERT OR IGNORE INTO attendance(roll,subject_id,date,status,marked_by,marked_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (st['roll'], s['id'], day.strftime('%Y-%m-%d'), status, 'admin',
                     day.strftime('%Y-%m-%d') + ' 09:30'))
    con.commit()
    con.close()


# ---------------------------------------------------------------- helpers ----
def esc(txt):
    return html.escape(str(txt), quote=True)


def ring(pct, size=92, stroke=10):
    pct = max(0, min(100, round(pct)))
    r = (size - stroke) / 2
    c = 2 * math.pi * r
    dash = c * pct / 100.0
    color = '#2e9e5b' if pct >= 75 else ('#f0a429' if pct >= 60 else '#d64545')
    return ('<svg width="%d" height="%d" viewBox="0 0 %d %d">'
            '<circle cx="%d" cy="%d" r="%d" fill="none" stroke="#e6eaf2" stroke-width="%d"/>'
            '<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="%d" stroke-linecap="round" '
            'stroke-dasharray="%.1f %.1f" transform="rotate(-90 %d %d)"/>'
            '<text x="50%%" y="50%%" dominant-baseline="central" text-anchor="middle" '
            'font-size="%d" font-weight="700" fill="#17305c">%d%%</text></svg>'
            % (size, size, size, size, size // 2, size // 2, r, stroke,
               size // 2, size // 2, r, color, stroke, dash, c - dash, size // 2, size // 2,
               int(size * 0.22), pct))


def pct_color(p):
    return '#2e9e5b' if p >= 75 else ('#f0a429' if p >= 60 else '#d64545')


def status_badge(s):
    if s == 'P':
        return '<span class="badge b-p">Present</span>'
    if s == 'A':
        return '<span class="badge b-a">Absent</span>'
    return '<span class="badge b-n">Not marked</span>'


def year_label(y):
    return 'I Year' if y == 1 else (YEAR_ROMAN.get(y, str(y)) + ' Year') + ' B.Tech'


def fmt_date(s):
    try:
        return datetime.strptime(s, '%Y-%m-%d').strftime('%d %b %Y')
    except Exception:
        return s


def weekday_name(s):
    try:
        return datetime.strptime(s, '%Y-%m-%d').strftime('%a')
    except Exception:
        return ''


def student_subs(roll):
    st = q1("SELECT * FROM students WHERE roll=?", (roll,))
    if not st:
        return []
    return qall("SELECT * FROM subjects WHERE branch=? AND year=? AND (section='' OR section=?)",
                (st['branch'], st['year'], st['section']))


def subject_stats(roll, subject_id=None):
    if subject_id:
        r = q1("SELECT COUNT(*) t, SUM(CASE WHEN status='P' THEN 1 ELSE 0 END) p, "
               "SUM(CASE WHEN status='A' THEN 1 ELSE 0 END) a FROM attendance "
               "WHERE roll=? AND subject_id=?", (roll, subject_id))
        return {'t': r['t'] or 0, 'p': r['p'] or 0, 'a': r['a'] or 0}
    r = q1("SELECT COUNT(*) t, SUM(CASE WHEN status='P' THEN 1 ELSE 0 END) p, "
           "SUM(CASE WHEN status='A' THEN 1 ELSE 0 END) a FROM attendance WHERE roll=?",
           (roll,))
    return {'t': r['t'] or 0, 'p': r['p'] or 0, 'a': r['a'] or 0}


def pct_of(st):
    return (st['p'] * 100.0 / st['t']) if st['t'] else 0.0


def norm_date_any(s):
    """Flexible date parser: dd-mm-yyyy, dd/mm/yyyy, yyyy-mm-dd, dd-Mon-yyyy."""
    s = (s or '').strip()
    m = re.match(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$', s)
    if m:
        return '%s-%s-%s' % (m.group(3), m.group(2).zfill(2), m.group(1).zfill(2))
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', s)
    if m:
        return '%s-%02d-%02d' % (m.group(1), int(m.group(2)), int(m.group(3)))
    try:
        return datetime.strptime(s, '%d-%b-%Y').strftime('%Y-%m-%d')
    except Exception:
        try:
            return datetime.strptime(s, '%d %b %Y').strftime('%Y-%m-%d')
        except Exception:
            return ''


def find_or_create_subject(name, branch, year):
    """Match official subject by name; auto-create under student branch/year if new."""
    nm = name.strip()
    subj = q1("SELECT * FROM subjects WHERE upper(name)=? AND branch=? AND year=?",
              (nm.upper(), branch, year))
    if not subj:
        subj = q1("SELECT * FROM subjects WHERE upper(name)=?", (nm.upper(),))
    if not subj:
        subj = q1("SELECT * FROM subjects WHERE upper(name) LIKE ?",
                  ('%' + nm.upper() + '%',))
    if subj:
        return subj['id']
    code = 'OF' + hashlib.sha256(nm.upper().encode()).hexdigest()[:6].upper()
    cur = run("INSERT INTO subjects(code,name,branch,year,section) VALUES(?,?,?,?,'')",
              (code, nm, branch, year))
    return cur.lastrowid


def apply_official_sync(roll, odata):
    """Store official portal records for a student. Returns (subjects_synced, records_synced)."""
    st = q1("SELECT branch, year FROM students WHERE roll=?", (roll,))
    if not st:
        return 0, 0
    total_recs = total_subs = 0
    for subj in odata.get('subjects', []):
        nm = (subj.get('subject') or '').strip()
        if not nm:
            continue
        sid = find_or_create_subject(nm, st['branch'], st['year'])
        stored = 0
        for rec in subj.get('records', []):
            d = norm_date_any(rec.get('date', ''))
            if not d or rec.get('status') not in ('P', 'A'):
                continue
            run("INSERT INTO attendance(roll,subject_id,date,status,marked_by,marked_at) "
                "VALUES(?,?,?,?, 'official', ?) "
                "ON CONFLICT(roll,subject_id,date) DO UPDATE SET status=excluded.status, "
                "marked_by='official', marked_at=excluded.marked_at",
                (roll, sid, d, rec['status'], now_ist().isoformat(timespec='seconds')))
            stored += 1
        if stored:
            total_subs += 1
            total_recs += stored
    return total_subs, total_recs


# ---------------------------------------------------------------- CSS -------
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--navy:#123a6b;--navy2:#0d2a4f;--gold:#f0b429;--bg:#eef2f8;--card:#ffffff;
--text:#1c2b4a;--muted:#66748f;--line:#e3e8f2;--green:#2e9e5b;--red:#d64545;--amber:#f0a429}
body{font-family:'Segoe UI',system-ui,-apple-system,Roboto,'Noto Sans',Arial,sans-serif;
background:var(--bg);color:var(--text);font-size:15px;line-height:1.5}
a{color:var(--navy);text-decoration:none}
.topbar{background:linear-gradient(90deg,var(--navy2),var(--navy));
color:#fff;padding:10px 20px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;
position:sticky;top:0;z-index:50;box-shadow:0 2px 10px rgba(13,42,79,.25)}
.topbar img{height:46px;width:46px;border-radius:50%;background:#fff;padding:3px;object-fit:contain}
.topbar .t1{font-weight:700;font-size:16px;letter-spacing:.2px}
.topbar .t2{font-size:12px;color:#c9d6ec}
.topbar .spacer{flex:1}
.topbar .user{font-size:13px;background:rgba(255,255,255,.12);padding:7px 14px;border-radius:20px}
.topbar a.logout{color:#ffd;font-size:13px;margin-left:10px;padding:7px 12px;border:1px solid rgba(255,255,255,.4);border-radius:20px}
.topbar a.logout:hover{background:rgba(255,255,255,.15)}
.wrap{max-width:1060px;margin:26px auto;padding:0 16px}
.grid{display:grid;gap:16px}
.g2{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.g3{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.g4{grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}
.card{background:var(--card);border-radius:14px;padding:20px;box-shadow:0 2px 10px rgba(18,58,107,.07);border:1px solid var(--line)}
.card h3{font-size:16px;margin-bottom:12px;color:var(--navy);display:flex;align-items:center;gap:8px}
.card h3 .bar{width:4px;height:18px;background:var(--gold);border-radius:3px}
.sub{color:var(--muted);font-size:13px}
.stat{text-align:center;padding:14px 8px}
.stat .num{font-size:30px;font-weight:800;color:var(--navy)}
.stat .lbl{font-size:12.5px;color:var(--muted);margin-top:2px;text-transform:uppercase;letter-spacing:.5px}
.subj-card{display:flex;align-items:center;gap:14px}
.subj-card .info{flex:1;min-width:0}
.subj-card .code{font-size:11.5px;color:var(--muted);letter-spacing:.4px}
.subj-card .nm{font-weight:700;font-size:15px}
.subj-card .cnt{font-size:12px;color:var(--muted);margin-top:2px}
.badge{display:inline-block;font-size:11.5px;font-weight:600;padding:3px 10px;border-radius:20px}
.b-p{background:#e4f6ec;color:#1d7a45}
.b-a{background:#fdeaea;color:#b23a3a}
.b-n{background:#eef1f6;color:#66748f}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{background:#f4f7fc;color:var(--navy);text-align:left;padding:9px 10px;border-bottom:2px solid var(--line);font-size:12.5px;text-transform:uppercase;letter-spacing:.4px}
td{padding:9px 10px;border-bottom:1px solid var(--line)}
tr:hover td{background:#fafcff}
.form{display:grid;gap:12px}
.form .row{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
label{font-size:12.5px;font-weight:600;color:var(--muted);display:block;margin-bottom:5px;letter-spacing:.3px}
input,select,textarea{width:100%;padding:10px 12px;border:1.5px solid var(--line);border-radius:9px;
font-size:14px;font-family:inherit;background:#fbfcfe;color:var(--text);outline:none}
input:focus,select:focus,textarea:focus{border-color:var(--navy);background:#fff}
.btn{display:inline-block;background:var(--navy);color:#fff;border:none;padding:10px 20px;border-radius:9px;
font-size:14px;font-weight:600;cursor:pointer;text-align:center}
.btn:hover{background:var(--navy2)}
.btn.gold{background:var(--gold);color:#3a2c00}
.btn.green{background:var(--green)}
.btn.red{background:var(--red)}
.btn.outline{background:#fff;color:var(--navy);border:1.5px solid var(--navy)}
.btn.sm{padding:6px 12px;font-size:12.5px;border-radius:7px}
.btn-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:6px}
.notice{background:#fff8e5;border:1px solid #f3df9a;color:#7a5c00;border-radius:10px;padding:12px 16px;font-size:13.5px;margin-bottom:16px}
.notice.green{background:#e8f7ee;border-color:#bfe6cf;color:#16603a}
.notice.red{background:#fdeeee;border-color:#f2c4c4;color:#8f2f2f}
.banner{background:linear-gradient(90deg,var(--navy2),var(--navy));color:#fff;border-radius:14px;
padding:22px 24px;margin-bottom:18px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.banner .big{font-size:20px;font-weight:800}
.banner .small{font-size:13px;color:#c9d6ec}
.banner img{height:58px;background:#fff;border-radius:50%;padding:4px}
.tabs{display:flex;border-bottom:2px solid var(--line);margin-bottom:18px;gap:4px;flex-wrap:wrap}
.tab{padding:9px 18px;border:none;background:none;font-size:14px;font-weight:600;color:var(--muted);
cursor:pointer;border-radius:8px 8px 0 0}
.tab.on{color:var(--navy);border-bottom:3px solid var(--gold);margin-bottom:-2px}
.pill{display:inline-flex;align-items:center;gap:5px;background:#eef2f9;border-radius:20px;padding:4px 12px;font-size:12.5px;color:var(--navy)}
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;
background:linear-gradient(135deg,#0d2a4f 0%,#123a6b 55%,#1a4d8f 100%);padding:20px}
.login-card{background:#fff;border-radius:18px;padding:34px 30px;width:100%;max-width:430px;
box-shadow:0 20px 60px rgba(0,0,0,.35)}
.brand{text-align:center;margin-bottom:20px}
.brand img{height:86px;border-radius:50%;background:#fff;padding:5px;border:3px solid var(--gold);box-shadow:0 0 0 3px var(--navy)}
.brand .bt{font-weight:800;font-size:17px;color:var(--navy);margin-top:10px;line-height:1.35}
.brand .bs{color:var(--gold);font-weight:700;font-size:13.5px;letter-spacing:1.5px;text-transform:uppercase;margin-top:2px}
.brand .bl{color:var(--muted);font-size:12px;margin-top:4px}
.login-card .field{margin-bottom:14px}
.login-btn{width:100%;padding:12px;font-size:15px;margin-top:6px}
.hint{font-size:12px;color:var(--muted);text-align:center;margin-top:14px;background:#f4f7fc;border-radius:8px;padding:8px}
.err{background:#fdeeee;color:#8f2f2f;border:1px solid #f2c4c4;border-radius:9px;padding:10px 14px;font-size:13px;margin-bottom:14px}
.ok{background:#e8f7ee;color:#16603a;border:1px solid #bfe6cf;border-radiusfc;border-radius:8px;padding:8px}
.err{background:#fdeeee;color:#8f2f2f;border:1px solid #f2c4c4;border-radius:9px;padding:10px 14px;font-size:13px;margin-bottom:14px}
.ok{background:#e8f7ee;color:#16603a;border:1px solid #bfe6cf;border-radius:9px;padding:10px 14px;font-size:13px;margin-bottom:14px}
.footer{text-align:center;color:var(--muted);font-size:12.5px;padding:26px 16px 40px}
.footer b{color:var(--navy)}
.pbar{height:9px;background:#e6eaf2;border-radius:6px;margin:10px 0 8px;overflow:hidden}
.pbar-fill{height:100%;border-radius:6px;transition:width .4s}
.subj-head{display:flex;align-items:center;gap:12px}
.subj-head .pct{font-size:22px;font-weight:800}
.adv{font-size:12.5px;padding:6px 10px;border-radius:8px;margin-bottom:10px}
.adv.good{background:#e4f6ec;color:#16603a}
.adv.bad{background:#fdeaea;color:#8f2f2f}
.adv.neutral{background:#eef1f6;color:#66748f}
details{font-size:13px;color:var(--muted)}
details summary{cursor:pointer;font-weight:600;color:var(--navy);padding:4px 0}
.passwrap{position:relative}
.passwrap .eye{position:absolute;right:10px;top:50%;transform:translateY(-50%);cursor:pointer;color:var(--muted);font-size:13px;user-select:none;background:none;border:none}
.student-list label{display:flex;gap:8px;align-items:center;font-weight:400;color:var(--text);cursor:pointer;padding:4px 0}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--muted)}
.small-note{font-size:12px;color:var(--muted)}
@media print{.topbar,.btn-row,.no-print{display:none!important}body{background:#fff}.card{box-shadow:none;border:none;padding:0}}
@media(max-width:600px){.wrap{padding:0 10px;margin:14px auto}.topbar .t2{display:none}.banner .big{font-size:17px}}
"""

# ---------------------------------------------------------------- pages -----
def page(title, body, nav=None, student=None, admin=False, extra_head=''):
    if nav is None:
        nav = ''
    elif student:
        nav = ('<div class="tabs">'
               '<a class="tab on" href="/student">Dashboard</a>'
               '<a class="tab" href="/student/sync">🔄 Sync Official</a>'
               '<a class="tab" href="/student/history">Attendance History</a>'
               '<a class="tab" href="/student/password">Change Password</a></div>')
    elif admin:
        nav = ('<div class="tabs">'
               '<a class="tab %s" href="/admin">Home</a>'
               '<a class="tab %s" href="/admin/attendance">Mark Attendance</a>'
               '<a class="tab %s" href="/admin/students">Students</a>'
               '<a class="tab %s" href="/admin/subjects">Subjects</a>'
               '<a class="tab %s" href="/admin/reports">Reports</a>'
               '<a class="tab %s" href="/admin/selfmark">Self-Mark</a>'
               '<a class="tab %s" href="/admin/import">Import Data</a>'
               '<a class="tab %s" href="/admin/settings">Settings</a></div>'
               % (admin, admin, admin, admin, admin, admin, admin, admin))
    return ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>%s | JNTUACEA – Academic Record Book</title><link rel="icon" href="/static/logo.png">%s'
            '<style>%s</style></head><body>%s<div class="wrap">%s%s</div>'
            '<div class="footer">%s · Student Academic Record Book · '
            '<b>Online Attendance System</b></div></body></html>'
            % (esc(title), extra_head, CSS, nav, body,
               '', esc(COLLEGE)))


def topbar(student=None, admin=False, label=''):
    if student:
        return ('<div class="topbar"><img src="/static/logo.png" alt="logo">'
                '<div><div class="t1">%s</div><div class="t2">Student Academic Record Book</div></div>'
                '<div class="spacer"></div><span class="user">🎓 %s · %s %s · %s</span>'
                '<a class="logout" href="/logout">Logout</a></div>'
                % (COLLEGE_SHORT, esc(student['name']), esc(student['roll']),
                   year_label(student['year']), esc(student['branch'])))
    if admin:
        return ('<div class="topbar"><img src="/static/logo.png" alt="logo">'
                '<div><div class="t1">%s</div><div class="t2">Admin Control Panel</div></div>'
                '<div class="spacer"></div><span class="user">👑 Administrator</span>'
                '<a class="logout" href="/logout">Logout</a></div>' % COLLEGE_SHORT)
    return ''


def page_login(err='', ok='', admin=False):
    act = '/login?admin=1' if admin else '/login'
    body = ('<div class="login-wrap"><div class="login-card">'
            '<div class="brand"><img src="/static/logo.png" alt="%s">'
            '<div class="bt">%s</div>'
            '<div class="bs">Student Academic Record Book</div>'
            '<div class="bl">Accredited by NAAC with "A" Grade</div></div>'
            '<div class="tabs" style="margin-bottom:18px">'
            '<a class="tab %s" href="/login">Student Login</a>'
            '<a class="tab %s" href="/login?admin=1">Admin Login</a></div>'
            % (esc(COLLEGE_SHORT), esc(COLLEGE),
               '' if not admin else 'on', 'on' if admin else ''))
    if err:
        body += '<div class="err">%s</div>' % esc(err)
    if ok:
        body += '<div class="ok">%s</div>' % esc(ok)
    body += ('<form method="post" action="%s">'
             '<div class="field"><label>%s</label><input name="roll" required '
             'placeholder="%s" autocomplete="username"></div>'
             '<div class="field"><label>%s</label><div class="passwrap">'
             '<input type="password" name="password" id="pw" required '
             'placeholder="••••••••" autocomplete="current-password">'
             '<button type="button" class="eye" onclick="togglePw()">👁</button></div></div>'
             '<button class="btn login-btn">Login</button></form>'
             '<div class="hint">%s</div>'
             '<div style="text-align:center;margin-top:16px;display:grid;gap:8px">'
             '<a href="https://jntuaceastudents.classattendance.in/" target="_blank" rel="noopener" '
             'style="font-size:12.5px;color:#66748f">🔗 Official College Portal (jntuaceastudents.classattendance.in) ↗</a>'
             '</div></div></div>'
             % (act,
                'Admin Username' if admin else 'Roll Number',
                'e.g. 22A51A0501' if not admin else 'admin',
                'Password',
                'Login: Roll Number + Roll Number (first time) or DOB (DDMMYYYY). '
                'New students get their account created automatically.'
                if not admin else 'Default admin password: admin123'))
    return page('Login', topbar() + body, nav='')


# ------------------------------------------------------------ student pages --
def norm_key(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def parse_summary_text(txt):
    """Parse student-entered subject totals. Supported line formats:
      'Operating Systems 36/40'
      'Operating Systems total 40 present 36'
      'Operating Systems 40 36'   (total then present)
    Returns [{'name':..., 'total':int, 'present':int}]"""
    rows = []
    for line in (txt or '').splitlines():
        line = line.strip()
        if not line:
            continue
        present = total = None
        m = re.search(r'(\d{1,3})\s*/\s*(\d{1,3})', line)
        if m:
            present, total = int(m.group(1)), int(m.group(2))
        else:
            low = line.lower()
            mt = re.search(r'total\s*[=:]?\s*(\d{1,3})', low)
            mp = re.search(r'present\s*[=:]?\s*(\d{1,3})', low)
            if mt and mp:
                total, present = int(mt.group(1)), int(mp.group(1))
            else:
                nums = re.findall(r'\d{1,3}', line)
                if len(nums) >= 2:
                    total, present = int(nums[-2]), int(nums[-1])
        if total is None or present is None:
            continue
        # clean the subject name: drop the numbers/keywords from the end
        name = re.sub(r'\d{1,3}\s*/\s*\d{1,3}', ' ', line)
        name = re.sub(r'(?i)total\s*[=:]?\s*\d{1,3}', ' ', name)
        name = re.sub(r'(?i)present\s*[=:]?\s*\d{1,3}', ' ', name)
        name = re.sub(r'\d{1,3}', ' ', name)
        name = name.strip(' :;,-.|')
        if not name or len(name) < 2 or not (1 <= present <= total <= 600):
            continue
        rows.append({'name': name.strip(), 'total': total, 'present': present})
    return rows


def skip_advice(p, t):
    """75% rule advice for a subject."""
    if t == 0:
        return 'neutral', 'No classes recorded yet.'
    pct = p * 100.0 / t
    if pct >= 75:
        can_skip = (4 * p - 3 * t) // 3
        if can_skip > 0:
            return 'good', 'You can skip up to <b>%d</b> more classes and still stay above 75%%.' % can_skip
        return 'good', 'You are safely above 75%.'
    need = max(1, 3 * t - 4 * p)
    return 'bad', 'Attend the next <b>%d</b> classes to get back above 75%%.' % need


def page_student_dash(st, msg=''):
    subs = student_subs(st['roll'])
    overall = subject_stats(st['roll'])
    summ = {r['key']: r for r in qall("SELECT * FROM att_summary WHERE roll=?", (st['roll'],))}

    def subj_totals(s):
        """Returns (present, total, source) — summary wins over records."""
        row = summ.get(norm_key(s['name']))
        if row:
            return row['present'], row['total'], 'summary'
        stt = subject_stats(st['roll'], s['id'])
        return stt['p'], stt['t'], 'records'

    cards = ''
    for s in subs:
        p, t, src = subj_totals(s)
        pct = (p * 100.0 / t) if t else 0.0
        cls, adv = skip_advice(p, t)
        if src == 'summary':
            src_tag = '<span class="badge b-p">Official portal</span>'
            det_rows = ('<tr><td colspan="2" class="sub">Entered from the official portal '
                        '(total %d, present %d).</td></tr>' % (t, p))
        else:
            src_tag = ''
            recs = qall("SELECT date, status FROM attendance WHERE roll=? AND subject_id=? "
                        "ORDER BY date DESC LIMIT 12", (st['roll'], s['id']))
            det_rows = ''.join(
                '<tr><td>%s</td><td>%s</td></tr>' % (fmt_date(r['date']), status_badge(r['status']))
                for r in recs) or '<tr><td colspan="2" class="sub">No records yet.</td></tr>'
        cards += (
            '<div class="card"><div class="subj-head">'
            '<div class="info"><div class="nm">%s %s</div>'
            '<div class="code">%s · %d of %d classes · Absent: %d</div></div>'
            '<div class="pct" style="color:%s">%.1f%%</div></div>'
            '<div class="pbar"><div class="pbar-fill" style="width:%.1f%%;background:%s"></div></div>'
            '<div class="adv %s">%s</div>'
            '<details><summary>📋 Details</summary>'
            '<table style="margin-top:8px"><tr><th>Date</th><th>Status</th></tr>%s</table></details>'
            '</div>'
            % (esc(s['name']), src_tag, esc(s['code']), p, t, max(0, t - p),
               pct_color(pct), pct, min(100, pct), pct_color(pct),
               cls, adv, det_rows))
    # subjects the student entered that are not in our subject list
    for key, row in summ.items():
        if any(norm_key(s['name']) == key for s in subs):
            continue
        p, t = int(row['present']), int(row['total'])
        pct = (p * 100.0 / t) if t else 0.0
        cls, adv = skip_advice(p, t)
        cards += (
            '<div class="card"><div class="subj-head">'
            '<div class="info"><div class="nm">%s <span class="badge b-p">Official portal</span></div>'
            '<div class="code">%d of %d classes · Absent: %d</div></div>'
            '<div class="pct" style="color:%s">%.1f%%</div></div>'
            '<div class="pbar"><div class="pbar-fill" style="width:%.1f%%;background:%s"></div></div>'
            '<div class="adv %s">%s</div></div>'
            % (esc(row['subject_name']), p, t, max(0, t - p),
               pct_color(pct), pct, min(100, pct), pct_color(pct), cls, adv))
    today = today_str()
    todays = qall("SELECT a.status, s.name, s.code FROM attendance a JOIN subjects s ON s.id=a.subject_id "
                  "WHERE a.roll=? AND a.date=? ORDER BY s.code", (st['roll'], today))
    trows = ''
    if todays:
        for t in todays:
            trows += '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (esc(t['code']), esc(t['name']), status_badge(t['status']))
    else:
        trows = '<tr><td colspan="3" class="sub">No classes marked today yet.</td></tr>'
    # self-mark open?
    sm_rows2 = qall("SELECT sm.subject_id, s.name, s.code, sm.open_until FROM selfmark sm "
                    "JOIN subjects s ON s.id=sm.subject_id "
                    "WHERE sm.enabled=1 AND sm.date=? AND s.branch=? AND s.year=? "
                    "AND (s.section='' OR s.section=?)", (today, st['branch'], st['year'], st['section']))
    sm_html = ''
    for sm in sm_rows2:
        cur = q1("SELECT status FROM attendance WHERE roll=? AND subject_id=? AND date=?",
                 (st['roll'], sm['subject_id'], today))
        if cur:
            sm_html += ('<div class="notice green">✔ <b>%s</b> (%s): today\'s attendance already marked — <b>%s</b>.</div>'
                        % (esc(sm['name']), esc(sm['code']), 'Present' if cur['status'] == 'P' else 'Absent'))
        else:
            till = (' till <b>%s</b>' % esc(sm['open_until'][11:16])) if sm['open_until'] else ''
            sm_html += ('<div class="notice">🕐 Self-attendance is open for <b>%s</b> (%s)%s.'
                        '<form method="post" action="/student/selfmark" style="margin-top:10px">'
                        '<input type="hidden" name="subject_id" value="%s">'
                        '<button class="btn green sm">Mark Myself Present</button></form></div>'
                        % (esc(sm['name']), esc(sm['code']), till, sm['subject_id']))
    if not sm_rows2:
        sm_html = ''
    # combined overall: summaries + records of subjects not covered by a summary
    if summ:
        com_p = sum(int(r['present']) for r in summ.values())
        com_t = sum(int(r['total']) for r in summ.values())
        for s in subs:
            if norm_key(s['name']) not in summ:
                stt = subject_stats(st['roll'], s['id'])
                com_p += stt['p']
                com_t += stt['t']
        overall = {'p': com_p, 't': com_t, 'a': max(0, com_t - com_p)}
    ovp = pct_of(overall)
    body = ('<div class="banner"><img src="/static/logo.png" alt="logo">'
            '<div><div class="big">%s</div>'
            '<div class="small">Roll Number: <b>%s</b> &nbsp;·&nbsp; %s %s &nbsp;·&nbsp; %s &nbsp;·&nbsp; Section %s</div></div>'
            '<div class="spacer"></div><div style="text-align:center"><div class="sub" style="color:#c9d6ec">Overall</div>%s</div></div>'
            % (esc(st['name']), esc(st['roll']), year_label(st['year']),
               esc(BRANCHES.get(st['branch'], st['branch'])),
               esc(COLLEGE_SHORT), esc(st['section']),
               ring(ovp, 100, 10).replace('#17305c', '#ffffff')))
    if summ:
        body += ('<div class="notice green">✅ Overall % is calculated from the totals you entered '
                 'from the official portal. Update them anytime on the '
                 '<a href="/student/sync"><b>Sync page</b></a>.</div>')
    if q1("SELECT password FROM students WHERE roll=?", (st['roll'],))['password'] == sha(st['roll']):
        body += ('<div class="notice">🔐 Your password is still your <b>Roll Number</b> (default). '
                 '<a href="/student/password"><b>Change it now</b></a> for safety.</div>')
    if st['name'].startswith('Student ') or not st['dob']:
        body += ('<div class="notice">👤 Please update your details — <a href="/student/profile">'
                 '<b>My Profile</b></a> — set your Name and DOB to enable DOB login.</div>')
    if msg:
        body += '<div class="ok">%s</div>' % esc(msg)
    body += sm_html
    # official portal sync card
    last_sync = q1("SELECT * FROM sync_log WHERE roll=? ORDER BY id DESC LIMIT 1", (st['roll'],))
    sync_info = ''
    if last_sync:
        ok_badge = '<span class="badge b-p">OK</span>' if last_sync['ok'] else '<span class="badge b-a">Failed</span>'
        sync_info = ('<div class="sub" style="margin-top:8px">Last sync: <b>%s</b> %s</div>'
                     % (esc(last_sync['at']), ok_badge))
    body += ('<div class="card" style="margin-bottom:16px"><h3><span class="bar"></span>🔗 Official Portal Sync</h3>'
             '<p class="sub">Bring your real attendance from the official portal '
             '(jntuaceastudents.classattendance.in). You log in yourself once (CAPTCHA is normal) '
             'and we pull your data — overall %% and subject-wise %%.</p>'
             '<div class="btn-row"><a class="btn green" href="/student/sync">🔗 Sync from Official Portal</a></div>'
             '%s</div>' % sync_info)
    body += ('<div class="grid g4" style="margin-bottom:16px">'
             '<div class="card stat"><div class="num" style="color:%s">%.1f%%</div><div class="lbl">Overall Attendance</div></div>'
             '<div class="card stat"><div class="num">%d</div><div class="lbl">Total Classes</div></div>'
             '<div class="card stat"><div class="num" style="color:var(--green)">%d</div><div class="lbl">Present</div></div>'
             '<div class="card stat"><div class="num" style="color:var(--red)">%d</div><div class="lbl">Absent</div></div></div>'
             % (pct_color(ovp), ovp, overall['t'], overall['p'], overall['a']))
    body += ('<div class="card" style="margin-bottom:16px"><h3><span class="bar"></span>Subject-wise Attendance</h3>'
             '<div class="grid">%s</div></div>' % cards)
    body += ('<div class="grid g2" style="margin-bottom:16px">'
             '<div class="card"><h3><span class="bar"></span>Today (%s)</h3><table><tr>'
             '<th>Code</th><th>Subject</th><th>Status</th></tr>%s</table></div>'
             '<div class="card"><h3><span class="bar"></span>Quick Links</h3>'
             '<div class="btn-row"><a class="btn outline" href="/student/history">📅 Full History</a>'
             '<a class="btn outline" href="/student/history?print=1">🖨 Print Report</a>'
             '<a class="btn outline" href="/student/profile">👤 My Profile</a>'
             '<a class="btn outline" href="/student/password">🔐 Change Password</a></div>'
             '<p class="sub" style="margin-top:12px">💡 <b>75%% rule:</b> you need at least 75%% attendance '
             'in each subject to be eligible for exams. Each subject card shows exactly how many classes '
             'you can skip or must attend.</p></div></div>'
             % (fmt_date(today), trows))
    return page('Dashboard', topbar(student=st) + body, student=st)


def page_student_history(st, subject_id=None, month=None, print_mode=False):
    subs = student_subs(st['roll'])
    cond, args = "a.roll=?", [st['roll']]
    if subject_id:
        cond += " AND a.subject_id=?"
        args.append(subject_id)
    if month:
        cond += " AND a.date LIKE ?"
        args.append(month + '%')
    rows = qall("SELECT a.date, a.status, s.name, s.code, a.marked_by FROM attendance a "
                "JOIN subjects s ON s.id=a.subject_id WHERE " + cond +
                " ORDER BY a.date DESC, s.code LIMIT 400", args)
    tr = ''
    for r in rows:
            tr += '<tr><td>%s <span class="sub">(%s)</span></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                fmt_date(r['date']), weekday_name(r['date']), esc(r['code']), esc(r['name']),
                status_badge(r['status']),
                {'self': 'Self', 'official': 'Official Portal', 'import': 'Imported'}.get(r['marked_by'], 'Admin'))
    subj_opts = ''.join('<option value="%s"%s>%s – %s</option>' % (s['id'], ' selected' if str(s['id']) == str(subject_id) else '', esc(s['code']), esc(s['name'])) for s in subs)
    month_opts = ''
    for i in range(5, -1, -1):
        m = (now_ist() - timedelta(days=30 * i)).strftime('%Y-%m')
        month_opts += '<option value="%s"%s>%s</option>' % (m, ' selected' if m == month else '',
                                                            datetime.strptime(m, '%Y-%m').strftime('%B %Y'))
    body = ('<div class="card no-print" style="margin-bottom:16px"><h3><span class="bar"></span>Filters</h3>'
            '<form class="form" method="get" action="/student/history"><div class="row">'
            '<div><label>Subject</label><select name="subject_id"><option value="">All Subjects</option>%s</select></div>'
            '<div><label>Month</label><select name="month"><option value="">All Months</option>%s</select></div>'
            '</div><div class="btn-row"><button class="btn sm">Apply</button>'
            '<a class="btn outline sm" href="/student/history">Clear</a>'
            '<a class="btn outline sm" href="/student/history?print=1%s%s">🖨 Print Report</a></div></form></div>'
            % (subj_opts, month_opts,
               ('&subject_id=' + str(subject_id)) if subject_id else '',
               ('&month=' + month) if month else ''))
    if print_mode:
        body += ('<div class="card"><h3><span class="bar"></span>Attendance Statement</h3>'
                 '<p class="sub">Name: <b>%s</b> &nbsp;·&nbsp; Roll No: <b>%s</b> &nbsp;·&nbsp; %s %s &nbsp;·&nbsp; %s</p>'
                 % (esc(st['name']), esc(st['roll']), year_label(st['year']),
                    BRANCHES.get(st['branch'], st['branch']), 'Section ' + esc(st['section'])))
    else:
        body += '<div class="card"><h3><span class="bar"></span>Attendance History</h3>'
    body += ('<table><tr><th>Date</th><th>Code</th><th>Subject</th><th>Status</th><th>Marked By</th></tr>'
             '%s</table><div class="btn-row no-print" style="margin-top:14px">'
             '<button class="btn sm" onclick="window.print()">🖨 Print</button></div></div>' % (tr or '<tr><td colspan="5" class="sub">No records found.</td></tr>'))
    return page('Attendance History', topbar(student=st) + body, student=st)


def page_student_sync(st, msg='', err=''):
    last = q1("SELECT * FROM sync_log WHERE roll=? ORDER BY id DESC LIMIT 1", (st['roll'],))
    body = ''
    if msg:
        body += '<div class="ok">%s</div>' % esc(msg)
    if err:
        body += '<div class="err">%s</div>' % esc(err)
    last_html = ''
    if last:
        state = '<span class="badge b-p">Success</span>' if last['ok'] else '<span class="badge b-a">Failed</span>'
        last_html = ('<div class="sub" style="margin-top:10px">Last sync: <b>%s</b> %s — %s</div>'
                     % (esc(last['at']), state, esc(last['message'])))
    body += ('<div class="card" style="max-width:620px"><h3><span class="bar"></span>✅ Way 1 — Enter your totals (works right now)</h3>'
             '<ol class="sub" style="padding-left:18px;display:grid;gap:5px;margin-bottom:12px">'
             '<li>Open the official portal: '
             '<a href="https://jntuaceastudents.classattendance.in/" target="_blank" rel="noopener">'
             '<b>jntuaceastudents.classattendance.in ↗</b></a> and log in.</li>'
             '<li>For each subject, note the <b>total classes</b> and <b>present</b> numbers.</li>'
             '<li>Type them below — one subject per line — and press Save.</li></ol>'
             '<form class="form" method="post" action="/student/summary">'
             '<textarea name="summary" rows="7" placeholder="Subject Name 36/40&#10;Operating Systems total 40 present 36&#10;DBMS 38 35"></textarea>'
             '<div class="btn-row"><button class="btn green">💾 Save — Update My Dashboard</button></div></form></div>')
    # Card 2 — automatic sync (works when the portal is not showing CAPTCHA)
    body += ('<div class="card" style="max-width:620px;margin-top:16px"><h3><span class="bar"></span>🔗 Way 2 — Automatic sync (when the portal allows)</h3>'
             '<p class="sub" style="margin-bottom:10px">The official portal currently shows a CAPTCHA to block '
             'automated logins, so you complete the login yourself: open the portal, log in there, '
             'then come back and pull. If the portal is not showing a CAPTCHA, the pull works fully automatically.</p>'
             '<div class="notice"><b>Step 1:</b> open the official portal and log in (CAPTCHA is normal). '
             '<b>Step 2:</b> come back here and click <b>Pull My Attendance</b>.</div>'
             '<div class="btn-row" style="margin-bottom:10px">'
             '<a class="btn" href="/bridge" target="_blank" rel="noopener">1️⃣ Open Official Portal</a>'
             '<form method="post" action="/student/pull" style="display:inline">'
             '<button class="btn green">2️⃣ Pull My Attendance</button></form></div>'
             '%s</div>' % last_html)
    # Card 3 — notes
    body += ('<div class="card" style="max-width:620px;margin-top:16px"><h3><span class="bar"></span>ℹ Notes</h3>'
             '<ul class="sub" style="padding-left:18px;display:grid;gap:6px">'
             '<li>Your dashboard shows <b>overall %</b> and <b>subject-wise %</b> with skip/attend advice '
             '(75% rule) — from the totals you enter or from a successful pull.</li>'
             '<li>We never store your official portal password.</li>'
             '<li>If you update the totals, your dashboard updates instantly.</li></ul></div>')
    return page('Sync', topbar(student=st) + body, student=st)


def page_student_profile(st, msg='', err=''):
    body = ''
    if msg:
        body += '<div class="ok">%s</div>' % esc(msg)
    if err:
        body += '<div class="err">%s</div>' % esc(err)
    body += ('<div class="card" style="max-width:560px"><h3><span class="bar"></span>My Profile</h3>'
             '<form class="form" method="post" action="/student/profile">'
             '<div><label>Full Name</label><input name="name" required value="%s"></div>'
             '<div><label>Date of Birth (optional — DOB tho login cheyadaniki)</label>'
             '<input type="date" name="dob" value="%s"></div>'
             '<div class="btn-row"><button class="btn">Save Profile</button></div></form></div>'
             % (esc(st['name']), esc(st['dob'])))
    return page('My Profile', topbar(student=st) + body, student=st)


def page_student_password(st, msg='', err=''):
    body = ''
    if msg:
        body += '<div class="ok">%s</div>' % esc(msg)
    if err:
        body += '<div class="err">%s</div>' % esc(err)
    body += ('<div class="card" style="max-width:520px"><h3><span class="bar"></span>Change Password</h3>'
             '<form class="form" method="post" action="/student/password">'
             '<div><label>Current Password</label><input type="password" name="old" required></div>'
             '<div><label>New Password (min 4 characters)</label><input type="password" name="new" minlength="4" required></div>'
             '<div><label>Confirm New Password</label><input type="password" name="confirm" minlength="4" required></div>'
             '<div class="btn-row"><button class="btn">Update Password</button></div></form></div>')
    return page('Change Password', topbar(student=st) + body, student=st)


# ------------------------------------------------------------- admin pages ---
def page_admin_dash():
    total_st = q1("SELECT COUNT(*) c FROM students")['c']
    total_su = q1("SELECT COUNT(*) c FROM subjects")['c']
    today = today_str()
    tod = q1("SELECT COUNT(*) t, SUM(CASE WHEN status='P' THEN 1 ELSE 0 END) p FROM attendance WHERE date=?", (today,))
    t = tod['t'] or 0
    p = tod['p'] or 0
    today_pct = (p * 100.0 / t) if t else 0
    week = q1("SELECT COUNT(*) t, SUM(CASE WHEN status='P' THEN 1 ELSE 0 END) p FROM attendance WHERE date>=?",
              ((now_ist() - timedelta(days=7)).strftime('%Y-%m-%d'),))
    wt, wp = week['t'] or 0, week['p'] or 0
    body = ('<div class="banner"><img src="/static/logo.png" alt="logo">'
            '<div><div class="big">Admin Control Panel</div>'
            '<div class="small">%s · %s</div></div></div>'
            % (esc(COLLEGE), fmt_date(today)))
    body += ('<div class="grid g4" style="margin-bottom:16px">'
             '<div class="card stat"><div class="num">%d</div><div class="lbl">Students</div></div>'
             '<div class="card stat"><div class="num">%d</div><div class="lbl">Subjects</div></div>'
             '<div class="card stat"><div class="num" style="color:%s">%.0f%%</div><div class="lbl">Today\'s Attendance</div></div>'
             '<div class="card stat"><div class="num" style="color:%s">%.0f%%</div><div class="lbl">7-Day Average</div></div></div>'
             % (total_st, total_su, pct_color(today_pct), today_pct, pct_color((wp * 100.0 / wt) if wt else 0),
                (wp * 100.0 / wt) if wt else 0))
    # today's per-subject summary
    srows = qall("SELECT s.code, s.name, s.branch, s.year, COUNT(*) t, "
                 "SUM(CASE WHEN a.status='P' THEN 1 ELSE 0 END) p FROM attendance a "
                 "JOIN subjects s ON s.id=a.subject_id WHERE a.date=? GROUP BY s.id ORDER BY s.branch,s.year,s.code",
                 (today,))
    tr = ''
    for r in srows:
        rp = (r['p'] * 100.0 / r['t']) if r['t'] else 0
        tr += ('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%d</td><td>%d</td>'
               '<td><span class="badge %s">%.0f%%</span></td></tr>'
               % (esc(r['code']), esc(r['name']), esc(r['branch']), year_label(r['year']),
                  r['p'], r['t'], 'b-p' if rp >= 75 else ('b-n' if rp >= 60 else 'b-a'), rp))
    body += ('<div class="card" style="margin-bottom:16px"><h3><span class="bar"></span>Today\'s Marking Summary</h3>'
             '<table><tr><th>Code</th><th>Subject</th><th>Branch</th><th>Year</th><th>Present</th><th>Total</th><th>%%</th></tr>'
             '%s</table></div>' % (tr or '<tr><td colspan="7" class="sub">No attendance marked today yet. '
                                          'Go to <a href="/admin/attendance"><b>Mark Attendance</b></a>.</td></tr>'))
    # below-threshold students
    low = qall("SELECT st.roll, st.name, st.branch, st.year, "
               "SUM(CASE WHEN a.status='P' THEN 1 ELSE 0 END) p, COUNT(*) t FROM attendance a "
               "JOIN students st ON st.roll=a.roll GROUP BY st.roll HAVING t>0 "
               "AND (SUM(CASE WHEN a.status='P' THEN 1 ELSE 0 END)*100.0/COUNT(*)) < 75 "
               "ORDER BY p*100.0/t LIMIT 12")
    ltr = ''
    for r in low:
        lp = (r['p'] * 100.0 / r['t'])
        ltr += ('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td><span class="badge b-a">%.0f%%</span></td></tr>'
                % (esc(r['roll']), esc(r['name']), esc(r['branch']), year_label(r['year']), lp))
    body += ('<div class="card" style="margin-bottom:16px"><h3><span class="bar"></span>⚠ Students Below 75%%</h3>'
             '<table><tr><th>Roll No</th><th>Name</th><th>Branch</th><th>Year</th><th>%%</th></tr>'
             '%s</table></div>' % (ltr or '<tr><td colspan="5" class="sub">No students below 75% — well done! 🎉</td></tr>'))
    body += ('<div class="grid g2"><div class="card"><h3><span class="bar"></span>Quick Actions</h3>'
             '<div class="btn-row"><a class="btn" href="/admin/attendance">✅ Mark Attendance</a>'
             '<a class="btn gold" href="/admin/students">👥 Add Students</a>'
             '<a class="btn outline" href="/admin/subjects">📚 Manage Subjects</a>'
             '<a class="btn outline" href="/admin/selfmark">🕐 Open Self-Mark</a>'
             '<a class="btn outline" href="/admin/reports">📊 Reports & CSV</a></div></div>'
             '<div class="card"><h3><span class="bar"></span>How it works</h3>'
             '<ol class="sub" style="padding-left:18px;display:grid;gap:6px">'
             '<li>Add students and subjects first (Students / Subjects tabs).</li>'
             '<li>Open <b>Mark Attendance</b>, pick subject &amp; date, tap Present/Absent, save.</li>'
             '<li>Students log in with <b>Roll Number</b> (password = roll number by default) and see their %.</li>'
             '<li>Use <b>Self-Mark</b> to let students mark themselves for a subject on a date.</li>'
             '<li>Use <b>Reports</b> to download CSV for defaulter lists.</li></ol></div></div>')
    return page('Admin', topbar(admin=True) + body, admin='on')


def page_admin_students(msg='', err=''):
    sts = qall("SELECT * FROM students ORDER BY branch, year, section, roll")
    tr = ''
    for s in sts:
        tr += ('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>Sec %s</td><td>'
               '<form method="post" action="/admin/students/delete" style="display:inline" '
               'onsubmit="return confirm(\'Delete student %s?\')">'
               '<input type="hidden" name="roll" value="%s"><button class="btn red sm">Delete</button></form></td></tr>'
               % (esc(s['roll']), esc(s['name']), esc(BRANCHES.get(s['branch'], s['branch'])),
                  year_label(s['year']), esc(s['section']), esc(s['name']), esc(s['roll'])))
    body = ''
    if msg:
        body += '<div class="ok">%s</div>' % esc(msg)
    if err:
        body += '<div class="err">%s</div>' % esc(err)
    body += ('<div class="grid g2" style="margin-bottom:16px">'
             '<div class="card"><h3><span class="bar"></span>Add Single Student</h3>'
             '<form class="form" method="post" action="/admin/students/add"><div>'
             '<label>Roll Number</label><input name="roll" required placeholder="e.g. 22A51A0501"></div>'
             '<div><label>Full Name</label><input name="name" required></div><div class="row">'
             '<div><label>Branch</label><select name="branch">'
             + ''.join('<option>%s</option>' % b for b in BRANCHES) +
             '</select></div><div><label>Year</label><select name="year">'
             '<option>1</option><option>2</option><option>3</option><option>4</option></select></div>'
             '<div><label>Section</label><select name="section"><option>A</option><option>B</option></select></div>'
             '<div><label>Date of Birth (optional)</label><input type="date" name="dob"></div></div>'
             '<div class="small-note">Default password = Roll Number or DOB. Student can change it after login.</div>'
             '<div><button class="btn">Add Student</button></div></form></div>'
             '<div class="card"><h3><span class="bar"></span>Bulk Add (CSV)</h3>'
             '<form class="form" method="post" action="/admin/students/bulk">'
             '<div><label>Paste CSV — one per line: <code>roll,name,branch,year,section,dob(optional)</code></label>'
             '<textarea name="csv" rows="7" placeholder="roll,name,branch,year,section,dob&#10;22A51A0501,Ravi Teja,CSE,2,A,2004-05-14&#10;22A51A0502,Sneha M,CSE,2,A,10-08-2004"></textarea></div>'
             '<div><button class="btn gold">Import Students</button></div></form></div></div>')
    body += ('<div class="card"><h3><span class="bar"></span>All Students (%d)</h3>'
             '<div style="margin-bottom:10px"><input placeholder="🔍 Search by name / roll…" '
             'onkeyup="var v=this.value.toLowerCase();document.querySelectorAll(\'#stbl tr\').forEach(r=>{r.style.display=r.innerText.toLowerCase().includes(v)?\'\':\'none\'})"></div>'
             '<table><thead><tr><th>Roll No</th><th>Name</th><th>Branch</th><th>Year</th><th>Section</th><th></th></tr></thead>'
             '<tbody id="stbl">%s</tbody></table></div>' % (len(sts), tr))
    return page('Students', topbar(admin=True) + body, admin='on')


def page_admin_subjects(msg='', err=''):
    subs = qall("SELECT * FROM subjects ORDER BY branch, year, code")
    tr = ''
    for s in subs:
        tr += ('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>'
               '<form method="post" action="/admin/subjects/delete" style="display:inline" '
               'onsubmit="return confirm(\'Delete subject %s?\')">'
               '<input type="hidden" name="id" value="%s"><button class="btn red sm">Delete</button></form></td></tr>'
               % (esc(s['code']), esc(s['name']), esc(s['branch']), year_label(s['year']),
                  ('All' if not s['section'] else 'Sec ' + s['section']), esc(s['name']), s['id']))
    body = ''
    if msg:
        body += '<div class="ok">%s</div>' % esc(msg)
    if err:
        body += '<div class="err">%s</div>' % esc(err)
    body += ('<div class="card" style="margin-bottom:16px"><h3><span class="bar"></span>Add Subject</h3>'
             '<form class="form" method="post" action="/admin/subjects/add"><div class="row">'
             '<div><label>Subject Code</label><input name="code" required placeholder="e.g. 19A05402"></div>'
             '<div><label>Subject Name</label><input name="name" required></div>'
             '<div><label>Branch</label><select name="branch">' + ''.join('<option>%s</option>' % b for b in BRANCHES) + '</select></div>'
             '<div><label>Year</label><select name="year"><option>1</option><option>2</option><option>3</option><option>4</option></select></div>'
             '<div><label>Section</label><select name="section"><option value="">All Sections</option><option>A</option><option>B</option></select></div>'
             '</div><div><button class="btn">Add Subject</button></div></form></div>')
    body += ('<div class="card"><h3><span class="bar"></span>All Subjects (%d)</h3>'
             '<table><tr><th>Code</th><th>Name</th><th>Branch</th><th>Year</th><th>Section</th><th></th></tr>%s</table></div>'
             % (len(subs), tr))
    return page('Subjects', topbar(admin=True) + body, admin='on')


def page_admin_reports(q):
    branch = q.get('branch', [''])[0]
    year = q.get('year', [''])[0]
    download = q.get('download', [''])[0]
    cond, args = '', []
    if branch:
        cond += " AND st.branch=?"
        args.append(branch)
    if year:
        cond += " AND st.year=?"
        args.append(year)
    rows = qall("SELECT st.roll, st.name, st.branch, st.year, st.section, "
                "SUM(CASE WHEN a.status='P' THEN 1 ELSE 0 END) p, "
                "SUM(CASE WHEN a.status='A' THEN 1 ELSE 0 END) a, COUNT(a.id) t "
                "FROM students st LEFT JOIN attendance a ON a.roll=st.roll WHERE 1=1" + cond +
                " GROUP BY st.roll ORDER BY st.branch, st.year, st.roll", args)
    sub_rows = qall("SELECT id, code, name FROM subjects ORDER BY branch,year,code")
    if download == 'csv':
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(['Roll No', 'Name', 'Branch', 'Year', 'Section', 'Present', 'Absent', 'Total', 'Overall %'])
        for r in rows:
            pct = (r['p'] * 100.0 / r['t']) if r['t'] else 0.0
            w.writerow([r['roll'], r['name'], r['branch'], r['year'], r['section'],
                        r['p'] or 0, r['a'] or 0, r['t'] or 0, '%.2f' % pct])
        return 200, out.getvalue(), 'text/csv; charset=utf-8', 'attendance_report.csv'
    tr = ''
    for r in rows:
        pct = (r['p'] * 100.0 / r['t']) if r['t'] else 0.0
        cls = 'b-p' if pct >= 75 else ('b-n' if pct >= 60 else 'b-a')
        tr += ('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
               '<td><span class="badge %s">%.1f%%</span></td></tr>'
               % (esc(r['roll']), esc(r['name']), esc(r['branch']), year_label(r['year']), esc(r['section']),
                  r['p'] or 0, r['a'] or 0, cls, pct))
    body = ('<div class="card" style="margin-bottom:16px"><h3><span class="bar"></span>Filters</h3>'
            '<form class="form" method="get" action="/admin/reports"><div class="row">'
            '<div><label>Branch</label><select name="branch"><option value="">All</option>'
            + ''.join('<option value="%s"%s>%s</option>' % (b, ' selected' if b == branch else '', b) for b in BRANCHES) +
            '</select></div><div><label>Year</label><select name="year"><option value="">All</option>'
            + ''.join('<option value="%d"%s>%s</option>' % (y, ' selected' if str(y) == year else '', year_label(y)) for y in range(1, 5)) +
            '</select></div></div><div class="btn-row"><button class="btn sm">Apply</button>'
            '<a class="btn outline sm" href="/admin/reports">Clear</a>'
            '<a class="btn green sm" href="/admin/reports?download=csv%s%s">⬇ Download CSV</a></div></form></div>'
            % (('&branch=' + branch) if branch else '', ('&year=' + year) if year else ''))
    body += ('<div class="card"><h3><span class="bar"></span>Consolidated Report (%d students)</h3>'
             '<table><tr><th>Roll No</th><th>Name</th><th>Branch</th><th>Year</th><th>Sec</th><th>Present</th>'
             '<th>Absent</th><th>Overall %%</th></tr>%s</table></div>' % (len(rows), tr))
    body += '<div class="small-note" style="margin-top:10px">Tip: The CSV opens in Excel / Google Sheets — use it to make defaulter lists.</div>'
    return 200, page('Reports', topbar(admin=True) + body, admin='on'), 'text/html; charset=utf-8', None


def page_admin_selfmark(msg='', err=''):
    subjects = qall("SELECT * FROM subjects ORDER BY branch, year, code")
    active = qall("SELECT sm.*, s.code, s.name, s.branch, s.year FROM selfmark sm "
                  "JOIN subjects s ON s.id=sm.subject_id ORDER BY sm.date DESC, s.code LIMIT 20")
    tr = ''
    for r in active:
        till = (' till ' + r['open_until'][11:16]) if r['open_until'] else ' all day'
        state = '<span class="badge b-p">Open</span>' if r['enabled'] else '<span class="badge b-n">Closed</span>'
        tr += ('<tr><td>%s %s</td><td>%s</td><td>%s · %s</td><td>%s%s</td><td>%s</td><td>'
               '<form method="post" action="/admin/selfmark/toggle" style="display:inline">'
               '<input type="hidden" name="id" value="%s"><input type="hidden" name="enabled" value="%s">'
               '<button class="btn %s sm">%s</button></form></td></tr>'
              % (fmt_date(r['date']), esc(r['code']), esc(r['name']), esc(r['branch']), year_label(r['year']),
                 'Open', till, state, r['id'], 0 if r['enabled'] else 1,
                 'red' if r['enabled'] else 'green', 'Close' if r['enabled'] else 'Open'))
    body = ''
    if msg:
        body += '<div class="ok">%s</div>' % esc(msg)
    if err:
        body += '<div class="err">%s</div>' % esc(err)
    body += ('<div class="card" style="margin-bottom:16px"><h3><span class="bar"></span>Open Self-Marking Window</h3>'
             '<p class="sub" style="margin-bottom:12px">Students of the subject\'s branch/year can mark themselves '
             '<b>Present</b> on their dashboard until the window closes.</p>'
             '<form class="form" method="post" action="/admin/selfmark"><div class="row">'
             '<div><label>Subject</label><select name="subject_id" required><option value="">-- Select --</option>'
             + ''.join('<option value="%s">%s · %s · %s · %s</option>'
                       % (s['id'], esc(s['code']), esc(s['name']), esc(s['branch']), year_label(s['year'])) for s in subjects) +
             '</select></div>'
             '<div><label>Date</label><input type="date" name="date" required value="%s"></div>'
             '<div><label>Close at (leave empty = whole day)</label><input type="time" name="open_until"></div>'
             '</div><div><button class="btn">Open Window</button></div></form></div>' % today_str())
    body += ('<div class="card"><h3><span class="bar"></span>Recent Self-Mark Windows</h3>'
             '<table><tr><th>Date</th><th>Subject</th><th>Class</th><th>Window</th><th>State</th><th></th></tr>'
             '%s</table></div>' % (tr or '<tr><td colspan="6" class="sub">No self-mark windows yet.</td></tr>'))
    return page('Self-Mark', topbar(admin=True) + body, admin='on')


def page_admin_import(msg='', err=''):
    body = ''
    if msg:
        body += '<div class="ok">%s</div>' % esc(msg)
    if err:
        body += '<div class="err">%s</div>' % esc(err)
    body += ('<div class="card" style="margin-bottom:16px"><h3><span class="bar"></span>📥 Import Students (same as official portal list)</h3>'
             '<p class="sub" style="margin-bottom:10px">Import students exactly from the official college list. '
             '<b>Header line is fine — it is detected automatically.</b> Columns (any order, header names flexible): '
             '<code>roll</code>, <code>name</code>, <code>branch</code> (CSE/ECE/EEE/ME/CE), <code>year</code> (1-4), '
             '<code>section</code> (A/B), <code>dob</code> (optional). Default password = Roll Number or DOB.</p>'
             '<form class="form" method="post" action="/admin/students/bulk">'
             '<textarea name="csv" rows="8" placeholder="Roll No,Name,Branch,Year,Section,DOB&#10;22A51A0501,Abhishek Reddy,CSE,2,A,01-01-2003&#10;22A51A0502,Akhila S,CSE,2,A,14-08-2004"></textarea>'
             '<div><button class="btn gold">⬆ Import Students</button></div></form></div>')
    body += ('<div class="card"><h3><span class="bar"></span>📥 Import Attendance (same as official portal record)</h3>'
             '<p class="sub" style="margin-bottom:10px">Paste attendance data exported from the official portal. '
             '<b>Header line ok.</b> Columns (any order): <code>roll</code>, <code>subject</code> (code or name), '
             '<code>date</code>, <code>status</code> (P/A/Present/Absent/1/0). '
             'Existing records are updated (not duplicated — latest value is saved).</p>'
             '<form class="form" method="post" action="/admin/attendance/import">'
             '<textarea name="csv" rows="8" placeholder="roll,subject,date,status&#10;22A51A0501,19A05402,18-08-2026,P&#10;22A51A0502,19A05402,18-08-2026,A"></textarea>'
             '<div class="small-note">💡 If you have the data in Excel/Sheets: copy the attendance data and paste it here. '
             'If the official portal has no export, get the list from the college office.</div>'
             '<div><button class="btn green">⬆ Import Attendance</button></div></form></div>')
    body += ('<div class="card" style="margin-top:16px"><h3><span class="bar"></span>ℹ How to get Official Portal data?</h3>'
             '<ol class="sub" style="padding-left:18px;display:grid;gap:6px">'
             '<li>Ask the <b>college office / exam cell</b> for the students list (roll + name + DOB) '
             'and attendance registers — they usually provide them in Excel.</li>'
             '<li>If your college has <b>classattendance.in admin access</b>, that portal also has a '
             'reports/export option — you can use it.</li>'
             '<li>After importing here, our app shows the <b>same students, same DOB login, '
             'same attendance %</b>.</li></ol></div>')
    return page('Import Data', topbar(admin=True) + body, admin='on')


def page_admin_settings(msg='', err=''):
    body = ''
    if msg:
        body += '<div class="ok">%s</div>' % esc(msg)
    if err:
        body += '<div class="err">%s</div>' % esc(err)
    body += ('<div class="card" style="max-width:520px;margin-bottom:16px"><h3><span class="bar"></span>Change Admin Password</h3>'
             '<form class="form" method="post" action="/admin/password">'
             '<div><label>Current Password</label><input type="password" name="old" required></div>'
             '<div><label>New Password (min 4 characters)</label><input type="password" name="new" minlength="4" required></div>'
             '<div><label>Confirm New Password</label><input type="password" name="confirm" minlength="4" required></div>'
             '<div><button class="btn">Update Password</button></div></form></div>')
    body += ('<div class="card" style="max-width:520px"><h3><span class="bar"></span>Demo Data</h3>'
             '<p class="sub" style="margin-bottom:10px">The app ships with sample students, subjects and '
             '2 months of attendance so you can explore. When you are ready for real data:</p>'
             '<form method="post" action="/admin/reset" onsubmit="return confirm(\'This deletes ALL students, subjects and attendance records. Continue?\')">'
             '<button class="btn red">🗑 Erase All Demo Data</button></form></div>')
    return page('Settings', topbar(admin=True) + body, admin='on')


LOGO_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">
<circle cx="200" cy="200" r="192" fill="#ffffff" stroke="#f0b429" stroke-width="10"/>
<circle cx="200" cy="200" r="160" fill="none" stroke="#123a6b" stroke-width="3"/>
<path d="M200 96 A104 104 0 0 1 304 200" fill="none" stroke="#123a6b" stroke-width="16" stroke-linecap="round"/>
<text x="200" y="150" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="34" font-weight="bold" fill="#123a6b">JNTUACEA</text>
<path d="M200 232 A104 104 0 0 0 96 200" fill="none" stroke="#f0b429" stroke-width="16" stroke-linecap="round"/>
<text x="200" y="252" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="24" font-weight="bold" fill="#f0b429">ANANTAPURAMU</text>
<path d="M176 300 q0 -44 24 -52 q24 -8 24 20 l0 18 q0 44 -24 52 q-24 8 -24 -20 z" fill="#123a6b"/>
<path d="M200 284 l0 62" stroke="#123a6b" stroke-width="10"/>
<path d="M186 330 l28 0" stroke="#123a6b" stroke-width="8"/>
<path d="M164 252 l34 -34 M200 258 l34 -34" stroke="#123a6b" stroke-width="6" stroke-linecap="round"/>
<circle cx="200" cy="180" r="14" fill="#f0b429"/>
<circle cx="200" cy="180" r="26" fill="none" stroke="#f0b429" stroke-width="4"/>
</svg>'''


# ---------------------------------------------------------------- handler ---
class App(BaseHTTPRequestHandler):
    server_version = 'JNTUACEA-Portal/1.0'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    # ----- plumbing
    def send(self, status, body, ctype='text/html; charset=utf-8', extra_headers=None, filename=None):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="%s"' % filename)
        if extra_headers:
            for k, v in extra_headers:
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def redir(self, loc):
        self.send(303, '', extra_headers=[('Location', loc)])

    def qs(self):
        return parse_qs(urlparse(self.path).query)

    def post_fields(self):
        ln = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(ln).decode('utf-8', 'replace')
        return parse_qs(raw, keep_blank_values=True)

    def field(self, f, name, default=''):
        v = f.get(name, [''])
        return v[0].strip() if v else default

    def session(self):
        ck = SimpleCookie(self.headers.get('Cookie', ''))
        tok = ck.get('sid')
        if not tok:
            return None
        return q1("SELECT * FROM sessions WHERE token=?", (tok.value,))

    def flash(self):
        ck = SimpleCookie(self.headers.get('Cookie', ''))
        f = ck.get('flash')
        return unquote(f.value) if f else ''

    def new_session(self, role, roll=''):
        tok = secrets.token_urlsafe(32)
        run("INSERT INTO sessions(token,role,roll,created) VALUES(?,?,?,?)",
            (tok, role, roll, now_ist().isoformat(timespec='seconds')))
        return tok

    def set_cookie(self, tok):
        return [('Set-Cookie', 'sid=%s; Path=/; HttpOnly; SameSite=Lax' % tok)]

    # ----- bridge: reverse-proxy the official portal through our app.
    # The student opens the official login page on OUR domain and logs in
    # THEMSELVES — so the CAPTCHA is solved by a real human in a real
    # browser. After login, our server uses their session cookies to read
    # their attendance (no CAPTCHA is needed after login).
    def bridge(self, method):
        try:
            import requests as _rq
        except ImportError:
            return self.send(502, 'Bridge engine not installed. Run: pip install -r requirements.txt', 'text/html')
        parsed = urlparse(self.path)
        rel = parsed.path[len('/bridge'):]
        if not rel:
            rel = '/'
        target = PORTAL_URL + rel + ('?' + parsed.query if parsed.query else '')
        hdrs = {}
        incoming_cookie = ''
        for k, v in self.headers.items():
            lk = k.lower()
            if lk in ('host', 'content-length', 'connection', 'accept-encoding',
                      'transfer-encoding', 'upgrade-insecure-requests', 'sec-fetch-dest'):
                continue
            if lk == 'cookie':
                incoming_cookie = v
                parts = [p.strip() for p in v.split(';')]
                parts = [p for p in parts if p and not p.lower().startswith(('sid=', 'flash='))]
                if parts:
                    hdrs['Cookie'] = '; '.join(parts)
                continue
            if lk == 'referer':
                our_host = self.headers.get('Host', '')
                if our_host:
                    v = re.sub(r'https?://' + re.escape(our_host), PORTAL_URL, v, flags=re.I)
                hdrs[k] = v
                continue
            if lk == 'origin':
                hdrs[k] = PORTAL_URL
                continue
            hdrs[k] = v
        hdrs['Host'] = urlparse(PORTAL_URL).netloc
        ua = hdrs.get('User-Agent', '')
        if not ua or 'curl' in ua.lower() or 'python' in ua.lower():
            hdrs['User-Agent'] = BRIDGE_UA
        hdrs['Accept-Encoding'] = 'identity'
        body = None
        if method == 'POST':
            ln = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(ln)
        try:
            resp = _rq.request(method, target, headers=hdrs, data=body, timeout=40,
                               allow_redirects=False)
        except Exception as e:
            return self.send(502, 'Official portal is unreachable right now (%s). '
                                  'Please try again in a minute.' % esc(str(e)[:80]), 'text/html')
        # remember the portal session cookies so we can pull attendance later
        sess = self.session()
        if sess and sess['role'] == 'student' and incoming_cookie:
            run("INSERT INTO bridge_cookies(token,cookies,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(token) DO UPDATE SET cookies=excluded.cookies, updated_at=excluded.updated_at",
                (sess['token'], incoming_cookie, now_ist().isoformat(timespec='seconds')))
        out = []
        ctype = resp.headers.get('Content-Type', 'text/html; charset=utf-8')
        for k, v in resp.headers.items():
            lk = k.lower()
            if lk in ('content-length', 'connection', 'transfer-encoding',
                      'content-encoding', 'keep-alive', 'alt-svc'):
                continue
            if lk == 'location':
                v = re.sub(r'https?://[^/]*jntuaceastudents\.classattendance\.in',
                           '/bridge', v, flags=re.I)
            elif lk == 'set-cookie':
                v = re.sub(r';\s*domain=[^;]*', '', v, flags=re.I)
                v = re.sub(r';\s*secure', '', v, flags=re.I)
            out.append((k, v))
        content = resp.content
        if 'html' in ctype.lower() or ctype.lower().startswith('text/'):
            text = content.decode(resp.encoding or 'utf-8', 'replace')
            text = re.sub(r'https?://jntuaceastudents\.classattendance\.in',
                          '/bridge', text, flags=re.I)
            banner = ('<div style="position:sticky;top:0;z-index:9999;background:#123a6b;'
                      'color:#fff;padding:8px 14px;font:600 13px/1.5 Segoe UI,Arial,sans-serif">'
                      '🔗 JNTUACEA Sync Bridge — this is the official portal. Log in here '
                      '(the CAPTCHA is normal), then come back to the '
                      '<a href="/student/sync" style="color:#ffd75e;font-weight:700">Sync tab</a> '
                      'and click <b>Pull My Attendance</b>.</div>')
            if '<body' in text:
                text = re.sub(r'(<body[^>]*>)', lambda m: m.group(1) + banner, text, count=1)
            else:
                text = banner + text
            content = text.encode('utf-8')
        self.send(resp.status_code, content, ctype, extra_headers=out)

    def serve_static(self, path):
        fname = os.path.basename(path)
        full = os.path.join(BASE, 'static', fname)
        if os.path.isfile(full):
            with open(full, 'rb') as f:
                data = f.read()
            ctype = 'image/png' if fname.endswith('.png') else ('image/svg+xml' if fname.endswith('.svg') else 'application/octet-stream')
            self.send(200, data, ctype, extra_headers=[('Cache-Control', 'max-age=86400')])
            return
        # Fallback: built-in SVG emblem if the PNG was not uploaded
        if fname == 'logo.png':
            svg = LOGO_SVG.encode('utf-8')
            self.send(200, svg, 'image/svg+xml', extra_headers=[('Cache-Control', 'max-age=86400')])
            return
        self.send(404, 'not found', 'text/plain')

    # ----- routing
    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith('/static/'):
            return self.serve_static(path)
        # ---- bridge: official portal through our app (student solves CAPTCHA)
        if path == '/bridge' or path.startswith('/bridge/'):
            return self.bridge('GET')
        # ---- easy downloads (for phone setup)
        if path == '/download':
            return self.send(200, page('Downloads', topbar() + (
                '<div class="card"><h3><span class="bar"></span>Setup Files</h3>'
                '<p class="sub" style="margin-bottom:14px">GitHub / Render lo pettadaniki kaavalsina files — '
                'phone lo download chesukondi:</p>'
                '<div class="btn-row">'
                '<a class="btn" href="/download/app.py" download>⬇ app.py (website)</a>'
                '<a class="btn outline" href="/download/logo.png" download>⬇ logo.png (optional)</a>'
                '</div></div>'), nav=''))
        if path == '/download/app.py':
            with open(os.path.join(BASE, 'app.py'), 'rb') as f:
                return self.send(200, f.read(), 'application/octet-stream', filename='app.py')
        if path == '/download/logo.png':
            full = os.path.join(BASE, 'static', 'logo.png')
            if os.path.isfile(full):
                with open(full, 'rb') as f:
                    return self.send(200, f.read(), 'image/png', filename='logo.png')
            return self.send(200, LOGO_SVG.encode('utf-8'), 'image/svg+xml', filename='logo.svg')
        sess = self.session()
        if path in ('/', '/index'):
            return self.redir('/student' if sess and sess['role'] == 'student' else
                              ('/admin' if sess and sess['role'] == 'admin' else '/login'))
        if path == '/login':
            admin = self.qs().get('admin') is not None
            return self.send(200, page_login(admin=admin))
        if path == '/logout':
            if sess:
                run("DELETE FROM sessions WHERE token=?", (sess['token'],))
            self.send(200, page_login(ok='You have been logged out.'),
                      extra_headers=[('Set-Cookie', 'sid=; Path=/; Max-Age=0; HttpOnly')])
            return
        if path == '/health':
            return self.send(200, 'ok', 'text/plain')
        # ---- student zone
        if sess and sess['role'] == 'student':
            st = q1("SELECT * FROM students WHERE roll=?", (sess['roll'],))
            if not st:
                return self.redir('/logout')
            if path == '/student':
                return self.send(200, page_student_dash(st, msg=self.flash()))
            if path == '/student/history':
                q = self.qs()
                return self.send(200, page_student_history(
                    st, q.get('subject_id', [''])[0], q.get('month', [''])[0],
                    print_mode=q.get('print') is not None))
            if path == '/student/password':
                return self.send(200, page_student_password(st))
            if path == '/student/sync':
                return self.send(200, page_student_sync(st))
            if path == '/student/profile':
                return self.send(200, page_student_profile(st))
            return self.redir('/student')
        # ---- admin zone
        if sess and sess['role'] == 'admin':
            if path == '/admin':
                return self.send(200, page_admin_dash())
            if path == '/admin/attendance':
                q = self.qs()
                subject_id = q.get('subject_id', [''])[0]
                date_s = q.get('date', [today_str()])[0]
                return self.send(200, self.mark_page(subject_id, date_s))
            if path == '/admin/students':
                return self.send(200, page_admin_students())
            if path == '/admin/subjects':
                return self.send(200, page_admin_subjects())
            if path == '/admin/reports':
                st_, body_, ct_, fn_ = page_admin_reports(self.qs())
                return self.send(st_, body_, ct_, filename=fn_)
            if path == '/admin/selfmark':
                return self.send(200, page_admin_selfmark())
            if path == '/admin/import':
                return self.send(200, page_admin_import())
            if path == '/admin/settings':
                return self.send(200, page_admin_settings())
            return self.redir('/admin')
        if path.startswith('/admin') or path.startswith('/student'):
            return self.redir('/login')
        self.send(404, page_login(err='Page not found.'))

    def do_POST(self):
        path = urlparse(self.path).path
        # ---- bridge: official portal through our app (student solves CAPTCHA)
        if path == '/bridge' or path.startswith('/bridge/'):
            return self.bridge('POST')
        sess = self.session()
        f = self.post_fields()
        # ---- login
        if path == '/login':
            admin = self.qs().get('admin') is not None
            if admin:
                if self.field(f, 'roll') == 'admin' and sha(self.field(f, 'password')) == q1(
                        "SELECT value FROM settings WHERE key='admin_pass'")['value']:
                    tok = self.new_session('admin')
                    return self.redir_ck('/admin', tok)
                return self.send(200, page_login(err='Invalid admin username or password.', admin=True))
            roll = self.field(f, 'roll').upper().replace(' ', '')
            pw = self.field(f, 'password')
            st = q1("SELECT * FROM students WHERE roll=?", (roll,))
            if st and (sha(pw) == st['password'] or dob_matches(pw, st['dob'])):
                tok = self.new_session('student', roll)
                return self.redir_ck('/student', tok)
            # ---- Auto-register: JNTUA-style roll + password == roll number
            if not st and pw.upper() == roll and re.match(r'^[0-9]{2}[0-9]{3}[A-Za-z]', roll):
                branch, year = guess_from_roll(roll)
                run("INSERT INTO students(roll,name,branch,year,section,password,dob) "
                    "VALUES(?,?,?,?,'A',?,'')", (roll, 'Student ' + roll, branch, year, sha(roll)))
                tok = self.new_session('student', roll)
                return self.send(303, '', extra_headers=[('Location', '/student')]
                                 + self.set_cookie(tok)
                                 + [('Set-Cookie', 'flash=%s; Path=/; Max-Age=8; HttpOnly'
                                     % quote('Account auto-created successfully ✅ Please update your '
                                             'Name and DOB on the My Profile page.'))])
            # ---- Friend-app mode: direct official portal login (roll + official password)
            odata = None
            perr = ''
            try:
                import scraper
                odata = scraper.official_fetch(roll, pw, max_subjects=12, polite_delay=0.1)
            except ImportError:
                pass
            except scraper.PortalError as e:
                perr = str(e)
            except Exception:
                perr = 'Official portal check failed. Please try again.'
            if odata is not None:
                if not st:
                    run("INSERT INTO students(roll,name,branch,year,section,password,dob) VALUES(?,?,?,?,'A',?,'')",
                        (roll, odata.get('name') or roll, odata.get('branch') or 'CSE',
                         int(odata.get('year') or 2), sha(roll)))
                elif odata.get('name'):
                    run("UPDATE students SET name=? WHERE roll=?", (odata.get('name'), roll))
                subs, recs = apply_official_sync(roll, odata)
                run("INSERT INTO sync_log(roll,at,ok,message) VALUES(?,?,1,?)",
                    (roll, now_ist().isoformat(timespec='seconds'),
                     '%d subjects, %d records synced' % (subs, recs)))
                tok = self.new_session('student', roll)
                flash_h = ('Set-Cookie', 'flash=%s; Path=/; Max-Age=8; HttpOnly'
                           % quote('Logged in via official portal — %d subjects, %d records synced ✅'
                                   % (subs, recs)))
                return self.send(303, '', extra_headers=[('Location', '/student')]
                                 + self.set_cookie(tok) + [flash_h])
            if st:
                msg = 'Incorrect password. (Default: Roll Number or DOB in DDMMYYYY format.)'
                if perr:
                    msg += ' Official portal check: %s' % perr
                return self.send(200, page_login(err=msg))
            msg = ('Roll number not found. Log in with Roll Number + Roll Number — '
                   'your account will be created automatically ✅ (or ask the admin to add your account).')
            if perr:
                msg += ' Official portal check: %s' % perr
            return self.send(200, page_login(err=msg))
        # ---- auth guard
        if not sess:
            return self.redir('/login')
        if sess['role'] == 'student':
            st = q1("SELECT * FROM students WHERE roll=?", (sess['roll'],))
            if not st:
                return self.redir('/logout')
            if path == '/student/selfmark':
                subject_id = self.field(f, 'subject_id')
                sm = q1("SELECT * FROM selfmark WHERE subject_id=? AND date=? AND enabled=1",
                        (subject_id, today_str()))
                if not sm:
                    return self.redir('/student')
                subj = q1("SELECT * FROM subjects WHERE id=?", (subject_id,))
                if not subj or subj['branch'] != st['branch'] or subj['year'] != st['year'] \
                        or (subj['section'] and subj['section'] != st['section']):
                    return self.redir('/student')
                if sm['open_until']:
                    try:
                        close = datetime.strptime(today_str() + ' ' + sm['open_until'], '%Y-%m-%d %H:%M').replace(tzinfo=IST)
                        if now_ist() > close:
                            return self.redir('/student')
                    except Exception:
                        pass
                run("INSERT OR IGNORE INTO attendance(roll,subject_id,date,status,marked_by,marked_at) "
                    "VALUES(?,?,?,'P','self',?)", (st['roll'], subject_id, today_str(),
                                                   now_ist().isoformat(timespec='seconds')))
                subj_nm = q1("SELECT name FROM subjects WHERE id=?", (subject_id,))
                nm = subj_nm['name'] if subj_nm else 'class'
                self.send(303, '', extra_headers=[('Location', '/student'),
                                                  ('Set-Cookie', 'flash=%s; Path=/; Max-Age=6; HttpOnly'
                                                   % quote('You marked yourself PRESENT for %s.' % nm))])
                return
            if path == '/student/profile':
                name = self.field(f, 'name').strip()
                dob = self.field(f, 'dob').strip()
                if not name:
                    return self.send(200, page_student_profile(st, err='Name is required.'))
                run("UPDATE students SET name=?, dob=? WHERE roll=?", (name[:60], dob, st['roll']))
                return self.send(200, page_student_profile(st, msg='Profile updated successfully! ✅'))
            if path == '/student/password':
                old = self.field(f, 'old')
                new = self.field(f, 'new')
                confirm = self.field(f, 'confirm')
                if new != confirm:
                    return self.send(200, page_student_password(st, err='New passwords do not match.'))
                if len(new) < 4:
                    return self.send(200, page_student_password(st, err='Password must be at least 4 characters.'))
                if sha(old) != st['password']:
                    return self.send(200, page_student_password(st, err='Current password is incorrect.'))
                run("UPDATE students SET password=? WHERE roll=?", (sha(new), st['roll']))
                return self.send(200, page_student_password(st, msg='Password updated successfully!'))
            if path == '/student/summary':
                rows = parse_summary_text(self.field(f, 'summary'))
                if not rows:
                    return self.send(200, page_student_sync(
                        st, err='No valid lines found. Format per line: '
                                'Subject Name 36/40  (or)  Subject Name total 40 present 36'))
                run("DELETE FROM att_summary WHERE roll=?", (st['roll'],))
                for r in rows:
                    run("INSERT INTO att_summary(roll,key,subject_name,total,present,updated_at) "
                        "VALUES(?,?,?,?,?,?)",
                        (st['roll'], norm_key(r['name']), r['name'][:80], r['total'], r['present'],
                         now_ist().isoformat(timespec='seconds')))
                n = len(rows)
                self.send(303, '', extra_headers=[('Location', '/student'),
                                                  ('Set-Cookie', 'flash=%s; Path=/; Max-Age=8; HttpOnly'
                                                   % quote('Saved %d subject%s from the official portal ✅ '
                                                           'Your dashboard is updated.'
                                                           % (n, '' if n == 1 else 's')))])
                return
            if path == '/student/pull':
                # Bridge flow: use the portal session the student created in
                # their own browser (CAPTCHA solved by a real human there).
                brow = q1("SELECT cookies FROM bridge_cookies WHERE token=?", (sess['token'],))
                if not brow:
                    return self.send(200, page_student_sync(
                        st, err='No official portal session found. Do Step 1 first: '
                                'open the official portal and log in there.'))
                try:
                    import requests as _rq
                    import scraper
                except Exception:
                    return self.send(200, page_student_sync(st, err='Sync engine is not available on this server yet.'))
                s2 = _rq.Session()
                s2.headers.update({'User-Agent': scraper.UA,
                                   'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                                   'Accept-Language': 'en-US,en;q=0.9'})
                keep = [p.strip() for p in brow['cookies'].split(';')
                        if p.strip() and not p.strip().lower().startswith(('sid=', 'flash='))]
                if not keep:
                    return self.send(200, page_student_sync(
                        st, err='Official portal session cookie missing. Do Step 1 again '
                                '(open portal, log in), then pull.'))
                s2.headers['Cookie'] = '; '.join(keep)
                try:
                    data = scraper.official_fetch_session(s2, fallback_name=st['roll'],
                                                          max_subjects=15, polite_delay=0.2)
                except scraper.PortalError as e:
                    run("INSERT INTO sync_log(roll,at,ok,message) VALUES(?,?,0,?)",
                        (st['roll'], now_ist().isoformat(timespec='seconds'), str(e)[:200]))
                    return self.send(200, page_student_sync(st, err=str(e)))
                except Exception as e:
                    run("INSERT INTO sync_log(roll,at,ok,message) VALUES(?,?,0,?)",
                        (st['roll'], now_ist().isoformat(timespec='seconds'),
                         'Unexpected error: %s' % str(e)[:160]))
                    return self.send(200, page_student_sync(st, err='Pull failed. Please open the portal again (Step 1) and try.'))
                total_subs, total_recs = apply_official_sync(st['roll'], data)
                run("INSERT INTO sync_log(roll,at,ok,message) VALUES(?,?,1,?)",
                    (st['roll'], now_ist().isoformat(timespec='seconds'),
                     '%d subjects, %d records pulled' % (total_subs, total_recs)))
                self.send(303, '', extra_headers=[('Location', '/student'),
                                                  ('Set-Cookie', 'flash=%s; Path=/; Max-Age=8; HttpOnly'
                                                   % quote('Pulled from official portal: %d subjects, %d records ✅ '
                                                           'Check your Dashboard.' % (total_subs, total_recs)))])
                return
            if path == '/student/sync':
                pw = self.field(f, 'password')
                if not pw:
                    return self.send(200, page_student_sync(st, err='Please enter your official portal password.'))
                # throttle: max one sync per 30 minutes per student (gentle with the portal)
                last_ok = q1("SELECT at FROM sync_log WHERE roll=? AND ok=1 ORDER BY id DESC LIMIT 1",
                             (st['roll'],))
                if last_ok:
                    try:
                        last_dt = datetime.fromisoformat(last_ok['at'])
                        if (now_ist() - last_dt).total_seconds() < 30 * 60:
                            return self.send(200, page_student_sync(
                                st, err='Synced recently (%s). Please wait 30 minutes before syncing again — '
                                        'we handle the official portal gently.' % esc(last_ok['at'])))
                    except Exception:
                        pass
                try:
                    import scraper
                    data = scraper.official_fetch(st['roll'], pw)
                except ImportError:
                    run("INSERT INTO sync_log(roll,at,ok,message) VALUES(?,?,0,?)",
                        (st['roll'], now_ist().isoformat(timespec='seconds'),
                         'Sync engine not installed on this server yet.'))
                    return self.send(200, page_student_sync(st, err='Sync engine is not available on this server yet.'))
                except scraper.PortalError as e:
                    run("INSERT INTO sync_log(roll,at,ok,message) VALUES(?,?,0,?)",
                        (st['roll'], now_ist().isoformat(timespec='seconds'), str(e)[:200]))
                    return self.send(200, page_student_sync(st, err=str(e)))
                except Exception as e:
                    run("INSERT INTO sync_log(roll,at,ok,message) VALUES(?,?,0,?)",
                        (st['roll'], now_ist().isoformat(timespec='seconds'),
                         'Unexpected error: %s' % str(e)[:160]))
                    return self.send(200, page_student_sync(st, err='Sync failed. Please try again later.'))
                # store fetched records
                total_subs, total_recs = apply_official_sync(st['roll'], data)
                run("INSERT INTO sync_log(roll,at,ok,message) VALUES(?,?,1,?)",
                    (st['roll'], now_ist().isoformat(timespec='seconds'),
                     '%d subjects, %d records synced' % (total_subs, total_recs)))
                self.send(303, '', extra_headers=[('Location', '/student'),
                                                  ('Set-Cookie', 'flash=%s; Path=/; Max-Age=6; HttpOnly'
                                                   % quote('Synced from official portal: %d subjects, %d records ✅'
                                                           % (total_subs, total_recs)))])
                return
            return self.redir('/student')
        if sess['role'] == 'admin':
            if path == '/admin/attendance':
                subject_id = self.field(f, 'subject_id')
                date_s = self.field(f, 'date') or today_str()
                marks = {k[2:]: v[0] for k, v in f.items() if k.startswith('r_')}
                subj = q1("SELECT * FROM subjects WHERE id=?", (subject_id,))
                if not subj:
                    return self.send(200, self.mark_page('', date_s, err='Please select a subject.'))
                students = qall("SELECT roll FROM students WHERE branch=? AND year=? AND (section=? OR ?='')",
                                (subj['branch'], subj['year'], subj['section'], subj['section']))
                n = 0
                for srow in students:
                    v = marks.get(srow['roll'], '')
                    if v not in ('P', 'A'):
                        continue
                    run("INSERT INTO attendance(roll,subject_id,date,status,marked_by,marked_at) "
                        "VALUES(?,?,?,?, 'admin', ?) "
                        "ON CONFLICT(roll,subject_id,date) DO UPDATE SET status=excluded.status, marked_by='admin', marked_at=excluded.marked_at",
                        (srow['roll'], subject_id, date_s, v, now_ist().isoformat(timespec='seconds')))
                    n += 1
                return self.send(303, '', extra_headers=[
                    ('Location', '/admin/attendance?subject_id=%s&date=%s' % (subject_id, date_s)),
                    ('Set-Cookie', 'flash=%s; Path=/; Max-Age=6; HttpOnly'
                     % quote('Saved %d records for %s on %s' % (n, subj['code'], date_s)))])
            if path == '/admin/students/add':
                roll = self.field(f, 'roll').upper().replace(' ', '')
                name = self.field(f, 'name')
                branch = self.field(f, 'branch')
                year = self.field(f, 'year')
                section = self.field(f, 'section')
                dob = self.field(f, 'dob')
                if not roll or not name or branch not in BRANCHES:
                    return self.send(200, page_admin_students(err='Please fill all fields correctly.'))
                if not re.match(r'^[A-Z0-9]{5,20}$', roll):
                    return self.send(200, page_admin_students(err='Roll number format looks invalid.'))
                if q1("SELECT 1 FROM students WHERE roll=?", (roll,)):
                    return self.send(200, page_admin_students(err='Roll number %s already exists.' % roll))
                run("INSERT INTO students(roll,name,branch,year,section,password,dob) VALUES(?,?,?,?,?,?,?)",
                    (roll, name, branch, int(year), section, sha(roll), dob))
                return self.send(200, page_admin_students(msg='Student %s (%s) added. Default password = roll number or DOB.' % (name, roll)))
            if path == '/admin/students/bulk':
                txt = self.field(f, 'csv')
                ok, bad = 0, []
                lines = [l for l in txt.splitlines() if l.strip()]
                # header detection + flexible column mapping
                cols = None
                if lines:
                    first = lines[0].lower()
                    if any(k in first for k in ('roll', 'name', 'branch', 'dob', 'student')):
                        heads = [h.strip().lower() for h in lines.pop(0).split(',')]
                        cols = {}
                        for i, h in enumerate(heads):
                            if 'roll' in h or 'ht' in h or 'id' in h:
                                cols['roll'] = i
                            elif 'name' in h:
                                cols['name'] = i
                            elif 'branch' in h or 'dept' in h or 'br' in h:
                                cols['branch'] = i
                            elif 'year' in h or 'sem' in h or 'class' in h:
                                cols['year'] = i
                            elif 'section' in h or 'sec' in h:
                                cols['section'] = i
                            elif 'dob' in h or 'birth' in h:
                                cols['dob'] = i
                        if 'roll' not in cols or 'name' not in cols:
                            cols = None
                for i, line in enumerate(lines):
                    parts = [p.strip() for p in line.split(',')]
                    def getc(key, default=''):
                        if cols is not None:
                            idx = cols.get(key)
                            return parts[idx] if idx is not None and idx < len(parts) else default
                        return default
                    if cols is not None:
                        roll = getc('roll').upper().replace(' ', '')
                        name = getc('name')
                        branch = getc('branch').upper() or 'CSE'
                        year = getc('year') or '1'
                        section = getc('section') or 'A'
                        dob = getc('dob')
                    else:
                        if len(parts) < 3:
                            bad.append('line %d: not enough columns' % (i + 1))
                            continue
                        roll = parts[0].upper().replace(' ', '')
                        name = parts[1]
                        branch = parts[2].upper()
                        year = parts[3] if len(parts) > 3 else '1'
                        section = parts[4] if len(parts) > 4 else 'A'
                        dob = parts[5] if len(parts) > 5 else ''
                    # normalize branch/year/dob (accept codes or full names)
                    if branch not in BRANCHES:
                        bl = branch.lower()
                        match = next((b for b, nm in BRANCHES.items() if nm.lower() == bl or nm.lower().startswith(bl)), '')
                        if not match:
                            match = next((b for b in BRANCHES if bl.startswith(b.lower())), '')
                        branch = match
                    try:
                        year = int(re.sub(r'[^0-9]', '', str(year)) or 1)
                    except Exception:
                        year = 1
                    if not (1 <= year <= 4):
                        year = 1
                    if not re.match(r'^[A-Z0-9]{5,20}$', roll) or not name or not branch:
                        bad.append('line %d: %s (bad roll/name/branch)' % (i + 1, roll))
                        continue
                    if q1("SELECT 1 FROM students WHERE roll=?", (roll,)):
                        bad.append('line %d: %s already exists' % (i + 1, roll))
                        continue
                    run("INSERT INTO students(roll,name,branch,year,section,password,dob) VALUES(?,?,?,?,?,?,?)",
                        (roll, name, branch, int(year), section, sha(roll), dob))
                    ok += 1
                msg = 'Imported %d students.' % ok
                if bad:
                    msg += ' Skipped: ' + '; '.join(bad[:5])
                return self.send(200, page_admin_import(msg=msg))
            if path == '/admin/students/delete':
                roll = self.field(f, 'roll')
                run("DELETE FROM attendance WHERE roll=?", (roll,))
                run("DELETE FROM students WHERE roll=?", (roll,))
                return self.send(200, page_admin_students(msg='Student %s deleted.' % roll))
            if path == '/admin/subjects/add':
                code = self.field(f, 'code').upper()
                name = self.field(f, 'name')
                branch = self.field(f, 'branch')
                year = self.field(f, 'year')
                section = self.field(f, 'section')
                if not code or not name or branch not in BRANCHES:
                    return self.send(200, page_admin_subjects(err='Please fill all fields.'))
                run("INSERT INTO subjects(code,name,branch,year,section) VALUES(?,?,?,?,?)",
                    (code, name, branch, int(year), section))
                return self.send(200, page_admin_subjects(msg='Subject %s – %s added.' % (code, name)))
            if path == '/admin/subjects/delete':
                sid = self.field(f, 'id')
                run("DELETE FROM attendance WHERE subject_id=?", (sid,))
                run("DELETE FROM selfmark WHERE subject_id=?", (sid,))
                run("DELETE FROM subjects WHERE id=?", (sid,))
                return self.send(200, page_admin_subjects(msg='Subject deleted.'))
            if path == '/admin/selfmark':
                subject_id = self.field(f, 'subject_id')
                date_s = self.field(f, 'date')
                until = self.field(f, 'open_until')
                if not subject_id or not date_s:
                    return self.send(200, page_admin_selfmark(err='Please select subject and date.'))
                run("INSERT INTO selfmark(subject_id,date,open_until,enabled) VALUES(?,?,?,1)", (subject_id, date_s, until))
                return self.send(200, page_admin_selfmark(msg='Self-mark window opened for %s.' % fmt_date(date_s)))
            if path == '/admin/selfmark/toggle':
                sid = self.field(f, 'id')
                enabled = self.field(f, 'enabled')
                run("UPDATE selfmark SET enabled=? WHERE id=?", (int(enabled), sid))
                return self.redir('/admin/selfmark')
            if path == '/admin/attendance/import':
                txt = self.field(f, 'csv')
                lines = [l for l in txt.splitlines() if l.strip()]
                cols = None
                if lines:
                    first = lines[0].lower()
                    if any(k in first for k in ('roll', 'subject', 'sub', 'date', 'status', 'att')):
                        heads = [h.strip().lower() for h in lines.pop(0).split(',')]
                        cols = {}
                        for i, h in enumerate(heads):
                            if 'roll' in h or 'ht' in h or 'id' in h:
                                cols['roll'] = i
                            elif 'subject' in h or 'sub' in h or 'code' in h or 'course' in h:
                                cols['subj'] = i
                            elif 'date' in h:
                                cols['date'] = i
                            elif 'status' in h or 'att' in h or 'mark' in h or 'pres' in h or 'absent' in h:
                                cols['status'] = i
                        if 'roll' not in cols or 'subj' not in cols or 'date' not in cols:
                            cols = None
                ok, bad = 0, []
                for i, line in enumerate(lines):
                    parts = [p.strip() for p in line.split(',')]
                    if cols is not None:
                        def g(k):
                            idx = cols.get(k)
                            return parts[idx] if idx is not None and idx < len(parts) else ''
                        roll = g('roll').upper().replace(' ', '')
                        subj_ref = g('subj').upper().strip()
                        date_s = g('date')
                        status_raw = g('status')
                    else:
                        if len(parts) < 4:
                            bad.append('line %d: not enough columns' % (i + 1))
                            continue
                        roll = parts[0].upper().replace(' ', '')
                        subj_ref = parts[1].upper().strip()
                        date_s = parts[2]
                        status_raw = parts[3]
                    # date normalize: dd-mm-yyyy, dd/mm/yyyy, dd-mon-yyyy, yyyy-mm-dd
                    m = re.match(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$', date_s)
                    if m:
                        date_n = '%s-%s-%s' % (m.group(3), m.group(2).zfill(2), m.group(1).zfill(2))
                    else:
                        m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', date_s)
                        if m:
                            date_n = '%s-%02d-%02d' % (m.group(1), int(m.group(2)), int(m.group(3)))
                        else:
                            try:
                                date_n = datetime.strptime(date_s, '%d-%b-%Y').strftime('%Y-%m-%d')
                            except Exception:
                                bad.append('line %d: bad date "%s"' % (i + 1, date_s))
                                continue
                    # status normalize
                    sr = status_raw.lower()
                    if sr in ('p', '1', 'present', 'yes', 'y', 'true'):
                        status = 'P'
                    elif sr in ('a', '0', 'absent', 'no', 'n', 'false'):
                        status = 'A'
                    else:
                        bad.append('line %d: bad status "%s" (use P/A)' % (i + 1, status_raw))
                        continue
                    st = q1("SELECT branch, year FROM students WHERE roll=?", (roll,))
                    if not st:
                        bad.append('line %d: %s unknown student' % (i + 1, roll))
                        continue
                    # subject: prefer code+branch+year, then code alone, then name
                    subj = q1("SELECT * FROM subjects WHERE upper(code)=? AND branch=? AND year=?",
                              (subj_ref, st['branch'], st['year']))
                    if not subj:
                        subj = q1("SELECT * FROM subjects WHERE upper(code)=?", (subj_ref,))
                    if not subj:
                        subj = q1("SELECT * FROM subjects WHERE upper(name)=?", (subj_ref.upper(),))
                    if not subj:
                        subj = q1("SELECT * FROM subjects WHERE upper(name) LIKE ?",
                                  ('%' + subj_ref + '%',))
                    if not subj:
                        bad.append('line %d: subject "%s" not found (add it in Subjects tab first)' % (i + 1, subj_ref))
                        continue
                    run("INSERT INTO attendance(roll,subject_id,date,status,marked_by,marked_at) "
                        "VALUES(?,?,?,?, 'import', ?) "
                        "ON CONFLICT(roll,subject_id,date) DO UPDATE SET status=excluded.status, marked_by='import', marked_at=excluded.marked_at",
                        (roll, subj['id'], date_n, status, now_ist().isoformat(timespec='seconds')))
                    ok += 1
                msg = 'Imported %d attendance records.' % ok
                if bad:
                    msg += ' Skipped: ' + '; '.join(bad[:6])
                return self.send(200, page_admin_import(msg=msg))
            if path == '/admin/password':
                old = self.field(f, 'old')
                new = self.field(f, 'new')
                confirm = self.field(f, 'confirm')
                cur = q1("SELECT value FROM settings WHERE key='admin_pass'")['value']
                if new != confirm:
                    return self.send(200, page_admin_settings(err='New passwords do not match.'))
                if len(new) < 4:
                    return self.send(200, page_admin_settings(err='Password must be at least 4 characters.'))
                if sha(old) != cur:
                    return self.send(200, page_admin_settings(err='Current password is incorrect.'))
                run("UPDATE settings SET value=? WHERE key='admin_pass'", (sha(new),))
                return self.send(200, page_admin_settings(msg='Admin password updated!'))
            if path == '/admin/reset':
                con = conn()
                con.execute("DELETE FROM attendance")
                con.execute("DELETE FROM students")
                con.execute("DELETE FROM subjects")
                con.execute("DELETE FROM selfmark")
                con.commit()
                con.close()
                seed_demo()
                return self.send(200, page_admin_settings(msg='All data erased. Fresh demo data re-seeded.'))
            return self.redir('/admin')
        self.redir('/login')

    def redir_ck(self, loc, tok):
        self.send(303, '', extra_headers=[('Location', loc)] + self.set_cookie(tok))

    # ----- mark attendance page
    def mark_page(self, subject_id, date_s, msg='', err=''):
        flash = SimpleCookie(self.headers.get('Cookie', '')).get('flash')
        if flash and not msg:
            msg = unquote(flash.value)
        subjects = qall("SELECT * FROM subjects ORDER BY branch, year, code")
        body = ''
        if msg:
            body += '<div class="ok">%s</div>' % esc(msg)
        if err:
            body += '<div class="err">%s</div>' % esc(err)
        body += ('<div class="card" style="margin-bottom:16px"><h3><span class="bar"></span>Step 1 · Select Subject &amp; Date</h3>'
                 '<form class="form" method="get" action="/admin/attendance"><div class="row">'
                 '<div><label>Subject</label><select name="subject_id" onchange="this.form.submit()">'
                 '<option value="">-- Select Subject --</option>'
                 + ''.join('<option value="%s"%s>%s · %s · %s · %s</option>'
                           % (s['id'], ' selected' if str(s['id']) == str(subject_id) else '',
                              esc(s['code']), esc(s['name']), esc(s['branch']),
                              year_label(s['year']) + (' / Sec-' + s['section'] if s['section'] else ''))
                           for s in subjects) +
                 '</select></div>'
                 '<div><label>Date</label><input type="date" name="date" value="%s" onchange="this.form.submit()"></div>'
                 '<div style="align-self:end"><a class="btn outline" href="/admin/attendance">Today</a></div>'
                 '</div></form></div>' % date_s)
        if subject_id:
            subj = q1("SELECT * FROM subjects WHERE id=?", (subject_id,))
            if not subj:
                return page('Mark Attendance', topbar(admin=True) + body, admin='on')
            students = qall("SELECT * FROM students WHERE branch=? AND year=? AND (section=? OR ?='') "
                            "ORDER BY roll", (subj['branch'], subj['year'], subj['section'], subj['section']))
            marked = {r['roll']: r['status'] for r in qall(
                "SELECT roll, status FROM attendance WHERE subject_id=? AND date=?", (subject_id, date_s))}
            rows = ''
            for s in students:
                cur = marked.get(s['roll'], '')
                rows += ('<tr><td>%s</td><td>%s</td><td style="white-space:nowrap">'
                         '<label class="student-list"><input type="radio" name="r_%s" value="P"%s> Present</label>'
                         '<label class="student-list"><input type="radio" name="r_%s" value="A"%s> Absent</label>'
                         '<label class="student-list"><input type="radio" name="r_%s" value=""%s> —</label></td></tr>'
                         % (esc(s['roll']), esc(s['name']), esc(s['roll']),
                            ' checked' if cur == 'P' else '', esc(s['roll']),
                            ' checked' if cur == 'A' else '', esc(s['roll']),
                            ' checked' if cur == '' else ''))
            pc = sum(1 for v in marked.values() if v == 'P')
            ac = sum(1 for v in marked.values() if v == 'A')
            body += ('<div class="card"><h3><span class="bar"></span>Step 2 · Mark Attendance — '
                     '%s · %s <span class="sub">(%s · %s%s)</span></h3>'
                     '<div class="legend" style="margin-bottom:10px">'
                     '<span class="pill">👥 %d students</span>'
                     '<span class="pill">✅ %d present</span>'
                     '<span class="pill">❌ %d absent</span>'
                     '<span class="pill">➖ %d unmarked</span></div>'
                     '<form method="post" action="/admin/attendance">'
                     '<input type="hidden" name="subject_id" value="%s">'
                     '<input type="hidden" name="date" value="%s">'
                     '<div class="btn-row" style="margin-bottom:10px">'
                     '<button type="button" class="btn green sm" onclick="markAll(\'P\')">✅ All Present</button>'
                     '<button type="button" class="btn red sm" onclick="markAll(\'A\')">❌ All Absent</button>'
                     '<button type="button" class="btn outline sm" onclick="markAll(\'\')">➖ Clear All</button></div>'
                     '<table><tr><th style="width:160px">Roll No</th><th>Student Name</th><th>Mark</th></tr>%s</table>'
                     '<div class="btn-row" style="margin-top:14px"><button class="btn">💾 Save Attendance</button></div>'
                     '</form></div>'
                     % (esc(subj['code']), esc(subj['name']), esc(subj['branch']), year_label(subj['year']),
                        (' / Sec-' + subj['section']) if subj['section'] else '',
                        len(students), pc, ac, len(students) - pc - ac, subject_id, date_s, rows))
        body += ('<script>function markAll(v){document.querySelectorAll(\'input[type=radio]\').forEach'
                 '(r=>{if(r.value===v)r.checked=true})}</script>')
        return page('Mark Attendance', topbar(admin=True) + body, admin='on')


# ---------------------------------------------------------------- WSGI ----
# Lets the same app run on PythonAnywhere / other WSGI hosts (permanent link).
class WSGIHandler(App):
    """Minimal adapter: turns a WSGI request into the handler's self.* world."""

    def __init__(self, environ):
        path_info = environ.get('PATH_INFO') or '/'
        qs = environ.get('QUERY_STRING') or ''
        self.path = path_info + ('?' + qs if qs else '')
        self.headers = {
            'Cookie': environ.get('HTTP_COOKIE') or '',
            'Content-Length': environ.get('CONTENT_LENGTH') or '',
        }

        class _R:
            def __init__(self, inp):
                self.inp = inp

            def read(self, n=-1):
                return self.inp.read(n)

        self.rfile = _R(environ.get('wsgi.input'))
        self._code = 200
        self._hdrs = []
        self._body = b''

    def send(self, status, body, ctype='text/html; charset=utf-8',
             extra_headers=None, filename=None):
        self._code = int(status)
        if isinstance(body, str):
            body = body.encode('utf-8')
        self._body = body
        self._hdrs = [('Content-Type', ctype)]
        if filename:
            self._hdrs.append(('Content-Disposition',
                               'attachment; filename="%s"' % filename))
        if extra_headers:
            self._hdrs += list(extra_headers)


def wsgi_application(environ, start_response):
    db_init()
    h = WSGIHandler(environ)
    method = environ.get('REQUEST_METHOD', 'GET').upper()
    try:
        if method == 'POST':
            h.do_POST()
        else:
            h.do_GET()
    except Exception as e:
        h._code = 500
        h._body = ('Server error: %s' % html.escape(str(e))).encode('utf-8')
        h._hdrs = [('Content-Type', 'text/plain; charset=utf-8')]
    reasons = {200: 'OK', 303: 'See Other', 404: 'Not Found', 500: 'Internal Server Error'}
    start_response('%d %s' % (h._code, reasons.get(h._code, 'OK')), h._hdrs)
    return [h._body]


def main():
    db_init()
    srv = ThreadingHTTPServer(('0.0.0.0', PORT), App)
    print('JNTUACEA Attendance Portal running on http://0.0.0.0:%d' % PORT, flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()
