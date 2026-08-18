#!/usr/bin/env python3
"""
JNTUACEA Attendance — Student Academic Record Book
===================================================
Student flow (exactly like the popular JNTUA attendance app):
  * Login with your official portal credentials (roll + password)
  * We log into jntuaceastudents.classattendance.in for you
  * Dashboard shows: your NAME, roll number, class, overall %,
    subject-wise cards (total / present / absent, %, Can Skip /
    Need to Attend for the 75% rule) and date-wise details.

Admin flow (for the college): import students, mark attendance,
reports CSV, change admin password.

Run:  python3 app.py          (needs: pip install -r requirements.txt)
"""

import csv
import hashlib
import io
import json
import math
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------- config ----
BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, 'attendance.db')
PORT = int(os.environ.get('PORT', '8000'))
IST = timezone(timedelta(hours=5, minutes=30))
COLLEGE = 'JNTUA College of Engineering Ananthapuramu'
COLLEGE_SHORT = 'JNTUACEA'
PORTAL_URL = 'https://jntuaceastudents.classattendance.in/'

BRANCHES = {'CSE': 'Computer Science & Engineering', 'ECE': 'Electronics & Communication Engineering',
            'EEE': 'Electrical & Electronics Engineering', 'ME': 'Mechanical Engineering',
            'CE': 'Civil Engineering'}
BRANCH_CODE = {'CE': '01', 'EEE': '02', 'ME': '03', 'ECE': '04', 'CSE': '05'}

# live official-portal sessions (like the reference app keeps them in memory)
ACTIVE_SESSIONS = {}

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


def now_ist():
    return datetime.now(IST)


