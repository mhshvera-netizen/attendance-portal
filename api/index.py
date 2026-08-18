#!/usr/bin/env python3
"""
JNTUACEA Attendance — Vercel edition (Flask, stateless serverless).
Student flow exactly like the popular JNTUA attendance app:
  login page (official portal look) -> POST -> portal login + fetch ->
  dashboard with name, roll, class, overall %, subject-wise cards,
  skip/attend advice and date-wise details — all in ONE response.
"""

from flask import Flask, request, render_template_string, Response

import os
import re
import sys
import traceback

# Vercel serverless: ensure this file's directory is on sys.path so that
# the sibling scraper module can be imported reliably.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import scraper
    SCRAPER_OK = True
except Exception as _e:
    SCRAPER_OK = False
    SCRAPER_ERR = repr(_e)

APK_B64 = '''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AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA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'''


app = Flask(__name__)

PORTAL_URL = 'https://jntuaceastudents.classattendance.in/'


@app.errorhandler(500)
def internal_error(e):
    """Show the real error instead of a blank 500 (for fast debugging)."""
    tb = traceback.format_exc()
    return ('<pre style="white-space:pre-wrap;font-family:monospace;padding:20px">'
            '500 INTERNAL SERVER ERROR\n\n%s</pre>' % tb), 500


@app.route('/api/health')
def health():
    return 'ok scraper=%s' % SCRAPER_OK

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


@app.route('/static/logo.svg')
def logo():
    return Response(LOGO_SVG, mimetype='image/svg+xml')


# ---------------------------------------------------------------- login ----
LOGIN_HTML = '''<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>JNTUACEA - Academic Record Book</title>
    <link rel="icon" href="/static/logo.svg" type="image/svg+xml" />
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet" />
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons/font/bootstrap-icons.css" rel="stylesheet" />
    <style type="text/css">
        html { position: relative; min-height: 100%; }
        body { margin-bottom: 60px; background-color: #F5F3EE; }
        .footer { position: absolute; bottom: 0; width: 100%; height: 60px; background-color: #f5f5f5; }
        .container .text-muted { margin: 20px 0; }
        .responsive-text { font-size: 1.3em; }
        .responsive-text2 { font-size: 1em; }
        .responsive-img { max-width: 100px; max-height: 100px; border-radius: 50%; }
        @media (max-width: 576px) {
            .responsive-text { font-size: 0.76em; }
            .responsive-text2 { font-size: 0.6em; }
            .responsive-img { max-width: 50px; max-height: 50px; }
        }
        .pill { border-radius: 10px; padding: 9px 13px; font-size: 13px; font-weight: 600; margin-bottom: 14px; }
        .pill.green { background: #E8F7EE; border: 1px solid #BFE6CF; color: #16603A; }
        .pill.red { background: #FDE8E8; border: 1px solid #F2C4C4; color: #9B1C1C; }
        .pill.gray { background: #EEF1F6; border: 1px solid #DFE4EC; color: #66748f; }
        .pill a { font-weight: 800; text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container-fluid bg-white p-3">
        <div class="container d-flex justify-content-center">
            <div class="row align-items-center">
                <div class="col-auto">
                    <img src="/static/logo.svg" alt="JNTUACEA" class="img-fluid responsive-img" />
                </div>
                <div class="col-auto p-0">
                    <span class="text-primary d-block responsive-text p-0"><b>JNTUA College of Engineering Ananthapuramu</b></span>
                    <span class="text-primary d-block responsive-text2 p-0">(Accredited by NAAC with &rsquo;A&rsquo; Grade)</span>
                    <span class="text-success d-block responsive-text"><b>Student Academic Record Book</b></span>
                </div>
            </div>
        </div>
    </div>
    <div class="container">
        <br />
        <div class="row">
            <div class="col-sm-3"></div>
            <div class="col-sm-6">
                <div class="card mt-3 p-4">
                    <h4>Login</h4>
                    <br />
                    {{ pill|safe }}
                    {% if err %}
                    <div class="alert alert-danger" role="alert">{{ err|safe }}</div>
                    {% endif %}
                    <form action="/" method="post" id="loginForm">
                        <div class="mb-3">
                            <div class="input-group">
                                <span class="input-group-text"><i class="bi bi-person"></i></span>
                                <input type="text" name="username" placeholder="Enter Username" required class="form-control" maxlength="32" />
                            </div>
                        </div>
                        <div class="mb-3">
                            <div class="input-group">
                                <span class="input-group-text"><i class="bi bi-lock"></i></span>
                                <input type="password" name="password" placeholder="Enter Password" required class="form-control" maxlength="32" />
                            </div>
                        </div>
                        <div class="d-grid">
                            <input type="submit" value="Login" class="btn btn-success" />
                        </div>
                    </form>
                    <div class="d-grid mt-2">
                        <a href="/entry" class="btn btn-outline-secondary">&#9998; Enter attendance manually instead</a>
                    </div>
                </div>
                <p class="text-center mt-2" style="color:#66748f;font-size:12px">
                    We check your attendance on the official portal using your own credentials.
                    Your password is never stored.
                </p>
                <p class="text-center mt-1" style="font-size:13px">
                    &#128241; <a href="/static/JNTUACEA-Attendance.apk" style="font-weight:700">Download the Android App (APK)</a>
                    &mdash; login inside it, then tap the &#128202; Attendance button for your
                    overall % and subject-wise %.
                </p>
            </div>
            <div class="col-sm-3"></div>
        </div>
        <br />
    </div>
    <div class="footer">
        <div class="container">
            <div class="row">
                <div class="col-sm-6"><br /> <span class="text-success">&copy; JNTUACEA - All rights reserved.</span></div>
            </div>
        </div>
    </div>
</body>
</html>'''

