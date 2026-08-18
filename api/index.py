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
                    <div class="alert alert-danger" role="alert">{{ err }}</div>
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
                </div>
                <p class="text-center mt-2" style="color:#66748f;font-size:12px">
                    We check your attendance on the official portal using your own credentials.
                    Your password is never stored.
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
  </div>
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


@app.route('/', methods=['GET', 'POST'], defaults={'path': ''})
@app.route('/api/index', methods=['GET', 'POST'], defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST'])
def index(path):
    if not SCRAPER_OK:
        return Response(
            '<pre style="white-space:pre-wrap;font-family:monospace;padding:20px">'
            'Scraper module failed to load: %s</pre>' % SCRAPER_ERR,
            mimetype='text/html', status=500)
    # Serve the logo from any rewritten path (Vercel rewrite-proof)
    if path in ('static/logo.png', 'static/logo.svg', 'api/index/static/logo.svg'):
        return Response(LOGO_SVG, mimetype='image/svg+xml')
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
                'verification right now). This blocks every app. Open the official portal '
                'directly to check, and try here again when the green status shows.'))
        return render_template_string(LOGIN_HTML, pill='', err=msg)
    except Exception:
        return render_template_string(LOGIN_HTML, pill='', err=(
            'Could not connect to the official portal. Please try again in a minute.'))

    details = data.get('details') or {}
    name = _detail_name(details) or username
    cls = details.get('classname') or details.get('Class') or ''
    acy = details.get('acad_year') or details.get('Academic Year') or ''

    rows = []
    for row in data.get('subjects', []):
        total = int(row.get('Total Days') or 0)
        present = int(row.get('No. of Present') or 0)
        pct = float(row.get('Attendance %') or 0)
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
        det_rows = ''.join(
            '<tr><td>%s</td><td><span class="badge %s">%s</span></td></tr>'
            % (_fmt_date(r.get('date', '')), 'b-p' if r.get('status') == 'P' else 'b-a',
               'Present' if r.get('status') == 'P' else 'Absent')
            for r in row.get('Details', [])[:60])
        if not det_rows:
            det_rows = '<tr><td colspan="2">No date-wise records.</td></tr>'
        if pct >= 75:
            bar = '#059669'
        elif pct >= 60:
            bar = '#D97706'
        else:
            bar = '#DC2626'
        rows.append({'card': _card(bar, bar, ('%.1f' % pct), row.get('Subject', 'Subject'),
                                   total, present, total - present,
                                   advice_cls, advice, det_rows),
                     'pct': pct})

    total_days = sum(int(r.get('Total Days') or 0) for r in data.get('subjects', []))
    total_present = sum(int(r.get('No. of Present') or 0) for r in data.get('subjects', []))
    overall = round(total_present * 100.0 / total_days, 2) if total_days else 0

    return render_template_string(
        DASH_HTML,
        initial=(name[0] if name else 'S').upper(),
        name=name.upper(),
        roll=username,
        cls=cls,
        acy=acy,
        ov_color='green' if overall >= 75 else 'red',
        overall=('%.1f' % overall),
        total_days=total_days,
        total_present=total_present,
        total_absent=total_days - total_present,
        portal=PORTAL_URL,
        n_subjects=len(rows),
        cards=''.join(r['card'] for r in rows),
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '8020')), debug=False)