def db_init():
    con = conn()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS students(
      roll TEXT PRIMARY KEY, name TEXT NOT NULL, branch TEXT NOT NULL,
      year INTEGER NOT NULL, section TEXT NOT NULL DEFAULT 'A',
      password TEXT NOT NULL, dob TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS subjects(
      id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, name TEXT NOT NULL,
      branch TEXT NOT NULL, year INTEGER NOT NULL, section TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS attendance(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      roll TEXT NOT NULL, subject_id INTEGER NOT NULL, date TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'P', marked_by TEXT DEFAULT 'admin',
      marked_at TEXT DEFAULT '',
      UNIQUE(roll, subject_id, date));
    CREATE TABLE IF NOT EXISTS student_info(
      roll TEXT PRIMARY KEY, name TEXT DEFAULT '', classname TEXT DEFAULT '',
      acad_year TEXT DEFAULT '', updated_at TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS subject_totals(
      roll TEXT NOT NULL, key TEXT NOT NULL, name TEXT NOT NULL,
      total INTEGER NOT NULL, present INTEGER NOT NULL, updated_at TEXT DEFAULT '',
      PRIMARY KEY(roll, key));
    CREATE TABLE IF NOT EXISTS settings(
      key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS student_sessions(
      token TEXT PRIMARY KEY, roll TEXT NOT NULL);
    """)
    if not con.execute("SELECT 1 FROM settings WHERE key='admin_pass'").fetchone():
        con.execute("INSERT INTO settings(key,value) VALUES('admin_pass', ?)", (sha('admin123'),))
    con.commit()
    con.close()


def guess_branch_year(classname):
    branch, year = 'CSE', 2
    cl = (classname or '').upper()
    for b in BRANCHES:
        if b in cl:
            branch = b
            break
    if 'IV' in cl:
        year = 4
    elif 'III' in cl:
        year = 3
    elif 'II' in cl:
        year = 2
    elif 'I' in cl:
        year = 1
    return branch, year


def norm_date(s):
    s = (s or '').strip()
    m = re.match(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$', s)
    if m:
        return '%s-%s-%s' % (m.group(3), m.group(2).zfill(2), m.group(1).zfill(2))
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', s)
    if m:
        return '%s-%02d-%02d' % (m.group(1), int(m.group(2)), int(m.group(3)))
    for fmt in ('%d-%b-%Y', '%d %b %Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except Exception:
            pass
    return ''


def find_or_create_subject(name, branch, year):
    nm = (name or '').strip()
    row = q1("SELECT * FROM subjects WHERE upper(name)=? AND branch=? AND year=?",
             (nm.upper(), branch, year))
    if not row:
        row = q1("SELECT * FROM subjects WHERE upper(name)=?", (nm.upper(),))
    if row:
        return row['id']
    code = 'OF' + hashlib.sha256(nm.upper().encode()).hexdigest()[:6].upper()
    return run("INSERT INTO subjects(code,name,branch,year,section) VALUES(?,?,?,?,'')",
               (code, nm[:80], branch, year)).lastrowid


def store_fetch(roll, data):
    """Cache a full official fetch into our DB."""
    details = data.get('details') or {}
    name = details.get('Student Name') or details.get('Name') or ''
    if not name:
        for k, v in details.items():
            if 'name' in k.lower() and v:
                name = v.strip()
                break
    name = name or roll
    cls = details.get('classname') or details.get('Class') or details.get('Class Name') or ''
    acy = details.get('acad_year') or details.get('Academic Year') or ''
    branch, year = guess_branch_year(cls)
    run("INSERT INTO students(roll,name,branch,year,section,password) VALUES(?,?,?,?,'A',?) "
        "ON CONFLICT(roll) DO UPDATE SET name=excluded.name, branch=excluded.branch, year=excluded.year",
        (roll, name[:60], branch, year, sha(roll)))
    run("INSERT INTO student_info(roll,name,classname,acad_year,updated_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(roll) DO UPDATE SET name=excluded.name, classname=excluded.classname, "
        "acad_year=excluded.acad_year, updated_at=excluded.updated_at",
        (roll, name[:60], cls[:80], acy[:40], now_ist().isoformat(timespec='seconds')))
    total_recs = 0
    for subj in data.get('subjects', []):
        sn = (subj.get('Subject') or '').strip()
        if not sn:
            continue
        sid = find_or_create_subject(sn, branch, year)
        # portal's own summary numbers (Total Days / Present) — authoritative
        try:
            tot = int(subj.get('Total Days') or 0)
            pres = int(subj.get('No. of Present') or 0)
        except Exception:
            tot = pres = 0
        if tot > 0:
            key = re.sub(r'[^a-z0-9]', '', sn.lower())
            run("INSERT INTO subject_totals(roll,key,name,total,present,updated_at) "
                "VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(roll,key) DO UPDATE SET name=excluded.name, "
                "total=excluded.total, present=excluded.present, updated_at=excluded.updated_at",
                (roll, key, sn[:80], tot, pres, now_ist().isoformat(timespec='seconds')))
        for rec in subj.get('Details', []):
            d = norm_date(rec.get('date', ''))
            if not d or rec.get('status') not in ('P', 'A'):
                continue
            run("INSERT INTO attendance(roll,subject_id,date,status,marked_by,marked_at) "
                "VALUES(?,?,?,?, 'official', ?) "
                "ON CONFLICT(roll,subject_id,date) DO UPDATE SET status=excluded.status, "
                "marked_by='official', marked_at=excluded.marked_at",
                (roll, sid, d, rec['status'], now_ist().isoformat(timespec='seconds')))
            total_recs += 1
    return total_recs


def skip_advice(present, total):
    if total == 0:
        return 'neutral', 'No classes recorded yet.'
    pct = present * 100.0 / total
    if pct >= 75:
        can = max(0, int(present / 0.75 - total))
        if can > 0:
            return 'good', 'You can skip up to <b>%d</b> more classes and stay above 75%%.' % can
        return 'good', 'You are safely above 75%.'
    need = max(0, int((0.75 * total - present) / 0.25))
    return 'bad', 'Attend the next <b>%d</b> classes to get back above 75%%.' % max(1, need)


# ---------------------------------------------------------------- CSS -------
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#F4F6F9;--card:#fff;--border:#E5E9F0;--ink:#1A1F2E;--muted:#8892A0;
--green:#059669;--red:#DC2626;--amber:#D97706;--navy:#123a6b;--gold:#f0b429}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,Arial,sans-serif;
background:var(--bg);color:var(--ink);min-height:100vh;-webkit-font-smoothing:antialiased}
a{text-decoration:none;color:var(--navy)}
.page{max-width:860px;margin:0 auto;padding:28px 16px 60px}
.wide{max-width:1060px}
/* header */
.site-header{margin-bottom:28px}
.eyebrow{display:inline-flex;align-items:center;gap:7px;font-size:.65rem;font-weight:700;
letter-spacing:1.4px;text-transform:uppercase;color:var(--muted);margin-bottom:12px}
.eyebrow-dot{width:5px;height:5px;border-radius:50%;background:#22C55E;animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}
.header-row{display:flex;align-items:flex-start;gap:18px;margin-bottom:6px}
.avatar{flex-shrink:0;width:52px;height:52px;border-radius:14px;
background:linear-gradient(135deg,#123a6b,#1a4d8f);display:flex;align-items:center;
justify-content:center;color:#fff;font-size:1.3rem;font-weight:800;box-shadow:0 4px 12px rgba(18,58,107,.25)}
.header-text h1{font-size:clamp(1.3rem,4vw,2rem);font-weight:800;letter-spacing:-.5px;
line-height:1.1;text-transform:uppercase}
.header-text .uid{font-size:.78rem;color:var(--muted);margin-top:4px;font-weight:600;letter-spacing:.4px}
/* stat row */
.stat-row{display:flex;gap:22px;margin-top:20px;flex-wrap:wrap;align-items:center}
.stat{display:flex;flex-direction:column;gap:2px}
.stat-val{font-size:1.5rem;font-weight:800;letter-spacing:-.5px;line-height:1}
.stat-val.green{color:var(--green)}.stat-val.red{color:var(--red)}
.stat-label{font-size:.62rem;font-weight:600;letter-spacing:.7px;text-transform:uppercase;color:var(--muted)}
.stat-sep{width:1px;height:26px;background:var(--border)}
/* buttons */
.action-row{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;margin-bottom:26px}
.btn{display:inline-flex;align-items:center;gap:6px;font-size:.78rem;font-weight:700;padding:8px 16px;
border-radius:9px;border:1px solid var(--border);background:var(--card);color:#374151;cursor:pointer}
.btn:hover{background:var(--bg);transform:translateY(-1px);box-shadow:0 3px 10px rgba(0,0,0,.07)}
.btn-navy{background:var(--navy);color:#fff;border-color:var(--navy)}
.btn-green{background:var(--green);color:#fff;border-color:var(--green)}
.btn-red{background:var(--red);color:#fff;border-color:var(--red)}
.btn-sm{padding:6px 12px;font-size:.72rem}
/* section head */
.section-head{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.sh-label{font-size:.6rem;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;color:var(--muted);white-space:nowrap}
.sh-line{flex:1;height:1px;background:var(--border)}
.sh-badge{font-size:.64rem;font-weight:700;padding:3px 9px;border-radius:20px;background:#EFF6FF;color:#1D4ED8;border:1px solid #BFDBFE}
/* search */
.search-wrap{max-width:340px;margin-bottom:16px}
#subject-search{width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:9px;
background:var(--card);font-size:.8rem;outline:none}
#subject-search:focus{border-color:#A78BFA;box-shadow:0 0 0 3px rgba(167,139,250,.15)}
/* subject cards */
.subj-card{background:var(--card);border:1px solid var(--border);border-radius:14px;overflow:hidden;
display:flex;margin-bottom:10px;transition:transform .2s,box-shadow .2s}
.subj-card:hover{transform:translateY(-2px);box-shadow:0 6px 24px rgba(0,0,0,.07)}
.card-bar{width:4px;flex-shrink:0}
.subj-inner{flex:1;padding:14px 16px;display:flex;align-items:center;gap:14px;min-width:0;flex-wrap:wrap}
.pct-block{flex-shrink:0;width:56px;text-align:center}
.pct-num{font-size:1.15rem;font-weight:800;line-height:1}
.pct-cap{font-size:.56rem;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:var(--muted);margin-top:2px}
.subj-main{flex:1;min-width:160px}
.subj-name{font-weight:800;font-size:.95rem;letter-spacing:-.2px}
.subj-meta{font-size:.72rem;color:var(--muted);margin-top:3px;display:flex;gap:10px;flex-wrap:wrap}
.subj-advice{font-size:.72rem;font-weight:600;padding:4px 9px;border-radius:8px;margin-top:6px;display:inline-block}
.adv-good{background:#E7F6EF;color:#046C4E}
.adv-bad{background:#FDE8E8;color:#9B1C1C}
.adv-neutral{background:#EEF1F6;color:#66748f}
details{width:100%;margin-top:8px;font-size:.75rem;color:var(--muted)}
details summary{cursor:pointer;font-weight:700;color:var(--navy);padding:2px 0}
.det-table{width:100%;border-collapse:collapse;margin-top:8px}
.det-table th{font-size:.6rem;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);
text-align:left;padding:5px 8px;border-bottom:1px solid var(--border)}
.det-table td{font-size:.74rem;padding:5px 8px;border-bottom:1px solid #F3F5F9}
.badge{display:inline-block;font-size:.64rem;font-weight:700;padding:2px 9px;border-radius:20px}
.b-p{background:#E7F6EF;color:#046C4E}
.b-a{background:#FDE8E8;color:#9B1C1C}
/* login */
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;
background:linear-gradient(135deg,#0d2a4f,#123a6b 55%,#1a4d8f);padding:20px}
.login-card{background:#fff;border-radius:18px;padding:32px 28px;width:100%;max-width:420px;
box-shadow:0 20px 60px rgba(0,0,0,.35)}
.brand{text-align:center;margin-bottom:18px}
.brand img{height:84px;border-radius:50%;background:#fff;padding:4px;border:3px solid var(--gold);box-shadow:0 0 0 3px var(--navy)}
.brand .bt{font-weight:800;font-size:15px;color:var(--navy);margin-top:10px;line-height:1.3}
.brand .bs{color:var(--gold);font-weight:700;font-size:12.5px;letter-spacing:1.5px;text-transform:uppercase;margin-top:2px}
.brand .bl{color:var(--muted);font-size:11.5px;margin-top:4px}
.field{margin-bottom:13px}
.field label{font-size:12px;font-weight:700;color:var(--muted);display:block;margin-bottom:5px;letter-spacing:.4px;text-transform:uppercase}
.field input{width:100%;padding:11px 13px;border:1.5px solid var(--border);border-radius:10px;font-size:14px;outline:none}
.field input:focus{border-color:var(--navy)}
.login-btn{width:100%;padding:12px;font-size:15px;margin-top:4px;justify-content:center}
.hint{font-size:11.5px;color:var(--muted);text-align:center;margin-top:14px;background:#F4F7FC;border-radius:8px;padding:8px}
/* notices & error page */
.notice{background:#FFF8E5;border:1px solid #F3DF9A;color:#7A5C00;border-radius:10px;
padding:11px 14px;font-size:12.5px;margin-bottom:14px}
.notice.green{background:#E8F7EE;border-color:#BFE6CF;color:#16603A}
.notice.red{background:#FDE8E8;border-color:#F2C4C4;color:#9B1C1C}
.error-page{max-width:520px;margin:60px auto;background:#fff;border:1px solid var(--border);
border-radius:16px;padding:32px 28px;text-align:center}
.error-page .ico{font-size:34px;margin-bottom:10px}
.error-page h2{font-size:1.15rem;margin-bottom:10px}
.error-page p{font-size:.85rem;color:var(--muted);margin-bottom:18px;line-height:1.6}
/* admin */
table{width:100%;border-collapse:collapse;font-size:.8rem}
th{background:#F4F7FC;color:var(--navy);text-align:left;padding:9px 10px;
border-bottom:2px solid var(--border);font-size:.68rem;text-transform:uppercase;letter-spacing:.5px}
td{padding:9px 10px;border-bottom:1px solid var(--border)}
tr:hover td{background:#FAFCFF}
.card{background:var(--card);border-radius:14px;padding:20px;box-shadow:0 2px 10px rgba(18,58,107,.07);border:1px solid var(--border);margin-bottom:14px}
.card h3{font-size:.95rem;margin-bottom:12px;color:var(--navy);display:flex;align-items:center;gap:8px}
.card h3 .bar{width:4px;height:16px;background:var(--gold);border-radius:3px}
.form{display:grid;gap:11px}
.form .row{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:11px}
textarea{width:100%;padding:10px 12px;border:1.5px solid var(--border);border-radius:10px;
font-size:13px;font-family:inherit;outline:none;min-height:110px}
input,select{width:100%;padding:10px 12px;border:1.5px solid var(--border);border-radius:10px;font-size:13.5px;outline:none}
select{background:#fff}
label{font-size:11.5px;font-weight:700;color:var(--muted);display:block;margin-bottom:5px;letter-spacing:.4px;text-transform:uppercase}
.tabs{display:flex;border-bottom:2px solid var(--border);margin-bottom:16px;gap:4px;flex-wrap:wrap}
.tab{padding:8px 16px;border:none;background:none;font-size:.82rem;font-weight:700;color:var(--muted);cursor:pointer;border-radius:8px 8px 0 0}
.tab.on{color:var(--navy);border-bottom:3px solid var(--gold);margin-bottom:-2px}
.footer{text-align:center;color:var(--muted);font-size:11.5px;padding:24px 16px 40px}
.footer b{color:var(--navy)}
@media(max-width:600px){.page{padding:16px 10px 50px}.subj-inner{padding:12px}}
"""


# ---------------------------------------------------------------- pages -----
def page(title, body, extra_head=''):
    return ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>%s</title><link rel="icon" href="/static/logo.png">%s'
            '<style>%s</style></head><body>%s</body></html>'
            % (title, extra_head, CSS, body))


def esc(t):
    import html as _h
    return _h.escape(str(t), quote=True)


def fmt_date(s):
    try:
        return datetime.strptime(s, '%Y-%m-%d').strftime('%d %b %Y')
    except Exception:
        return s


def year_roman(y):
    return {1: 'I', 2: 'II', 3: 'III', 4: 'IV'}.get(y, str(y))


# ---------------- login page ----------------
def page_login(err=''):
    body = ('<div class="login-wrap"><div class="login-card">'
            '<div class="brand"><img src="/static/logo.png" alt="JNTUACEA">'
            '<div class="bt">%s</div>'
            '<div class="bs">Student Academic Record Book</div>'
            '<div class="bl">Accredited by NAAC with "A" Grade</div></div>'
            % (esc(COLLEGE),))
    if err:
        body += ('<div class="notice red">%s</div>' % esc(err))
    body += ('<form method="post" action="/login">'
             '<div class="field"><label>Username (Roll Number)</label>'
             '<input name="username" required placeholder="e.g. 23001A0204" autocomplete="username"></div>'
             '<div class="field"><label>Password</label>'
             '<input type="password" name="password" required placeholder="Your official portal password" '
             'autocomplete="current-password"></div>'
             '<button class="btn btn-navy login-btn">Check My Attendance</button></form>'
             '<div class="hint">We log into the official portal '
             '<b>jntuaceastudents.classattendance.in</b> with your own credentials and show '
             'your attendance. Your password is never stored. '
             '<a href="/admin" style="font-weight:700">Admin login →</a></div></div></div>')
    return page('JNTUACEA Attendance — Login', body)


# ---------------- error page ----------------
def page_error(message, back='/'):
    body = ('<div class="error-page"><div class="ico">⚠️</div>'
            '<h2>Something went wrong</h2>'
            '<p>%s</p>'
            '<div class="action-row"><a class="btn btn-navy" href="%s">← Try Again</a>'
            '<a class="btn" href="%s" target="_blank" rel="noopener">Open Official Portal ↗</a></div>'
            '</div>'
            % (esc(message), esc(back), esc(PORTAL_URL)))
    return page('Error', body)


# ---------------- dashboard (result page, like the reference app) ----------------
def page_dashboard(roll, notice=''):
    st = q1("SELECT * FROM students WHERE roll=?", (roll,))
    if not st:
        return page_error('No cached data for this account. Please log in again.', '/logout')
    info = q1("SELECT * FROM student_info WHERE roll=?", (roll,))
    name = (info['name'] if info and info['name'] else st['name'])
    cls = info['classname'] if info and info['classname'] else ('%s %s' % (year_roman(st['year']), st['branch']))
    acy = info['acad_year'] if info and info['acad_year'] else ''
    subs = qall("SELECT * FROM subjects WHERE branch=? AND year=? AND (section='' OR section=?) "
                "ORDER BY name", (st['branch'], st['year'], st['section']))
    totals = {r['key']: r for r in qall("SELECT * FROM subject_totals WHERE roll=?", (roll,))}
    rows = []
    for s in subs:
        key = re.sub(r'[^a-z0-9]', '', s['name'].lower())
        trow = totals.get(key)
        if trow:
            # authoritative portal summary numbers
            t = int(trow['total'])
            p = int(trow['present'])
        else:
            stats = q1("SELECT COUNT(*) t, SUM(CASE WHEN status='P' THEN 1 ELSE 0 END) p "
                       "FROM attendance WHERE roll=? AND subject_id=?", (roll, s['id']))
            t = stats['t'] or 0
            p = stats['p'] or 0
        a = t - p
        pct = round(p * 100.0 / t, 1) if t else 0
        clsadv, adv = skip_advice(p, t)
        det = qall("SELECT date, status FROM attendance WHERE roll=? AND subject_id=? "
                   "ORDER BY date DESC LIMIT 60", (roll, s['id']))
        det_rows = ''.join(
            '<tr><td>%s</td><td><span class="badge %s">%s</span></td></tr>'
            % (fmt_date(r['date']), 'b-p' if r['status'] == 'P' else 'b-a',
               'Present' if r['status'] == 'P' else 'Absent')
            for r in det)
        if not det_rows:
            det_rows = '<tr><td colspan="2">No date-wise records.</td></tr>'
        rows.append({'name': s['name'], 't': t, 'p': p, 'a': a, 'pct': pct,
                     'cls': clsadv, 'adv': adv, 'det_rows': det_rows})
    # also show subjects the portal reported that are not in our subject list
    for key, trow in totals.items():
        if any(re.sub(r'[^a-z0-9]', '', r['name'].lower()) == key for r in rows):
            continue
        t = int(trow['total'])
        p = int(trow['present'])
        pct = round(p * 100.0 / t, 1) if t else 0
        clsadv, adv = skip_advice(p, t)
        rows.append({'name': trow['name'], 't': t, 'p': p, 'a': t - p, 'pct': pct,
                     'cls': clsadv, 'adv': adv, 'det_rows': '<tr><td colspan="2">No date-wise records.</td></tr>'})
    rows.sort(key=lambda r: r['name'])
    total_days = sum(r['t'] for r in rows)
    total_present = sum(r['p'] for r in rows)
    overall_pct = round(total_present * 100.0 / total_days, 2) if total_days else 0

    body = ('<div class="page">'
            '<a class="btn btn-sm" href="/logout" style="margin-bottom:16px">← Logout</a>'
            '<div class="site-header">'
            '<div class="eyebrow"><span class="eyebrow-dot"></span>Live attendance · Official portal synced</div>'
            '<div class="header-row">'
            '<div class="avatar">%s</div>'
            '<div class="header-text"><h1>%s</h1>'
            '<div class="uid">%s &nbsp;·&nbsp; %s%s</div></div></div>'
            '<div class="stat-row">'
            '<div class="stat"><div class="stat-val %s">%s%%</div><div class="stat-label">Overall Attendance</div></div>'
            '<div class="stat-sep"></div>'
            '<div class="stat"><div class="stat-val">%d</div><div class="stat-label">Total Classes</div></div>'
            '<div class="stat-sep"></div>'
            '<div class="stat"><div class="stat-val green">%d</div><div class="stat-label">Present</div></div>'
            '<div class="stat-sep"></div>'
            '<div class="stat"><div class="stat-val red">%d</div><div class="stat-label">Absent</div></div>'
            '</div></div>'
            % (esc((name[0] if name else 'S').upper()), esc(name.upper()), esc(roll),
               esc(cls), (' · ' + esc(acy)) if acy else '',
               'green' if overall_pct >= 75 else 'red', ('%.1f' % overall_pct),
               total_days, total_present, total_days - total_present))
    if notice:
        body += ('<div class="notice">%s</div>' % notice)
    body += ('<div class="action-row">'
             '<a class="btn btn-navy" href="/refresh">🔄 Refresh</a>'
             '<a class="btn" href="/student/print" target="_blank" rel="noopener">🖨 Print</a>'
             '<a class="btn" href="%s" target="_blank" rel="noopener">Official Portal ↗</a></div>'
             '<div class="section-head"><span class="sh-label">Subjects</span><span class="sh-line"></span>'
             '<span class="sh-badge">%d subjects</span></div>'
             '<div class="search-wrap"><input id="subject-search" placeholder="Search subjects…" '
             'onkeyup="var v=this.value.toLowerCase();document.querySelectorAll(\'.subj-card\').forEach'
             '(c=>{c.style.display=c.innerText.toLowerCase().includes(v)?\'\':\'none\'})"></div>'
             % (esc(PORTAL_URL), len(rows)))
    for r in rows:
        bar = '#059669' if r['pct'] >= 75 else ('#D97706' if r['pct'] >= 60 else '#DC2626')
        body += ('<div class="subj-card"><div class="card-bar" style="background:%s"></div>'
                 '<div class="subj-inner">'
                 '<div class="pct-block"><div class="pct-num" style="color:%s">%s%%</div>'
                 '<div class="pct-cap">Attendance</div></div>'
                 '<div class="subj-main"><div class="subj-name">%s</div>'
                 '<div class="subj-meta"><span>Total: <b>%d</b></span>'
                 '<span>Present: <b style="color:var(--green)">%d</b></span>'
                 '<span>Absent: <b style="color:var(--red)">%d</b></span></div>'
                 '<div class="subj-advice adv-%s">%s</div></div>'
                 '<details><summary>📋 Date-wise details</summary>'
                 '<table class="det-table"><tr><th>Date</th><th>Status</th></tr>%s</table></details>'
                 '</div></div>'
                 % (bar, bar, ('%.1f' % r['pct']), esc(r['name']), r['t'], r['p'], r['a'],
                    r['cls'], r['adv'], r['det_rows']))
    body += ('<div class="footer">%s · Student Academic Record Book · Data fetched from the '
             'official portal with your own credentials</div></div>' % esc(COLLEGE))
    return page('Attendance Result — JNTUACEA', body)


def page_print(roll):
    st = q1("SELECT * FROM students WHERE roll=?", (roll,))
    info = q1("SELECT * FROM student_info WHERE roll=?", (roll,))
    name = (info['name'] if info and info['name'] else (st['name'] if st else roll))
    subs = qall("SELECT * FROM subjects WHERE branch=? AND year=? ORDER BY name",
                (st['branch'], st['year']))
    totals = {r['key']: r for r in qall("SELECT * FROM subject_totals WHERE roll=?", (roll,))}
    tr = ''
    for s in subs:
        key = re.sub(r'[^a-z0-9]', '', s['name'].lower())
        trow = totals.get(key)
        if trow:
            t, p = int(trow['total']), int(trow['present'])
        else:
            stats = q1("SELECT COUNT(*) t, SUM(CASE WHEN status='P' THEN 1 ELSE 0 END) p "
                       "FROM attendance WHERE roll=? AND subject_id=?", (roll, s['id']))
            t, p = stats['t'] or 0, stats['p'] or 0
        pct = round(p * 100.0 / t, 1) if t else 0
        tr += ('<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td><td>%s%%</td></tr>'
               % (esc(s['name']), t, p, t - p, ('%.1f' % pct)))
    body = ('<div class="page"><h2 style="text-transform:uppercase">%s</h2>'
            '<p style="color:var(--muted);margin:6px 0 18px">Roll Number: %s &nbsp;·&nbsp; %s</p>'
            '<table><tr><th>Subject</th><th>Total</th><th>Present</th><th>Absent</th><th>Attendance %%</th></tr>'
            '%s</table></div>'
            % (esc(name), esc(roll), esc(COLLEGE), tr))
    return page('Print — Attendance Statement', body)


# ---------------- admin ----------------
def admin_nav(active=''):
    items = [('home', '/admin', 'Home'), ('students', '/admin/students', 'Students'),
             ('att', '/admin/attendance', 'Mark Attendance'), ('reports', '/admin/reports', 'Reports')]
    return ('<div class="tabs">' + ''.join(
        '<a class="tab%s" href="%s">%s</a>' % (' on' if a == active else '', u, l)
        for a, u, l in items) +
        '<a class="tab" href="/admin/logout">Logout</a></div>')


def admin_wrap(title, body, active=''):
    return page(title, '<div class="page wide">' + admin_nav(active) + body + '</div>')


def page_admin_login(err=''):
    body = ('<div class="login-wrap"><div class="login-card">'
            '<div class="brand"><img src="/static/logo.png" alt="JNTUACEA">'
            '<div class="bt">Admin Login</div><div class="bl">Attendance management panel</div></div>'
            + ('<div class="notice red">%s</div>' % esc(err) if err else '')
            + '<form method="post" action="/admin/login">'
            '<div class="field"><label>Username</label><input name="username" required value="admin"></div>'
            '<div class="field"><label>Password</label><input type="password" name="password" required></div>'
            '<button class="btn btn-navy login-btn">Login</button></form>'
            '<div class="hint"><a href="/login">← Student login</a></div></div></div>')
    return page('Admin — JNTUACEA', body)


def page_admin_home():
    t_students = q1("SELECT COUNT(*) c FROM students")['c']
    t_subjects = q1("SELECT COUNT(*) c FROM subjects")['c']
    t_att = q1("SELECT COUNT(*) c FROM attendance")['c']
    body = ('<div class="card"><h3><span class="bar"></span>Overview</h3>'
            '<div class="stat-row">'
            '<div class="stat"><div class="stat-val">%d</div><div class="stat-label">Students</div></div>'
            '<div class="stat-sep"></div>'
            '<div class="stat"><div class="stat-val">%d</div><div class="stat-label">Subjects</div></div>'
            '<div class="stat-sep"></div>'
            '<div class="stat"><div class="stat-val">%d</div><div class="stat-label">Attendance rows</div></div>'
            '</div></div>'
            '<div class="card"><h3><span class="bar"></span>Quick actions</h3>'
            '<div class="action-row" style="justify-content:flex-start">'
            '<a class="btn btn-navy" href="/admin/students">👥 Add Students (CSV)</a>'
            '<a class="btn btn-green" href="/admin/attendance">✅ Mark Attendance</a>'
            '<a class="btn" href="/admin/reports">📊 Reports / CSV</a></div></div>'
            % (t_students, t_subjects, t_att))
    return admin_wrap('Admin Home', body, 'home')


def page_admin_students(msg='', err=''):
    sts = qall("SELECT * FROM students ORDER BY branch, year, roll")
    tr = ''.join('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s Year</td><td>%s</td></tr>'
                 % (esc(s['roll']), esc(s['name']), esc(s['branch']), year_roman(s['year']), esc(s['section']))
                 for s in sts)
    body = (('<div class="ok notice green">%s</div>' % esc(msg)) if msg else '') \
        + (('<div class="notice red">%s</div>' % esc(err)) if err else '')
    body += ('<div class="card"><h3><span class="bar"></span>Bulk add students (CSV)</h3>'
             '<p style="font-size:12.5px;color:var(--muted);margin-bottom:10px">'
             'One student per line: <b>roll,name,branch,year,section,dob(optional)</b>. '
             'Header line is auto-detected. Students can log in with roll number + official password '
             '(they will sync their own attendance from the official portal).</p>'
             '<form class="form" method="post" action="/admin/students">'
             '<textarea name="csv" placeholder="22A51A0501,Ravi Teja,CSE,2,A,2004-05-14"></textarea>'
             '<div><button class="btn btn-navy">Import Students</button></div></form></div>'
             '<div class="card"><h3><span class="bar"></span>All students (%d)</h3>'
             '<table><tr><th>Roll</th><th>Name</th><th>Branch</th><th>Year</th><th>Section</th></tr>'
             '%s</table></div>' % (len(sts), tr))
    return admin_wrap('Students', body, 'students')


def page_admin_attendance(msg='', err='', subject_id=None, date_s=None):
    import datetime as _dt
    date_s = date_s or _dt.date.today().isoformat()
    subjects = qall("SELECT * FROM subjects ORDER BY branch, year, code")
    body = (('<div class="notice green">%s</div>' % esc(msg)) if msg else '') \
        + (('<div class="notice red">%s</div>' % esc(err)) if err else '')
    body += ('<div class="card"><h3><span class="bar"></span>Select subject &amp; date</h3>'
             '<form class="form" method="get" action="/admin/attendance"><div class="row">'
             '<div><label>Subject</label><select name="subject_id" onchange="this.form.submit()">'
             '<option value="">— select —</option>'
             + ''.join('<option value="%s"%s>%s · %s · %s · %s Year</option>'
                       % (s['id'], ' selected' if str(s['id']) == str(subject_id) else '',
                          esc(s['code']), esc(s['name']), esc(s['branch']), year_roman(s['year']))
                       for s in subjects)
             + '</select></div>'
             '<div><label>Date</label><input type="date" name="date" value="%s" onchange="this.form.submit()"></div>'
             '</div></form></div>' % date_s)
    if subject_id:
        subj = q1("SELECT * FROM subjects WHERE id=?", (subject_id,))
        if subj:
            students = qall("SELECT * FROM students WHERE branch=? AND year=? "
                            "AND (section=? OR ?='') ORDER BY roll",
                            (subj['branch'], subj['year'], subj['section'], subj['section']))
            marked = {r['roll']: r['status'] for r in qall(
                "SELECT roll, status FROM attendance WHERE subject_id=? AND date=?", (subject_id, date_s))}
            rows = ''.join(
                '<tr><td>%s</td><td>%s</td><td style="white-space:nowrap">'
                '<label style="display:inline;margin-right:10px"><input type="radio" name="r_%s" value="P"%s> Present</label>'
                '<label style="display:inline"><input type="radio" name="r_%s" value="A"%s> Absent</label></td></tr>'
                % (esc(s['roll']), esc(s['name']), esc(s['roll']),
                   ' checked' if marked.get(s['roll']) == 'P' else '',
                   esc(s['roll']), ' checked' if marked.get(s['roll']) == 'A' else '')
                for s in students)
            body += ('<div class="card"><h3><span class="bar"></span>%s — %s (%s)</h3>'
                     '<form method="post" action="/admin/attendance">'
                     '<input type="hidden" name="subject_id" value="%s">'
                     '<input type="hidden" name="date" value="%s">'
                     '<div class="action-row" style="justify-content:flex-start;margin-bottom:10px">'
                     '<button type="button" class="btn btn-green btn-sm" '
                     'onclick="document.querySelectorAll(\'input[value=P]\').forEach(r=>r.checked=true)">All Present</button>'
                     '<button type="button" class="btn btn-red btn-sm" '
                     'onclick="document.querySelectorAll(\'input[value=A]\').forEach(r=>r.checked=true)">All Absent</button></div>'
                     '<table><tr><th style="width:160px">Roll</th><th>Name</th><th>Mark</th></tr>%s</table>'
                     '<div style="margin-top:12px"><button class="btn btn-navy">Save Attendance</button></div>'
                     '</form></div>' % (esc(subj['code']), esc(subj['name']), esc(subj['branch']),
                                        subject_id, date_s, rows))
    return admin_wrap('Mark Attendance', body, 'att')


def page_admin_reports():
    rows = qall("SELECT st.roll, st.name, st.branch, st.year, "
                "SUM(CASE WHEN a.status='P' THEN 1 ELSE 0 END) p, COUNT(a.id) t "
                "FROM students st LEFT JOIN attendance a ON a.roll=st.roll "
                "GROUP BY st.roll ORDER BY st.branch, st.year, st.roll")
    tr = ''
    for r in rows:
        p, t = r['p'] or 0, r['t'] or 0
        pct = round(p * 100.0 / t, 1) if t else 0
        cls = 'b-p' if pct >= 75 else ('b-a' if pct < 60 else 'b-p')
        tr += ('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s Year</td><td>%d</td><td>%d</td>'
               '<td><span class="badge %s">%s%%</span></td></tr>'
               % (esc(r['roll']), esc(r['name']), esc(r['branch']), year_roman(r['year']),
                  p, t, cls, ('%.1f' % pct)))
    body = ('<div class="card"><h3><span class="bar"></span>Consolidated report (%d students)</h3>'
            '<div style="margin-bottom:10px"><a class="btn btn-navy btn-sm" href="/admin/reports?download=csv">'
            '⬇ Download CSV</a></div>'
            '<table><tr><th>Roll</th><th>Name</th><th>Branch</th><th>Year</th><th>Present</th>'
            '<th>Total</th><th>%%</th></tr>%s</table></div>' % (len(rows), tr))
    return admin_wrap('Reports', body, 'reports')


# ---------------------------------------------------------------- handler ---
class App(BaseHTTPRequestHandler):
    server_version = 'JNTUACEA/1.0'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    def send(self, status, body, ctype='text/html; charset=utf-8',
             extra_headers=None, filename=None):
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

    def redir(self, loc, extra=None):
        hdrs = [('Location', loc)] + (extra or [])
        self.send(303, '', extra_headers=hdrs)

    def qs(self):
        return parse_qs(urlparse(self.path).query)

    def post_fields(self):
        ln = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(ln).decode('utf-8', 'replace')
        return parse_qs(raw, keep_blank_values=True)

    def field(self, f, name, default=''):
        v = f.get(name, [''])
        return v[0].strip() if v else default

    def session_roll(self):
        from http.cookies import SimpleCookie
        ck = SimpleCookie(self.headers.get('Cookie', ''))
        tok = ck.get('sid')
        if not tok:
            return None
        row = q1("SELECT roll FROM student_sessions WHERE token=?", (tok.value,))
        return row['roll'] if row else None

    def admin_ok(self):
        from http.cookies import SimpleCookie
        ck = SimpleCookie(self.headers.get('Cookie', ''))
        return bool(ck.get('adm') and ck.get('adm').value == '1')

    def set_login(self, roll):
        tok = secrets.token_urlsafe(32)
        run("INSERT INTO student_sessions(token,roll) VALUES(?,?)", (tok, roll))
        return [('Set-Cookie', 'sid=%s; Path=/; HttpOnly; SameSite=Lax' % tok)]

    # ----- routing -----
    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith('/static/'):
            return self.serve_static(path)
        if path == '/health':
            return self.send(200, 'ok', 'text/plain')
        if path == '/':
            return self.redir('/login')
        if path == '/login':
            return self.send(200, page_login())
        if path == '/logout':
            from http.cookies import SimpleCookie
            ck = SimpleCookie(self.headers.get('Cookie', ''))
            if ck.get('sid'):
                run("DELETE FROM student_sessions WHERE token=?", (ck.get('sid').value,))
            self.send(200, page_login(), extra_headers=[('Set-Cookie', 'sid=; Path=/; Max-Age=0; HttpOnly')])
            return
        # ---- student zone
        roll = self.session_roll()
        if roll:
            if path == '/dashboard':
                notice = self.live_refresh(roll)
                return self.send(200, page_dashboard(roll, notice=notice))
            if path == '/refresh':
                notice = self.live_refresh(roll)
                return self.send(200, page_dashboard(roll, notice=notice))
            if path == '/student/print':
                return self.send(200, page_print(roll))
            return self.redir('/dashboard')
        # ---- admin zone
        if path == '/admin/login':
            return self.send(200, page_admin_login())
        if path.startswith('/admin'):
            if not self.admin_ok():
                return self.redir('/admin/login')
            if path == '/admin' or path == '/admin/':
                return self.send(200, page_admin_home())
            if path == '/admin/students':
                return self.send(200, page_admin_students())
            if path == '/admin/attendance':
                q = self.qs()
                return self.send(200, page_admin_attendance(
                    subject_id=q.get('subject_id', [''])[0], date_s=q.get('date', [''])[0]))
            if path == '/admin/reports':
                if self.qs().get('download') == ['csv']:
                    return self.csv_report()
                return self.send(200, page_admin_reports())
            if path == '/admin/logout':
                self.send(200, page_admin_login(), extra_headers=[
                    ('Set-Cookie', 'adm=; Path=/; Max-Age=0; HttpOnly')])
                return
            return self.redir('/admin')
        self.send(404, page_error('Page not found.', '/login'))

    def do_POST(self):
        path = urlparse(self.path).path
        f = self.post_fields()
        if path == '/login':
            return self.do_login(f)
        if path == '/admin/login':
            user = self.field(f, 'username')
            pw = self.field(f, 'password')
            if user == 'admin' and sha(pw) == q1("SELECT value FROM settings WHERE key='admin_pass'")['value']:
                return self.redir('/admin', [('Set-Cookie', 'adm=1; Path=/; HttpOnly; SameSite=Lax')])
            return self.send(200, page_admin_login('Invalid admin credentials.'))
        if path.startswith('/admin'):
            if not self.admin_ok():
                return self.redir('/admin/login')
            if path == '/admin/students':
                return self.import_students(f)
            if path == '/admin/attendance':
                return self.save_attendance(f)
            return self.redir('/admin')
        self.redir('/login')

    # ----- student login (official portal) -----
    def do_login(self, f):
        username = self.field(f, 'username').upper().replace(' ', '')
        password = self.field(f, 'password')
        if not username or not password:
            return self.send(200, page_login('Please enter both username and password.'))
        try:
            import scraper
            data = scraper.full_fetch(username, password)
        except ImportError:
            return self.send(200, page_login('Sync engine is not installed on this server.'))
        except scraper.PortalError as e:
            return self.send(200, page_error(str(e), '/login'))
        except Exception:
            return self.send(200, page_error(
                'Could not connect to the official portal. Please try again in a minute.', '/login'))
        store_fetch(username, data)
        if data.get('session') is not None:
            ACTIVE_SESSIONS[username] = data['session']
        return self.redir('/dashboard', self.set_login(username))

    # ----- live refresh from portal session (like the reference app) -----
    def live_refresh(self, roll):
        sess = ACTIVE_SESSIONS.get(roll)
        if sess is None:
            return ''
        try:
            import scraper
            details = scraper.get_student_details(sess)
            subjects = scraper.get_subjects(sess, details)
            rows = scraper.fetch_attendance(sess, subjects)
            store_fetch(roll, {'details': details, 'subjects': rows})
            return ''
        except Exception as e:
            msg = str(e)[:160] or 'portal unavailable'
            return ('Showing the last synced data — live refresh failed (%s). '
                    '<a href="/refresh"><b>Try again</b></a>.' % esc(msg))

    # ----- admin actions -----
    def import_students(self, f):
        txt = self.field(f, 'csv')
        lines = [l for l in txt.splitlines() if l.strip()]
        cols = None
        if lines:
            first = lines[0].lower()
            if any(k in first for k in ('roll', 'name', 'branch', 'dob', 'student')):
                heads = [h.strip().lower() for h in lines.pop(0).split(',')]
                cols = {}
                for i, h in enumerate(heads):
                    if 'roll' in h or 'ht' in h:
                        cols['roll'] = i
                    elif 'name' in h:
                        cols['name'] = i
                    elif 'branch' in h or 'dept' in h:
                        cols['branch'] = i
                    elif 'year' in h or 'sem' in h or 'class' in h:
                        cols['year'] = i
                    elif 'section' in h or 'sec' in h:
                        cols['section'] = i
                    elif 'dob' in h or 'birth' in h:
                        cols['dob'] = i
        ok, bad = 0, []
        for i, line in enumerate(lines):
            parts = [p.strip() for p in line.split(',')]
            if cols is not None:
                def g(k):
                    idx = cols.get(k)
                    return parts[idx] if idx is not None and idx < len(parts) else ''
                roll = g('roll').upper().replace(' ', '')
                name = g('name')
                branch = g('branch').upper() or 'CSE'
                year = g('year') or '1'
                section = g('section') or 'A'
                dob = g('dob')
            else:
                if len(parts) < 3:
                    continue
                roll = parts[0].upper().replace(' ', '')
                name = parts[1]
                branch = parts[2].upper()
                year = parts[3] if len(parts) > 3 else '1'
                section = parts[4] if len(parts) > 4 else 'A'
                dob = parts[5] if len(parts) > 5 else ''
            if branch not in BRANCHES:
                bl = branch.lower()
                branch = next((b for b, nm in BRANCHES.items() if nm.lower() == bl), '')
                if not branch:
                    bad.append('line %d: bad branch %s' % (i + 1, branch))
                    continue
            try:
                year = int(re.sub(r'[^0-9]', '', str(year)) or 1)
            except Exception:
                year = 1
            if not re.match(r'^[A-Z0-9]{5,20}$', roll) or not name:
                bad.append('line %d: bad roll/name' % (i + 1))
                continue
            if q1("SELECT 1 FROM students WHERE roll=?", (roll,)):
                run("UPDATE students SET name=?, branch=?, year=?, section=?, dob=? WHERE roll=?",
                    (name[:60], branch, year, section, dob, roll))
            else:
                run("INSERT INTO students(roll,name,branch,year,section,password,dob) VALUES(?,?,?,?,?,?,?)",
                    (roll, name[:60], branch, year, section, sha(roll), dob))
            ok += 1
        msg = 'Imported/updated %d students.' % ok
        if bad:
            msg += ' Skipped: ' + '; '.join(bad[:5])
        return self.send(200, page_admin_students(msg=msg))

    def save_attendance(self, f):
        subject_id = self.field(f, 'subject_id')
        date_s = self.field(f, 'date')
        subj = q1("SELECT * FROM subjects WHERE id=?", (subject_id,))
        if not subj or not date_s:
            return self.send(200, page_admin_attendance(err='Select subject and date.'))
        marks = {k[2:]: v[0] for k, v in f.items() if k.startswith('r_') and v}
        students = qall("SELECT roll FROM students WHERE branch=? AND year=? AND (section=? OR ?='')",
                        (subj['branch'], subj['year'], subj['section'], subj['section']))
        n = 0
        for srow in students:
            v = marks.get(srow['roll'], '')
            if v not in ('P', 'A'):
                continue
            run("INSERT INTO attendance(roll,subject_id,date,status,marked_by,marked_at) "
                "VALUES(?,?,?,?,'admin',?) "
                "ON CONFLICT(roll,subject_id,date) DO UPDATE SET status=excluded.status, "
                "marked_by='admin', marked_at=excluded.marked_at",
                (srow['roll'], subject_id, date_s, v, now_ist().isoformat(timespec='seconds')))
            n += 1
        return self.send(200, page_admin_attendance(
            msg='Saved %d records for %s on %s.' % (n, subj['code'], date_s),
            subject_id=subject_id, date_s=date_s))

    def csv_report(self):
        rows = qall("SELECT st.roll, st.name, st.branch, st.year, st.section, "
                    "SUM(CASE WHEN a.status='P' THEN 1 ELSE 0 END) p, COUNT(a.id) t "
                    "FROM students st LEFT JOIN attendance a ON a.roll=st.roll "
                    "GROUP BY st.roll ORDER BY st.branch, st.year, st.roll")
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(['Roll No', 'Name', 'Branch', 'Year', 'Section', 'Present', 'Total', 'Overall %'])
        for r in rows:
            p, t = r['p'] or 0, r['t'] or 0
            w.writerow([r['roll'], r['name'], r['branch'], r['year'], r['section'],
                        p, t, ('%.2f' % (p * 100.0 / t)) if t else '0.00'])
        return self.send(200, out.getvalue(), 'text/csv; charset=utf-8',
                         filename='attendance_report.csv')

    def serve_static(self, path):
        fname = os.path.basename(path)
        full = os.path.join(BASE, 'static', fname)
        if os.path.isfile(full):
            with open(full, 'rb') as fh:
                data = fh.read()
            ctype = 'image/png' if fname.endswith('.png') else 'application/octet-stream'
            return self.send(200, data, ctype, extra_headers=[('Cache-Control', 'max-age=86400')])
        self.send(404, 'not found', 'text/plain')


# ---------------------------------------------------------------- WSGI ------
class WSGIHandler(App):
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
            self._hdrs.append(('Content-Disposition', 'attachment; filename="%s"' % filename))
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
        import html as _h
        h._code = 500
        h._body = ('Server error: %s' % _h.escape(str(e))).encode('utf-8')
        h._hdrs = [('Content-Type', 'text/plain; charset=utf-8')]
    reasons = {200: 'OK', 303: 'See Other', 404: 'Not Found', 500: 'Internal Server Error'}
    start_response('%d %s' % (h._code, reasons.get(h._code, 'OK')), h._hdrs)
    return [h._body]


def main():
    db_init()
    srv = ThreadingHTTPServer(('0.0.0.0', PORT), App)
    print('JNTUACEA Attendance running on http://0.0.0.0:%d' % PORT, flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()