# ------------------------------------------------------------- dashboard ----
DASH_HTML = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Attendance Result — JNTUACEA</title>
<link rel="icon" href="/static/logo.svg" type="image/svg+xml">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#F4F6F9;--card:#fff;--border:#E5E9F0;--ink:#1A1F2E;--muted:#8892A0;
--green:#059669;--red:#DC2626;--amber:#D97706;--navy:#123a6b;--gold:#f0b429}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,Arial,sans-serif;
background:#F5F3EE;color:var(--ink);min-height:100vh;-webkit-font-smoothing:antialiased}
a{text-decoration:none;color:var(--navy)}
.page{max-width:860px;margin:0 auto;padding:24px 16px 60px}
.site-header{margin-bottom:26px}
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
.stat-row{display:flex;gap:22px;margin-top:20px;flex-wrap:wrap;align-items:center}
.stat{display:flex;flex-direction:column;gap:2px}
.stat-val{font-size:1.5rem;font-weight:800;letter-spacing:-.5px;line-height:1}
.stat-val.green{color:var(--green)}.stat-val.red{color:var(--red)}
.stat-label{font-size:.62rem;font-weight:600;letter-spacing:.7px;text-transform:uppercase;color:var(--muted)}
.stat-sep{width:1px;height:26px;background:var(--border)}
.action-row{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;margin:20px 0 26px}
.btn{display:inline-flex;align-items:center;gap:6px;font-size:.78rem;font-weight:700;padding:8px 16px;
border-radius:9px;border:1px solid var(--border);background:var(--card);color:#374151;cursor:pointer}
.btn:hover{background:var(--bg);transform:translateY(-1px);box-shadow:0 3px 10px rgba(0,0,0,.07)}
.btn-navy{background:var(--navy);color:#fff;border-color:var(--navy)}
.section-head{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.sh-label{font-size:.6rem;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;color:var(--muted);white-space:nowrap}
.sh-line{flex:1;height:1px;background:var(--border)}
.sh-badge{font-size:.64rem;font-weight:700;padding:3px 9px;border-radius:20px;background:#EFF6FF;color:#1D4ED8;border:1px solid #BFDBFE}
.search-wrap{max-width:340px;margin-bottom:16px}
#subject-search{width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:9px;
background:var(--card);font-size:.8rem;outline:none}
#subject-search:focus{border-color:#A78BFA;box-shadow:0 0 0 3px rgba(167,139,250,.15)}
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
.footer{margin-top:30px;text-align:center;color:var(--muted);font-size:11.5px;padding:16px}
@media print{.action-row,.search-wrap,.eyebrow{display:none!important}body{background:#fff}}
@media(max-width:600px){.page{padding:16px 10px 50px}.subj-inner{padding:12px}}
</style>
</head>
<body>
<div class="page">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
    <a class="btn" href="/">&larr; Logout</a>
    <button class="btn" onclick="window.print()">&#128424; Print</button>
  </div>
  <div class="site-header">
    <div class="eyebrow"><span class="eyebrow-dot"></span>Live attendance &middot; Official portal synced</div>
    <div class="header-row">
      <div class="avatar">{{ initial }}</div>
      <div class="header-text"><h1>{{ name }}</h1>
        <div class="uid">{{ roll }} &nbsp;&middot;&nbsp; {{ cls }}{% if acy %} &nbsp;&middot;&nbsp; {{ acy }}{% endif %}</div>
      </div>
    </div>
    <div class="stat-row">
      <div class="stat"><div class="stat-val {{ ov_color }}">{{ overall }}%</div><div class="stat-label">Overall Attendance</div></div>
      <div class="stat-sep"></div>
      <div class="stat"><div class="stat-val">{{ total_days }}</div><div class="stat-label">Total Classes</div></div>
      <div class="stat-sep"></div>
      <div class="stat"><div class="stat-val green">{{ total_present }}</div><div class="stat-label">Present</div></div>
      <div class="stat-sep"></div>
      <div class="stat"><div class="stat-val red">{{ total_absent }}</div><div class="stat-label">Absent</div></div>
    </div>
  </div>
  <div class="action-row">
    <a class="btn btn-navy" href="/">&#128260; Re-check</a>
    <a class="btn" href="{{ portal }}" target="_blank" rel="noopener">Official Portal &#8599;</a>
    <a class="btn" href="/entry">&#9998; Enter Totals</a>
  </div>
  {% if note %}<div class="alert alert-info" style="font-size:13.5px;margin:0 0 14px">{{ note|safe }}</div>{% endif %}
  <div class="section-head"><span class="sh-label">Subjects</span><span class="sh-line"></span>
    <span class="sh-badge">{{ n_subjects }} subjects</span></div>
  <div class="search-wrap"><input id="subject-search" placeholder="Search subjects&hellip;"
    onkeyup="var v=this.value.toLowerCase();document.querySelectorAll('.subj-card').forEach(function(c){c.style.display=c.innerText.toLowerCase().includes(v)?'':'none'})"></div>
  {{ cards|safe }}
  <div class="footer">&copy; JNTUACEA - All rights reserved &middot; Data fetched from the official portal with your own credentials</div>
</div>
</body>
</html>'''


def _detail_name(details):
    for key in ('Student Name', 'Name', 'student_name'):
        if details.get(key):
            return str(details[key]).strip()
    for k, v in details.items():
        if 'name' in k.lower() and v:
            return str(v).strip()
    return ''


def parse_totals(text):
    """Parse subject lines: 'Operating Systems 36/40', 'DBMS total 40 present 36',
    'Data Structures 40 36' -> [{'name','total','present'}]"""
    rows = []
    for line in (text or '').splitlines():
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
        name = re.sub(r'\d{1,3}\s*/\s*\d{1,3}', ' ', line)
        name = re.sub(r'(?i)total\s*[=:]?\s*\d{1,3}', ' ', name)
        name = re.sub(r'(?i)present\s*[=:]?\s*\d{1,3}', ' ', name)
        name = re.sub(r'\d{1,3}', ' ', name)
        name = name.strip(' :;,-.|')
        if not name or len(name) < 2 or not (1 <= present <= total <= 600):
            continue
        rows.append({'name': name, 'total': total, 'present': present})
    return rows


# ------------------------------------------------------------ manual entry --
ENTRY_HTML = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Enter Attendance — JNTUACEA</title>
<link rel="icon" href="/static/logo.svg" type="image/svg+xml">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
  body { background-color: #F5F3EE; }
  .card { margin-top: 14px; }
  textarea { font-family: monospace; font-size: 14px; }
</style>
</head>
<body>
<div class="container-fluid bg-white p-3">
  <div class="container d-flex justify-content-center">
    <div class="row align-items-center">
      <div class="col-auto"><img src="/static/logo.svg" alt="JNTUACEA" class="img-fluid" style="max-width:80px;border-radius:50%"></div>
      <div class="col-auto p-0">
        <span class="text-primary d-block" style="font-size:1.05em"><b>JNTUA College of Engineering Ananthapuramu</b></span>
        <span class="text-primary d-block" style="font-size:0.85em">(Accredited by NAAC with &rsquo;A&rsquo; Grade)</span>
        <span class="text-success d-block" style="font-size:1.05em"><b>Student Academic Record Book</b></span>
      </div>
    </div>
  </div>
</div>
<div class="container" style="max-width:720px">
  <div class="card mt-3 p-4">
    <h4>Quick Entry — Enter Your Attendance</h4>
    <br>
    <div class="alert alert-info" style="font-size:14px">
      <b>2-minute way that always works.</b> Open the
      <a href="https://jntuaceastudents.classattendance.in/" target="_blank" rel="noopener"><b>official portal &#8599;</b></a>
      on your phone, look at each subject, and type the numbers below —
      one subject per line: <b>Subject Name &nbsp;Present/Total</b>.
      <br>Example: <code>Operating Systems 36/40</code> &nbsp;or&nbsp;
      <code>DBMS total 40 present 36</code>
    </div>
    {% if err %}<div class="alert alert-danger">{{ err }}</div>{% endif %}
    <form action="/entry" method="post">
      <div class="mb-3">
        <label class="form-label"><b>Roll Number</b></label>
        <input type="text" class="form-control" name="roll" id="roll" required placeholder="e.g. 23001A0204">
      </div>
      <div class="mb-3">
        <label class="form-label"><b>Your Name</b></label>
        <input type="text" class="form-control" name="name" id="name" placeholder="e.g. Sai Kumar">
      </div>
      <div class="mb-3">
        <label class="form-label"><b>Subjects (one per line)</b></label>
        <textarea class="form-control" name="subjects" id="subjects" rows="9" required
          placeholder="Operating Systems 36/40&#10;Database Management Systems 35/40&#10;Probability and Statistics 25/40"></textarea>
      </div>
      <div class="d-grid">
        <button type="submit" class="btn btn-success btn-lg">Show My Attendance</button>
      </div>
    </form>
    <p class="text-center mt-3" style="color:#66748f;font-size:12px">
      Your numbers are saved only on this device (browser storage) — we never store them on a server.
      <a href="/">&larr; Back to login</a>
    </p>
  </div>
</div>
<script>
  // remember on this device
  try {
    var saved = localStorage.getItem('jntuacea_totals');
    if (saved) {
      var d = JSON.parse(saved);
      if (d.roll && !document.getElementById('roll').value) document.getElementById('roll').value = d.roll;
      if (d.name) document.getElementById('name').value = d.name;
      if (d.subjects) document.getElementById('subjects').value = d.subjects;
    }
  } catch (e) {}
  document.querySelector('form').addEventListener('submit', function () {
    try {
      localStorage.setItem('jntuacea_totals', JSON.stringify({
        roll: document.getElementById('roll').value.trim().toUpperCase(),
        name: document.getElementById('name').value.trim(),
        subjects: document.getElementById('subjects').value
      }));
    } catch (e) {}
  });
</script>
</body>
</html>'''


def _fmt_date(s):
    import datetime as _dt
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%d-%b-%Y', '%d %b %Y'):
        try:
            return _dt.datetime.strptime(s.strip(), fmt).strftime('%d %b %Y')
        except Exception:
            pass
    return s


def _card(bar, pct_color, pct, name, total, present, absent, advice_cls, advice, det_rows):
    return ('<div class="subj-card"><div class="card-bar" style="background:%s"></div>'
            '<div class="subj-inner">'
            '<div class="pct-block"><div class="pct-num" style="color:%s">%s%%</div>'
            '<div class="pct-cap">Attendance</div></div>'
            '<div class="subj-main"><div class="subj-name">%s</div>'
            '<div class="subj-meta"><span>Total: <b>%d</b></span>'
            '<span>Present: <b style="color:var(--green)">%d</b></span>'
            '<span>Absent: <b style="color:var(--red)">%d</b></span></div>'
            '<div class="subj-advice %s">%s</div></div>'
            '<details><summary>&#128203; Date-wise details</summary>'
            '<table class="det-table"><tr><th>Date</th><th>Status</th></tr>%s</table></details>'
            '</div></div>'
            % (bar, pct_color, pct, name, total, present, absent, advice_cls, advice, det_rows))


def build_dashboard(name, roll, cls, acy, rows_data, note=''):
    """rows_data: list of dicts {Subject, Total Days, No. of Present, Details} —
    exactly the shape the portal scraper returns."""
    cards = []
    for row in rows_data:
        total = int(row.get('Total Days') or 0)
        present = int(row.get('No. of Present') or 0)
        pct = float(row.get('Attendance %') or 0)
        if total:
            pct = round(present * 100.0 / total, 1)
        if total == 0:
            can_skip = need = 0
        elif pct >= 75:
            can_skip = max(0, int(present / 0.75 - total))
            need = 0
        else:
            can_skip = 0
            need = max(0, int((0.75 * total - present) / 0.25))
        if total == 0:
            advice_cls, advice = 'adv-neutral', 'No classes recorded yet.'
        elif pct >= 75:
            if can_skip > 0:
                advice_cls, advice = 'adv-good', ('You can skip up to <b>%d</b> more classes '
                                                  'and stay above 75%%.' % can_skip)
            else:
                advice_cls, advice = 'adv-good', 'You are safely above 75%.'
        else:
            advice_cls, advice = 'adv-bad', ('Attend the next <b>%d</b> classes to get back '
                                             'above 75%%.' % max(1, need))
        det = row.get('Details') or []
        if det:
            det_rows = ''.join(
                '<tr><td>%s</td><td><span class="badge %s">%s</span></td></tr>'
                % (_fmt_date(r.get('date', '')), 'b-p' if r.get('status') == 'P' else 'b-a',
                   'Present' if r.get('status') == 'P' else 'Absent')
                for r in det[:60])
        else:
            det_rows = ('<tr><td colspan="2">Totals entered manually — open the official '
                        'portal for date-wise details, or '
                        '<a href="/entry">update these totals</a>.</td></tr>')
        if pct >= 75:
            bar = '#059669'
        elif pct >= 60:
            bar = '#D97706'
        else:
            bar = '#DC2626'
        cards.append(_card(bar, bar, ('%.1f' % pct), row.get('Subject', 'Subject'),
                           total, present, total - present, advice_cls, advice, det_rows))
    total_days = sum(int(r.get('Total Days') or 0) for r in rows_data)
    total_present = sum(int(r.get('No. of Present') or 0) for r in rows_data)
    overall = round(total_present * 100.0 / total_days, 2) if total_days else 0
    return render_template_string(
        DASH_HTML,
        initial=(name[0] if name else 'S').upper(),
        name=name.upper(),
        roll=roll,
        cls=cls or '',
        acy=acy or '',
        ov_color='green' if overall >= 75 else 'red',
        overall=('%.1f' % overall),
        total_days=total_days,
        total_present=total_present,
        total_absent=total_days - total_present,
        portal=PORTAL_URL,
        n_subjects=len(cards),
        cards=''.join(cards),
        note=note,
    )


def entry_logic():
    """Shared handler for the manual-entry flow (works from /entry and from
    the Vercel rewrite path /api/index/entry)."""
    if request.method == 'GET':
        return render_template_string(ENTRY_HTML, err='')
    roll = (request.form.get('roll') or '').strip().upper().replace(' ', '')
    name = (request.form.get('name') or '').strip() or roll
    rows = parse_totals(request.form.get('subjects') or '')
    if not rows:
        return render_template_string(ENTRY_HTML, err=(
            'No valid lines found. Type one subject per line like: '
            'Operating Systems 36/40'))
    if not re.match(r'^[A-Z0-9]{5,20}$', roll):
        return render_template_string(ENTRY_HTML, err='Please enter a valid roll number.')
    rows_data = [{'Subject': r['name'], 'Total Days': r['total'],
                  'No. of Present': r['present'], 'No. of Absent': r['total'] - r['present'],
                  'Attendance %': round(r['present'] * 100.0 / r['total'], 1),
                  'Details': []} for r in rows]
    return build_dashboard(name, roll, '', '', rows_data,
                           note='Totals entered by you — saved only on this device. '
                                '<a href="/entry" style="font-weight:700">Update totals</a> '
                                'anytime, or try <a href="/" style="font-weight:700">auto sync</a> '
                                'when the portal is open.')


@app.route('/entry', methods=['GET', 'POST'], defaults={'path': ''})
@app.route('/entry/<path:path>', methods=['GET', 'POST'])
def entry(path):
    return entry_logic()


@app.route('/', methods=['GET', 'POST'], defaults={'path': ''})
@app.route('/api/index', methods=['GET', 'POST'], defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST'])
def index(path):
    if path and 'health' in path:
        return Response('ok scraper=%s' % SCRAPER_OK, mimetype='text/plain')
    if not SCRAPER_OK:
        return Response(
            '<pre style="white-space:pre-wrap;font-family:monospace;padding:20px">'
            'Scraper module failed to load: %s</pre>' % SCRAPER_ERR,
            mimetype='text/html', status=500)
    # Serve the logo from any rewritten path (Vercel rewrite-proof)
    if path and 'logo' in path:
        return Response(LOGO_SVG, mimetype='image/svg+xml')
    # Serve the Android APK (embedded bytes — rewrite-proof)
    if path and 'apk' in path:
        import base64
        return Response(base64.b64decode(APK_B64),
                        mimetype='application/vnd.android.package-archive',
                        headers={'Content-Disposition':
                                 'attachment; filename="JNTUACEA-Attendance.apk"'})
    if 'entry' in (path or ''):
        return entry_logic()
    if request.method == 'GET':
        st = scraper.portal_status()
        if st == 'open':
            pill = ('<div class="pill green">&#128994; Official portal is open &mdash; '
                    'attendance check works now.</div>')
        elif st == 'captcha':
            pill = ('<div class="pill red">&#128308; The official portal has enabled its '
                    'human-verification (CAPTCHA) right now &mdash; this blocks every app. '
                    '<a href="%s" target="_blank" rel="noopener" style="color:#9B1C1C">'
                    'Open the official portal directly &#8599;</a> and check there. '
                    'Come back when this turns green.</div>' % PORTAL_URL)
        else:
            pill = ('<div class="pill gray">Checking the official portal status&hellip; '
                    'it may be temporarily unreachable.</div>')
        return render_template_string(LOGIN_HTML, pill=pill, err='')

    username = (request.form.get('username') or '').strip().upper().replace(' ', '')
    password = (request.form.get('password') or '').strip()
    if not username or not password:
        return render_template_string(LOGIN_HTML, pill='', err='Please enter both username and password.')
    try:
        data = scraper.full_fetch(username, password)
    except scraper.PortalError as e:
        msg = str(e)
        if 'CAPTCHA' in msg or 'Use https' in msg or 'rejected login' in msg:
            return render_template_string(LOGIN_HTML, pill='', err=(
                'The official portal blocked the automated login (it is showing a human '
                'verification right now). This blocks every app &mdash; the other student '
                'app is paused too. Instead use '
                '<a href="/entry" style="font-weight:800">&#9998; Enter attendance manually</a> '
                '(2 minutes, always works).'))
        if 'Failed to load' in msg or 'no subjects' in msg or 'route' in msg:
            return render_template_string(LOGIN_HTML, pill='', err=(
                'Your credentials were accepted, but this college portal copy is missing the '
                'attendance pages (the portal runs multiple incomplete copies). Use '
                '<a href="/entry" style="font-weight:800">&#9998; Enter attendance manually</a> '
                '&mdash; open the official portal on your phone, read the numbers, type them here.'))
        return render_template_string(LOGIN_HTML, pill='', err=msg)
    except Exception:
        return render_template_string(LOGIN_HTML, pill='', err=(
            'Could not connect to the official portal. Please try again in a minute, or '
            '<a href="/entry" style="font-weight:800">&#9998; Enter attendance manually</a>.'))

    details = data.get('details') or {}
    name = _detail_name(details) or username
    cls = details.get('classname') or details.get('Class') or ''
    acy = details.get('acad_year') or details.get('Academic Year') or ''
    return build_dashboard(name, username, cls, acy, data.get('subjects', []),
                           note='Live data fetched from the official portal with your own credentials. '
                                'If the portal later blocks sync, use &#9998; Enter Totals.')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '8020')), debug=False)
