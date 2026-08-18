#!/usr/bin/env python3
"""
JNTUACEA Attendance — landing page (friend-style)
Serves the "App is Now Available" page with the Android APK download,
exactly like the popular JNTUA student attendance app did after the
portal's security updates.
"""

import os
import sys
from flask import Flask, render_template_string, Response, redirect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

APK_FILENAME = 'JNTUA-Attendance-Application.apk'
APK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', 'downloads', APK_FILENAME)

LANDING = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JNTUACEA Attendance App for Android</title>
<style>
:root{--blue:#0b4db9;--blue-deep:#06357f;--sky:#eaf4ff;--ink:#10213d;
--muted:#63728a;--line:rgba(24,81,166,.14);--white:#fff}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;min-width:320px;color:var(--ink);font:16px/1.6 Inter,ui-sans-serif,
system-ui,-apple-system,"Segoe UI",sans-serif;background:#f6f9fe;overflow-x:hidden}
body::before,body::after{content:"";position:fixed;z-index:-1;border-radius:50%;
filter:blur(8px);pointer-events:none}
body::before{width:38rem;height:38rem;background:rgba(66,153,255,.22);top:-16rem;left:-12rem}
body::after{width:30rem;height:30rem;background:rgba(16,74,181,.13);right:-12rem;top:19rem}
a{color:inherit}
.container{width:min(1120px,calc(100% - 40px));margin:auto}
.nav{display:flex;align-items:center;justify-content:space-between;padding:23px 0}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none;font-weight:800;letter-spacing:-.02em}
.brand-mark{display:grid;place-items:center;width:38px;height:38px;border-radius:12px;color:white;
background:linear-gradient(135deg,#1171e9,#073d92);box-shadow:0 8px 16px rgba(11,77,185,.25)}
.nav-link{color:var(--blue);font-weight:700;text-decoration:none;font-size:.92rem}
.hero{min-height:610px;display:grid;grid-template-columns:1.05fr .95fr;align-items:center;gap:56px;padding:54px 0 76px}
.eyebrow{display:inline-flex;align-items:center;gap:8px;margin-bottom:16px;padding:7px 12px;
border:1px solid var(--line);border-radius:999px;color:var(--blue);
background:rgba(255,255,255,.66);font-size:.78rem;font-weight:800}
.eyebrow span{width:7px;height:7px;border-radius:50%;background:#36b96d;box-shadow:0 0 0 4px rgba(54,185,109,.18)}
h1{font-size:clamp(2.1rem,5vw,3.2rem);line-height:1.08;letter-spacing:-.03em;margin:0 0 16px}
.hero p.sub{color:var(--muted);font-size:1.05rem;max-width:480px;margin:0 0 30px}
.btn{display:inline-flex;align-items:center;gap:10px;padding:14px 26px;border-radius:12px;
background:linear-gradient(135deg,#1171e9,#073d92);color:#fff;font-weight:800;
text-decoration:none;box-shadow:0 12px 26px rgba(11,77,185,.35);font-size:1rem}
.btn:hover{transform:translateY(-1px)}
.btn .ico{font-size:1.2rem}
.hero-visual{background:var(--white);border:1px solid var(--line);border-radius:22px;
padding:26px;box-shadow:0 24px 60px rgba(11,77,185,.12)}
.phone{max-width:230px;margin:auto;text-align:center}
.phone .scr{border:8px solid #10213d;border-radius:22px;padding:14px;background:#f6f9fe}
.phone .pct{font-size:2.4rem;font-weight:800;color:#059669}
.phone .lbl{font-size:.62rem;letter-spacing:1.4px;color:var(--muted);font-weight:800;text-transform:uppercase}
.phone .subj{margin-top:12px;text-align:left;background:#fff;border:1px solid var(--line);
border-radius:10px;padding:9px 11px;font-size:.74rem}
.phone .subj b{display:block;font-size:.8rem}
.notice{background:var(--white);border:1px solid var(--line);border-radius:16px;padding:26px;margin:34px 0}
.notice h2{margin:0 0 8px;font-size:1.25rem}
.notice p{color:var(--muted);margin:0}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:26px 0}
.step{background:var(--white);border:1px solid var(--line);border-radius:14px;padding:18px}
.step .n{display:grid;place-items:center;width:30px;height:30px;border-radius:10px;
background:var(--sky);color:var(--blue);font-weight:800;margin-bottom:10px}
.step h3{margin:0 0 4px;font-size:.98rem}
.step p{margin:0;color:var(--muted);font-size:.88rem}
.faq{background:var(--white);border:1px solid var(--line);border-radius:16px;padding:26px;margin:30px 0}
.faq h2{margin:0 0 14px;font-size:1.25rem}
.faq .q{font-weight:800;margin:14px 0 4px;font-size:.95rem}
.faq .a{color:var(--muted);font-size:.9rem;margin:0}
.cta{text-align:center;padding:44px 0 60px}
.cta h2{font-size:1.6rem;margin:0 0 10px}
.cta p{color:var(--muted);margin:0 0 22px}
footer{border-top:1px solid var(--line);padding:26px 0;color:var(--muted);font-size:.85rem;
display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px}
@media(max-width:860px){.hero{grid-template-columns:1fr;min-height:0;gap:34px}
.phone .scr{max-width:200px;margin:auto}}
</style>
</head>
<body>
<div class="container">
  <nav class="nav">
    <a class="brand" href="/"><span class="brand-mark">&#127891;</span> JNTUACEA Attendance</a>
    <a class="nav-link" href="#install">How to install</a>
  </nav>

  <section class="hero">
    <div>
      <span class="eyebrow"><span></span> ANDROID APP &middot; v1.0.0</span>
      <h1>JNTUACEA Attendance App is Now Available</h1>
      <p class="sub">To ensure uninterrupted attendance access after recent
      security updates on the college portal, we have launched an official
      Android application.</p>
      <a class="btn" href="/downloads/{{ apk }}">
        <span class="ico">&#8681;</span> Download APK{% if size %} &middot; {{ size }}{% endif %}
      </a>
    </div>
    <div class="hero-visual">
      <div class="phone">
        <div class="scr">
          <div class="lbl">Overall Attendance</div>
          <div class="pct">78.6%</div>
          <div class="subj"><b>Power System Operation</b>81.8% &middot; Skip 1 class</div>
          <div class="subj"><b>Electrical Distribution</b>83.3% &middot; Skip 1 class</div>
          <div class="subj"><b>Industrial Safety</b>85.0% &middot; Skip 2 classes</div>
        </div>
      </div>
    </div>
  </section>

  <div class="notice" id="install">
    <h2>Important notice</h2>
    <p>Due to recent security changes implemented on the JNTUACEA portal,
    attendance services are now accessible through the Android application.
    Your overall attendance percentage and subject-wise attendance with the
    75% rule (skip / attend calculations) are available inside the app.</p>
  </div>

  <h2>How to Install</h2>
  <p style="color:var(--muted)">It only takes a minute to get started.</p>
  <div class="steps">
    <div class="step"><div class="n">1</div><h3>Download APK</h3>
      <p>Click the Download APK button above.</p></div>
    <div class="step"><div class="n">2</div><h3>Allow installs</h3>
      <p>If prompted, enable &ldquo;Install from Unknown Sources&rdquo;.</p></div>
    <div class="step"><div class="n">3</div><h3>Open the APK</h3>
      <p>Open the downloaded APK file from your downloads.</p></div>
    <div class="step"><div class="n">4</div><h3>Install &amp; launch</h3>
      <p>Install, launch the app and login with your JNTUACEA credentials.</p></div>
  </div>

  <div class="faq">
    <h2>Frequently asked questions</h2>
    <p class="q">Is this app for JNTUACEA students?</p>
    <p class="a">Yes, it is developed specifically for JNTUACEA (JNTUA College of
    Engineering Ananthapuramu) students.</p>
    <p class="q">Are my credentials safe?</p>
    <p class="a">Yes, credentials are securely transmitted to the official college
    portal and not stored unnecessarily.</p>
    <p class="q">Will the website work again?</p>
    <p class="a">Future web support updates will be announced.</p>
  </div>

  <div class="cta">
    <h2>Ready to check your attendance?</h2>
    <p>Download JNTUACEA Attendance App v1.0.0 for Android 8.0 and above.</p>
    <a class="btn" href="/downloads/{{ apk }}"><span class="ico">&#8681;</span> Download APK{% if size %} &middot; {{ size }}{% endif %}</a>
  </div>

  <footer>
    <span>&copy; 2026 JNTUACEA Attendance. All rights reserved.</span>
    <span>Secure session &middot; jntuaceastudents.classattendance.in</span>
  </footer>
</div>
</body>
</html>'''


@app.route('/api/health')
def health():
    return 'ok'


@app.route('/', defaults={'path': ''})
@app.route('/api/index', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    size = None
    if os.path.isfile(APK_PATH):
        size = '%.1f MB' % (os.path.getsize(APK_PATH) / (1024 * 1024))
    return render_template_string(LANDING, apk=APK_FILENAME, size=size)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '8020')), debug=False)
