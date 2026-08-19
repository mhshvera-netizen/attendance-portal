#!/usr/bin/env python3
"""The in-browser attendance checker - ONE clean flow.

  1. LOGIN    - username + password (saved on this device)
  2. SYNCING  - "Reading your semester" with progress
  3. DASHBOARD - OVERALL % + SUBJECT-WISE % + tap subject for log

Behaviour:
  * saved credentials + portal open  -> syncs on page load (one attempt)
  * portal CAPTCHA ON                -> no auto-retry; user taps
    Paste & Calculate (100% works) or pastes the record manually.
  * Browser Helper bookmarklet       -> dashboard inside the portal page.
"""

try:
    import requests  # noqa
    from bs4 import BeautifulSoup  # noqa
    HAS_SCRAPER = True
except Exception:
    HAS_SCRAPER = False

APP_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Check Your Attendance - JNTUACEA</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#1171e9">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#f6f9fe;--card:#fff;--ink:#10213d;--muted:#63728a;--blue:#1171e9;
--green:#059669;--red:#DC2626;--amber:#D97706;--line:#e3ecf7}
body{font-family:-apple-system,'Segoe UI',system-ui,Arial,sans-serif;background:var(--bg);
color:var(--ink);min-height:100vh;line-height:1.5}
.wrap{max-width:640px;margin:0 auto;padding:22px 14px 60px}
.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.top .brand{font-weight:800;color:var(--blue)}
.top a{font-size:13px;font-weight:700;color:var(--blue);text-decoration:none}
h1{font-size:23px;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:13.5px;margin-top:4px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin:14px 0}
label{display:block;font-size:11px;font-weight:800;color:var(--muted);letter-spacing:.4px;margin:10px 0 4px}
input,textarea{width:100%;padding:11px 12px;border:1.5px solid var(--line);border-radius:10px;
font-size:14px;color:var(--ink);background:#fff;outline:none;font-family:inherit}
input:focus,textarea:focus{border-color:var(--blue)}
textarea{min-height:110px}
.btn{display:block;width:100%;padding:13px;border:none;border-radius:12px;background:var(--blue);
color:#fff;font-size:15px;font-weight:800;cursor:pointer;margin-top:14px;text-align:center;text-decoration:none}
.btn.green{background:var(--green)}
.msg{display:none;padding:10px 13px;border-radius:10px;font-size:13px;margin-top:10px}
.msg.err{display:block;background:#FDE8E8;color:#9B1C1C;border:1px solid #F2C4C4}
.msg.ok{display:block;background:#E7F6EF;color:#046C4E;border:1px solid #BFE6CF}
.status{display:none;padding:11px 14px;border-radius:12px;font-size:13.5px;font-weight:700;margin-top:12px}
.status.red{display:block;background:#FDE8E8;color:#9B1C1C;border:1px solid #F2C4C4}
.status.green{display:block;background:#E7F6EF;color:#046C4E;border:1px solid #BFE6CF}
.status.gray{display:block;background:#EEF1F6;color:#66748f;border:1px solid #DFE4EC}
.links{text-align:center;margin-top:14px;font-size:12.5px}
.links a{color:var(--blue);font-weight:700;text-decoration:none}
#syncOverlay{display:none;position:fixed;inset:0;background:var(--bg);z-index:50;
text-align:center;padding-top:64px}
#syncOverlay .big{font-size:42px}
#syncOverlay .t1{font-size:26px;font-weight:800;letter-spacing:3px;margin-top:14px;color:var(--ink)}
#syncOverlay .t2{color:var(--muted);margin-top:6px;font-size:14px}
#syncOverlay .step{margin-top:22px;font-size:16px;font-weight:700;color:var(--blue)}
#syncOverlay .bar{max-width:280px;margin:12px auto 0;height:8px;background:var(--line);border-radius:6px;overflow:hidden}
#syncOverlay .bar div{width:0%;height:100%;background:linear-gradient(90deg,#1171e9,#073d92);border-radius:6px;transition:width .3s}
#syncOverlay .foot{margin-top:24px;font-size:11px;color:var(--muted)}
.d-name{font-size:21px;font-weight:800;text-transform:uppercase}
.d-roll{color:var(--muted);font-size:13px;margin-top:2px}
.ovcard{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;
text-align:center;margin:14px 0}
.ov-label{font-size:10.5px;font-weight:800;letter-spacing:1.4px;color:var(--muted)}
.ov-pct{font-size:46px;font-weight:800;line-height:1.1}
.ov-stats{display:flex;justify-content:center;gap:26px;margin-top:10px}
.ov-stats .s{text-align:center}
.ov-stats .v{font-size:19px;font-weight:800}
.ov-stats .l{font-size:10px;letter-spacing:1px;color:var(--muted);font-weight:800}
.ov-adv{margin-top:10px;font-size:13px;font-weight:700}
.sh{font-size:11px;font-weight:800;letter-spacing:1.4px;color:var(--muted);margin:18px 0 8px}
.search{width:100%;margin-bottom:12px}
.subj{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 14px;
margin-bottom:8px;cursor:pointer}
.subj .row1{display:flex;justify-content:space-between;align-items:center;gap:10px}
.subj .nm{font-weight:800;font-size:14.5px}
.subj .pct{font-size:17px;font-weight:800;white-space:nowrap}
.subj .meta{color:var(--muted);font-size:12px;margin-top:2px}
.subj .adv{font-size:12px;font-weight:700;margin-top:4px}
.log{display:none;margin-top:8px;border-top:1px solid var(--line);padding-top:8px}
.log .li{display:flex;justify-content:space-between;font-size:12.5px;padding:3px 0;color:var(--muted);gap:8px}
.log .li b{color:var(--ink)}
.btns{display:flex;gap:8px;margin-top:14px}
.btns .btn{flex:1}
.hidden{display:none}
</style>
</head>
<body>
<div class="wrap">

  <!-- ============ LOGIN ============ -->
  <div id="screenLogin">
    <div class="top"><span class="brand">&#127891; JNTUACEA Attendance</span></div>
    <h1>Check Your Attendance</h1>
    <p class="sub">Secure access to your JNTUACEA attendance records &mdash; subject-wise,
    updated in real time.</p>

    <div class="status gray" id="statusBox">Checking portal&hellip;</div>

    <div class="card">
      <label>USERNAME (ROLL NUMBER)</label>
      <input id="syncRoll" placeholder="e.g. 23001A0204" autocomplete="username">
      <label>PASSWORD</label>
      <input id="syncPass" type="password" placeholder="Your college portal password"
             autocomplete="current-password">
      <button class="btn" id="syncBtn" onclick="doSync()">Check Attendance &rarr;</button>
      <div class="msg" id="syncMsg"></div>
      <p style="font-size:11.5px;color:var(--muted);margin-top:10px">
        Your credentials are saved on this device only &mdash; next time the page
        syncs automatically. Your password is never stored on any server.</p>
    </div>

    <a class="btn green" href="https://jntuaceastudents.classattendance.in/"
       target="_blank" rel="noopener"
       style="text-align:center">&#128279; Open Official Portal (check directly while this page waits)</a>

    <button class="btn green" onclick="showEntry();"
      style="margin-top:10px">&#128203; Paste &amp; Calculate &mdash; works even WITHOUT server (tap here)</button>

    <div id="captchaBox" style="display:none;margin-top:4px">
      <div style="background:#FFF7ED;border:1.5px solid #FDBA74;border-radius:12px;padding:12px 14px;margin:10px 0">
        <b style="color:#C2410C;font-size:13.5px">&#128274; Mee credentials tappu kadu! Portal CAPTCHA (Cloudflare security) server login ni block chestundi.</b>
        <p style="font-size:12px;color:#9A3412;margin:6px 0 2px">
          Official portal lo CAPTCHA <b>mee browser lo solve avtundi</b> — app "Check Attendance"
          server nunchi chestundi, adi block avtundi. So browser lo login chesi, copy chesi,
          ikkada paste cheyandi — 100% works:</p>
        <ol style="font-size:12.5px;color:#7C2D12;margin:6px 0 10px 18px;padding:0;line-height:1.8">
          <li>&#128279; <b>Open Official Portal</b> button nokkandi &rarr; mee roll + password tho
              login ayyi (CAPTCHA solve avtundi) &rarr; attendance page lo <b>Select All + Copy</b></li>
          <li>&#128241; Ikkada return ayyi <b>Paste &amp; Calculate</b> nokkandi &rarr; copy chesindi
              <b>automatic ga detect avtundi</b></li>
          <li>&#127891; Overall % + subject-wise % + skip/attend advice instant ga!</li>
        </ol>
        <div style="margin-top:8px">
          <button class="btn green" onclick="showEntry();" style="margin-top:0">&#128203; Paste &amp; Calculate (100% works)</button>
          <a class="btn" href="https://jntuaceastudents.classattendance.in/" target="_blank"
             rel="noopener" style="margin-top:8px">&#128279; Open Official Portal (login + copy)</a>
        </div>
        <p style="font-size:11px;color:#9A3412;margin-top:8px">
          <b>Note:</b> portal CAPTCHA appudu on, appudu off (adaptive). Off unde time lo
          "Check Attendance" direct ga work chestundi — mee 78.6% screenshot la.
          CAPTCHA active unde varaku browser flow (paina) use cheyandi.</p>
      </div>
    </div>

    <div class="links">
      <a href="#" onclick="showEntry();return false;">&#128203; Paste &amp; Calculate (always works)</a><br>
      <a href="/extension.zip" style="font-size:11.5px">&#129309; Chrome Extension (PC/kiwi lo test)</a>
      &nbsp;&middot;&nbsp;
      <a href="/downloads/app.apk">&#128241; Android App</a>
    </div>

    <!-- ===== BOOKMARKLET ===== -->
    <div class="card" id="bmCard" style="margin-top:6px;border-color:#1171e9">
      <div style="font-size:11px;font-weight:800;color:#1171e9;letter-spacing:.4px">
        &#127919; MEE FLOW: CAPTCHA nuvvu solve cheyandi &rarr; helper oka tap &rarr; read + calculate AUTOMATIC
      </div>
      <p style="font-size:12px;color:var(--muted);margin:6px 0 8px">
        Browser security valla app lo official portal captcha kanipinchadu (portal embed block
        chestundi). Kani ee helper tho: portal lo login ayyaka <b>oka tap</b> lo attendance
        chadivi calculate chestundi &mdash; copy cheyalsina avasaram ledu! <b>Oka saari setup:</b></p>

      <div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;padding:10px 12px;margin:8px 0">
        <div style="font-size:12px;font-weight:800;color:#1E40AF;margin-bottom:6px">1) PC/Desktop &mdash; EASIEST (drag &amp; drop)</div>
        <div style="font-size:12px;color:#1E40AF;line-height:1.6">
          Kotha bookmark cheyadam kadu &mdash; idi <b>drag chesi bookmarks bar lo vadileyandi</b>:</div>
        <a id="bmDragLink" href="#" draggable="true"
           style="display:block;text-align:center;margin:8px 0 2px;padding:11px;border-radius:10px;
                  background:linear-gradient(135deg,#1171e9,#073d92);color:#fff;font-size:14px;
                  font-weight:800;text-decoration:none;cursor:grab">&#128279; &#127919; JNTU Attendance Helper &mdash; drag me to bookmarks bar</a>
        <div style="font-size:11px;color:#1E40AF;margin-top:4px">
          Bookmarks bar (Ctrl+Shift+B) open lo &mdash; ee link ni akkadiki drag cheyandi. Done!</div>
      </div>

      <div style="background:#FFF7ED;border:1px solid #FDBA74;border-radius:10px;padding:10px 12px;margin:8px 0">
        <div style="font-size:12px;font-weight:800;color:#C2410C;margin-bottom:6px">2) Phone &mdash; copy + bookmark</div>
        <ol style="font-size:12px;color:#9A3412;margin:0 0 6px 18px;padding:0;line-height:1.7">
          <li>Kinda <b>Copy Bookmarklet Code</b> button nokkandi</li>
          <li>Browser lo <b>official portal</b> open cheyandi &rarr; menu &rarr; <b>Add bookmark</b> &rarr; <b>Edit</b> &rarr; URL lo code <b>paste</b> cheyandi</li>
          <li>Login ayyaka portal lo unnapudu aa bookmark <b>tap</b> cheyandi &rarr; dashboard!</li>
        </ol>
      </div>

      <div style="display:flex;gap:8px;margin-top:10px">
        <button class="btn green" onclick="copyBM();" style="flex:1;margin-top:0">&#128203; Copy Bookmarklet Code</button>
        <a class="btn" href="https://jntuaceastudents.classattendance.in/" target="_blank"
           rel="noopener" style="flex:0 0 auto;margin-top:0;background:#059669;padding:13px 14px">&#128279; Open Portal</a>
      </div>
      <textarea id="bmCode" readonly style="min-height:52px;font-size:11px;margin-top:8px;background:#f4f7fb"></textarea>

      <div style="font-size:12px;font-weight:700;color:#059669;margin-top:8px">Use chesaka:</div>
      <ol style="font-size:12px;color:var(--ink);margin:2px 0 0 18px;padding:0;line-height:1.7">
        <li>Portal lo login (captcha mee browser lo solve avtundi)</li>
        <li>Helper bookmark tap &rarr; "Reading your semester..." &rarr; dashboard</li>
        <li>Dashboard lo <b>Open in App</b> &rarr; ikkada auto-fill + auto-calculate</li>
      </ol>
    </div>
  </div>

  <!-- ============ QUICK ENTRY ============ -->
  <div id="screenEntry" class="hidden">
    <div class="top">
      <span class="brand">&#9998; Quick Entry</span>
      <a href="#" onclick="showLogin();return false;">&larr; Back</a>
    </div>
    <div class="card">
      <label>ROLL NUMBER</label>
      <input id="entryRoll" placeholder="e.g. 23001A0204">
      <label>YOUR NAME</label>
      <input id="entryName" placeholder="e.g. Sai Kumar">

      <!-- ===== PASTE & CALCULATE (new) ===== -->
      <div style="margin-top:16px;border-top:1px dashed var(--line);padding-top:14px">
        <div style="font-size:11px;font-weight:800;color:var(--muted);letter-spacing:.4px">
          &#128203; PASTE RECORD FROM PORTAL &nbsp;<span style="color:var(--green)">(fast - no typing)</span>
        </div>
        <textarea id="pasteBox" style="min-height:130px"
          placeholder="Portal lo attendance page open chesi -> Select All (Ctrl+A / long-press) -> Copy -> ikkada paste cheyandi (Ctrl+V).&#10;&#10;Example:&#10;POWER ELECTRONICS&#10;01-02-2026 09:30 AM P&#10;02-02-2026 09:30 AM A&#10;Total: 9  Present: 6  Absent: 3"></textarea>
        <div style="display:flex;gap:8px;margin-top:10px">
          <button class="btn green" onclick="doPasteParse()" style="flex:1;margin-top:0">&#128269; Parse Paste</button>
          <button class="btn" onclick="fillSample()" style="flex:0 0 auto;margin-top:0;background:var(--muted);padding:13px 16px">Sample</button>
        </div>
        <button class="btn" onclick="clipboardPaste();" style="margin-top:8px;background:#0f766e">&#128203; Auto-Paste from Clipboard (copy ayyaka ikkada oka tap)</button>
        <div class="msg" id="pasteMsg"></div>
        <p style="font-size:11.5px;color:var(--muted);margin-top:8px">
          Portal lo copy chesi app tab ki return ayithee <b>automatic ga detect</b> avutundi too!
          Any format works &mdash; subject name line + numbers like <b>6/9</b>, or
          <b>Total 9 Present 6</b>, or a <b>date + P/A</b> list. App counts automatically.</p>
      </div>

      <!-- ===== MANUAL LIST (auto-filled by paste) ===== -->
      <div style="margin-top:16px;border-top:1px dashed var(--line);padding-top:14px">
        <label style="margin-top:0">SUBJECTS - ONE PER LINE (Present/Total) <span style="color:var(--green)">auto-filled by Paste</span></label>
        <textarea id="entrySubs" placeholder="Power Electronics 6/9&#10;Management Science 6/8&#10;Electrical Distribution 10/12"></textarea>
        <button class="btn green" onclick="doEntry()">Show My Attendance</button>
        <div class="msg" id="entryMsg"></div>
        <p style="font-size:11.5px;color:var(--muted);margin-top:10px">
          Paste chesaka list automatic ga fill avutundi &mdash; oka saari chusi,
          edaina miss ayite add/edit chesi <b>Show My Attendance</b> nokkandi.</p>
      </div>
    </div>
  </div>

  <!-- ============ DASHBOARD ============ -->
  <div id="screenDash" class="hidden">
    <div class="top">
      <span class="brand">&#127891; JNTUACEA Attendance</span>
      <a href="#" onclick="showLogin();return false;">Logout</a>
    </div>
    <div class="d-name" id="dName"></div>
    <div class="d-roll" id="dRoll"></div>
    <div class="ovcard">
      <div class="ov-label">OVERALL ATTENDANCE</div>
      <div class="ov-pct" id="dOverall"></div>
      <div class="ov-stats">
        <div class="s"><div class="v" id="dTot"></div><div class="l">TOTAL</div></div>
        <div class="s"><div class="v" id="dAtt" style="color:var(--green)"></div><div class="l">ATT</div></div>
        <div class="s"><div class="v" id="dAbs" style="color:var(--red)"></div><div class="l">ABS</div></div>
      </div>
      <div class="ov-adv" id="dAdv"></div>
    </div>
    <div class="sh">SUBJECTS</div>
    <input class="search" id="searchInput" placeholder="Search subject..." onkeyup="filterSubs()">
    <div id="subjList"></div>
    <div class="btns">
      <button class="btn" onclick="doSync()">&#128260; Re-check</button>
      <button class="btn green" onclick="window.print()">&#128424; Print</button>
    </div>
  </div>
</div>

<!-- ============ SYNCING OVERLAY ============ -->
<div id="syncOverlay">
  <div class="big">&#127891;</div>
  <div class="t1">SYNCING</div>
  <div class="t2">Reading your semester</div>
  <div class="step" id="syncStep">Starting&hellip;</div>
  <div class="bar"><div id="syncBar"></div></div>
  <div class="foot">Secure session &middot; jntuaceastudents.classattendance.in</div>
</div>

<script>
var STATE = {name:'', roll:'', subs:[]};

function showLogin(){
  document.getElementById('screenLogin').classList.remove('hidden');
  document.getElementById('screenEntry').classList.add('hidden');
  document.getElementById('screenDash').classList.add('hidden');
}
function showEntry(){
  loadEntryPrefs();
  document.getElementById('screenLogin').classList.add('hidden');
  document.getElementById('screenEntry').classList.remove('hidden');
  document.getElementById('screenDash').classList.add('hidden');
}
function showDash(){
  document.getElementById('screenLogin').classList.add('hidden');
  document.getElementById('screenEntry').classList.add('hidden');
  document.getElementById('screenDash').classList.remove('hidden');
}

var SYNC_TIMER = null;
function startSync(){
  var total = 8;
  document.getElementById('syncOverlay').style.display = 'block';
  var done = 0;
  document.getElementById('syncStep').textContent = 'Processed 0 of ' + total + ' subjects  0%';
  document.getElementById('syncBar').style.width = '0%';
  SYNC_TIMER = setInterval(function(){
    done = Math.min(total, done + 1);
    var pct = Math.round(done * 100 / total);
    document.getElementById('syncStep').textContent =
      'Processed ' + done + ' of ' + total + ' subjects  ' + pct + '%';
    document.getElementById('syncBar').style.width = pct + '%';
  }, 1400);
}
function stopSync(){
  if (SYNC_TIMER){ clearInterval(SYNC_TIMER); SYNC_TIMER = null; }
  document.getElementById('syncOverlay').style.display = 'none';
}

function msg(id, cls, text){
  var m = document.getElementById(id);
  m.className = 'msg ' + cls;
  m.textContent = text;
}

function setStatus(txt, cls){
  var b = document.getElementById('statusBox');
  b.textContent = txt;
  b.className = 'status ' + cls;
}

function checkStatus(cb){
  fetch('/app/status').then(function(r){ return r.json(); }).then(function(d){
    var now = new Date().toLocaleTimeString();
    if (d.open){
      setStatus('\uD83D\uDFE2 Portal is OPEN \u2014 tap Check Attendance to sync (checked ' + now + ')', 'green');
    } else if (d.captcha){
      setStatus('\uD83D\uDD34 Portal CAPTCHA is ON right now \u2014 two instant options below', 'red');
    } else {
      setStatus('\u26AA Could not reach the portal (checked ' + now + ')', 'gray');
    }
    if (cb) cb(d);
  }).catch(function(){
    setStatus('\u26AA Could not reach the portal \u2014 but Paste & Calculate works even without server \u2193', 'gray');
    if (cb) cb({open:false});
  });
}

function doSync(){
  var roll = document.getElementById('syncRoll').value.trim().toUpperCase();
  var pass = document.getElementById('syncPass').value;
  if (roll.length < 5 || !pass){
    msg('syncMsg','err','Please enter username and password.');
    return;
  }
  doSyncNow(roll, pass, false);
}

function doSyncNow(roll, pass, quiet){
  try {
    localStorage.setItem('jnt_roll', roll);
    localStorage.setItem('jnt_pass', pass);
  } catch(e){}
  var btn = document.getElementById('syncBtn');
  btn.disabled = true; btn.textContent = 'Loading\u2026';
  if (!quiet){ msg('syncMsg','ok',''); }
  startSync();
  fetch('/app/sync', {
    method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:'username='+encodeURIComponent(roll)+'&password='+encodeURIComponent(pass)
  }).then(function(r){ return r.json(); })
    .then(function(d){
      btn.disabled = false; btn.textContent = 'Check Attendance \u2192';
      stopSync();
      if (d.error){
        if (d.error.indexOf('CAPTCHA') >= 0 || d.error.indexOf('verification') >= 0){
          msg('syncMsg','err', d.error);
          document.getElementById('captchaBox').style.display = 'block';
          checkStatus();
        } else {
          showLogin();
          msg('syncMsg','err', d.error);
        }
        return;
      }
      var rows = (d.subjects||[]).map(function(s){
        return {name:s.Subject, total:s.total, present:s.present, rows:s.rows||[]};
      });
      renderDash(d.name||roll, roll + (d.cls?' : '+d.cls:''), rows,
        (d.subjects||[]).map(function(s){return s.rows||[];}));
      if (d.diag && d.diag.length){
        var dmsg = document.createElement('div');
        dmsg.style.cssText = 'font-size:11.5px;color:#B45309;background:#FEF3C7;border:1px solid #FDE68A;border-radius:10px;padding:10px 12px;margin-top:14px;white-space:pre-wrap';
        dmsg.textContent = 'Some subjects returned no data:\n' + d.diag.join('\n')
          + '\n\nTap Re-check - portal session ok aite anni vastayi.';
        document.getElementById('subjList').appendChild(dmsg);
      }
      showDash();
    })
    .catch(function(e){
      btn.disabled = false; btn.textContent = 'Check Attendance \u2192';
      stopSync();
      showLogin();
      msg('syncMsg','err','Could not connect. Please try again. (Tip: server needs to run on Vercel \u2014 or use Paste & Calculate below, it works offline.)');
    });
}

function loadEntryPrefs(){
  try {
    document.getElementById('entryRoll').value = localStorage.getItem('jnt_eroll')||'';
    document.getElementById('entryName').value = localStorage.getItem('jnt_ename')||'';
    document.getElementById('entrySubs').value = localStorage.getItem('jnt_esubs')||'';
  } catch(e){}
}

function parseTotals(text){
  var out = [];
  text.split('\n').forEach(function(line){
    line = line.trim();
    if (!line) return;
    var present = -1, total = -1;
    var m = line.match(/(\d{1,3})\s*\/\s*(\d{1,3})/);
    if (m){ present = +m[1]; total = +m[2]; }
    else {
      var k = line.match(/total\s*=?\s*(\d{1,3})\s+present\s*=?\s*(\d{1,3})/i);
      if (k){ total = +k[1]; present = +k[2]; }
      else {
        var nums = line.match(/\d{1,3}/g);
        if (nums && nums.length >= 2){ total = +nums[nums.length-2]; present = +nums[nums.length-1]; }
      }
    }
    if (present < 0 || total < 1 || present > total || total > 600) return;
    var name = line.replace(/\d{1,3}\s*\/\s*\d{1,3}/,' ')
      .replace(/total\s*=?\s*\d{1,3}/gi,' ')
      .replace(/present\s*=?\s*\d{1,3}/gi,' ')
      .replace(/\d{1,3}/g,' ')
      .replace(/[\s:;,.|\-]+/g,' ').trim();
    if (name.length < 2) return;
    out.push({name:name, total:total, present:present});
  });
  return out;
}

function doEntry(){
  var roll = document.getElementById('entryRoll').value.trim().toUpperCase();
  var name = document.getElementById('entryName').value.trim() || roll;
  var subsText = document.getElementById('entrySubs').value;
  if (roll.length < 5){ msg('entryMsg','err','Please enter a valid roll number.'); return; }
  var rows = parseTotals(subsText);
  if (!rows.length){ msg('entryMsg','err','No valid lines. Format: Subject Name 6/9 (one per line).'); return; }
  try {
    localStorage.setItem('jnt_eroll', roll);
    localStorage.setItem('jnt_ename', name);
    localStorage.setItem('jnt_esubs', subsText);
  } catch(e){}
  renderDash(name, roll + ' : B.Tech (JNTUACEA)', rows, []);
  showDash();
}

/* ============================================================
   PASTE & CALCULATE — parse copied portal record text
   Handles:  "Subject 6/9",  "Total 9 Present 6 Absent 3",
             "Subject 9 6",  date + P/A lists, tables, etc.
   ============================================================ */

function stripJunk(s){
  return s.replace(/\b\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}\b/g,' ')      // dates
    .replace(/\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?\b/gi,' ')          // times
    .replace(/\b(s\.?no\.?|sl\.?no\.?|sno|date|day|status|attendance|period|session|time|lecture|class|subject|log|total|tot|present|absent|percentage|per\s*cent|attended|missed|att|skip|keep|attending|more|semester|sem)\b/gi,' ')
    .replace(/\b[PA]\b/g,' ')                                              // status tokens P / A
    .replace(/[()\[\]{};,:"'|]+/g,' ')
    .replace(/\s+/g,' ').trim();
}
function grabNum(text, re){
  var m = text.match(re);
  return m ? parseInt(m[1],10) : null;
}
function isHeaderLine(ln){
  if (/(absent|present|attended|missed)/i.test(ln)) return false;  // status rows are not headers
  if (/[0-9:]/.test(ln)) return false;                              // dates/times/S.No rows are not headers
  var s = stripJunk(ln);
  if (!s || s.length < 2 || s.length > 70) return false;
  if (/^(total|present|absent|percentage|per\s*cent)/i.test(ln.trim())) return false;
  return true;
}
function splitBlocks(text){
  var lines = text.split(/\r?\n/).map(function(l){ return l.trim(); });
  var blocks = [], cur = [];
  function flush(){ if (cur.length){ blocks.push(cur.join('\n')); cur = []; } }
  lines.forEach(function(ln){
    if (!ln){ flush(); return; }
    if (isHeaderLine(ln)){ flush(); }
    cur.push(ln);
  });
  flush();
  return blocks;
}
function pickName(lines){
  for (var i=0;i<lines.length;i++){
    var s = stripJunk(lines[i]).replace(/\d{1,3}(?:\.\d+)?\s*%/g,' ').replace(/\s*\d{1,3}\s*$/,'');
    if (s.length >= 2 && /[A-Za-z]/.test(s) && !/^(total|present|absent|percentage)/i.test(s)) return s;
  }
  var fb = stripJunk(lines[0]).replace(/\d{1,3}(?:\.\d+)?\s*%/g,' ').replace(/\s*\d{1,3}\s*$/,'');
  return (/total|present|absent|percentage/i.test(fb) || !/[A-Za-z]/.test(fb)) ? 'Subject' : (fb || 'Subject');
}
function countPA(text){
  var P = 0, A = 0;
  text.split(/[^A-Za-z]+/).forEach(function(t){
    if (t === 'P') P++;
    else if (t === 'A') A++;
    else if (/^PRESENT$/i.test(t) || /^ATTENDED$/i.test(t)) P++;
    else if (/^ABSENT$/i.test(t) || /^MISSED$/i.test(t)) A++;
  });
  return [P, A];
}
function nameBeforeTotals(text){
  var t = text.split(/\b(?:total|tot)\b/i)[0];
  t = t.replace(/\d{1,3}(?:\.\d+)?\s*%/g,' ');
  t = t.replace(/\s*(?:skip\s+\d+\s+class(?:es)?|attend\s+\d+\s+more|keep\s+attending)\s*$/i,' ');
  t = stripJunk(t).replace(/(?:\s+\d{1,3})+\s*$/,' ').trim();
  return t.length >= 2 ? t : null;
}
function parseBlock(text){
  var lines = text.split('\n');
  var am = text.match(/(\d{1,3})\s+attended\b[\s\S]{0,40}\b(\d{1,3})\s+missed\b/i);
  var amRev = null;
  if (!am) amRev = text.match(/(\d{1,3})\s+missed\b[\s\S]{0,40}\b(\d{1,3})\s+attended\b/i);
  if (am){
    var apr = +am[1], ami = +am[2];
    return {name: pickName(lines), present: apr, total: apr + ami};
  }
  if (amRev){
    var apr2 = +amRev[2], ami2 = +amRev[1];
    return {name: pickName(lines), present: apr2, total: apr2 + ami2};
  }
  var tp = text.match(/(?:total|tot)\s*[=:]?\s*(\d{1,3})[\s,;]{1,12}(?:present|att|attended)\s*[=:]?\s*(\d{1,3})/i);
  var tp2 = text.match(/(?:present|att|attended)\s*[=:]?\s*(\d{1,3})[\s,;]{1,12}(?:total|tot)\s*[=:]?\s*(\d{1,3})/i);
  if (tp && +tp[2] <= +tp[1] && +tp[1] <= 600){
    return {name: nameBeforeTotals(text) || pickName(lines), present: +tp[2], total: +tp[1]};
  }
  if (tp2 && +tp2[1] <= +tp2[2] && +tp2[2] <= 600){
    return {name: nameBeforeTotals(text) || pickName(lines), present: +tp2[1], total: +tp2[2]};
  }
  var pa = countPA(text);
  if (pa[0] + pa[1] >= 2){
    return {name: pickName(lines), present: pa[0], total: pa[0] + pa[1]};
  }
  var m = text.match(/(\d{1,3})\s*\/\s*(\d{1,3})/);
  if (m){
    var pr = +m[1], tt = +m[2];
    if (pr <= tt && tt <= 600){
      var nm = stripJunk(text.replace(/\d{1,3}\s*\/\s*\d{1,3}/,' '));
      if (nm.length >= 2) return {name: nm, present: pr, total: tt};
    }
  }
  if (/total|present|absent|\//i.test(text)){
    var nums = text.match(/\d{1,3}/g);
    if (nums && nums.length >= 2){
      var lastN = +nums[nums.length-1], prevN = +nums[nums.length-2];
      if (prevN <= lastN && lastN <= 600){            // "name  6  9" (present total)
        return {name: pickName(lines), present: prevN, total: lastN};
      }
      var tt2 = +nums[nums.length-2], pr2 = +nums[nums.length-1];
      if (pr2 <= tt2 && tt2 <= 600 && tt2 >= 1){      // "name  9  6" (total present)
        return {name: pickName(lines), present: pr2, total: tt2};
      }
    }
  }
  return null;
}
function parseTableMode(text){
  var out = [];
  text.split(/\r?\n/).forEach(function(ln0){
    var ln = ln0.trim();
    if (!ln) return;
    // "Subject ... Tot 11 Att 9 ..." style line (dashboard copy)
    var mm = ln.match(/^(.{2,90}?)\s+(?:total|tot)\s*[=:]?\s*(\d{1,3})[\s,;]+(?:present|att|attended)\s*[=:]?\s*(\d{1,3})\b/i);
    if (mm && +mm[3] <= +mm[2] && +mm[2] <= 600){
      out.push({name: nameBeforeTotals(ln) || mm[1].trim(), present: +mm[3], total: +mm[2]});
      return;
    }
    var name = null, nums = [];
    if (ln.indexOf('\t') >= 0 || /\s{2,}/.test(ln)){
      var cells = ln.split(/\t+|\s{2,}/).map(function(c){ return c.trim(); }).filter(Boolean);
      if (!cells.length) return;
      var c0 = cells[0];
      if (/^\d|total|present|absent|percentage|status|date|subject|s\.?no/i.test(c0)) return;
      var tI = -1, pI = -1;
      for (var k=1;k<cells.length;k++){
        if (/^(total|tot)$/i.test(cells[k]) && tI < 0) tI = k;
        else if (/^(present|att|attended)$/i.test(cells[k]) && pI < 0) pI = k;
      }
      if (tI >= 0 && pI >= 0 && tI < cells.length-1 && pI < cells.length-1){
        var tt = parseInt(cells[tI+1],10), pr = parseInt(cells[pI+1],10);
        if (!isNaN(tt) && !isNaN(pr) && pr <= tt && tt <= 600){
          out.push({name: nameBeforeTotals(ln) || c0, present: pr, total: tt});
          return;
        }
      }
      name = c0;
      for (var j=1;j<cells.length;j++){
        var n = parseInt(cells[j],10);
        if (!isNaN(n)) nums.push(n);
      }
    } else {
      var m = ln.match(/^([A-Za-z][A-Za-z0-9 .&(),'-]{2,60}?)\s+(\d{1,3})\s+(\d{1,3})\s*$/);
      if (m){ name = m[1].trim(); nums = [+m[2], +m[3]]; }
    }
    if (!name || nums.length !== 2) return;
    var a = nums[0], b = nums[1];
    if (a <= b && b <= 600 && b >= 1) out.push({name:name, present:a, total:b});
    else if (b <= a && a <= 600 && a >= 1) out.push({name:name, present:b, total:a});
  });
  return out;
}
function dedupeRows(rows){
  var out = [];
  rows.forEach(function(r){
    var last = out[out.length-1];
    if (last && last.name.toLowerCase() === r.name.toLowerCase()){
      last.total += r.total; last.present += r.present;
    } else out.push(r);
  });
  return out;
}
function parseManualLines(text){
  var out = [];
  text.split(/\r?\n/).forEach(function(line){
    line = line.trim();
    if (!line) return;
    var m = line.match(/^(.{2,80}?)\s*(\d{1,3})\s*\/\s*(\d{1,3})\s*$/);
    if (!m) return;
    var pr = +m[2], tt = +m[3];
    if (pr > tt || tt > 600) return;
    var nm = stripJunk(m[1]);
    if (nm.length < 2 || !/[A-Za-z]/.test(nm)) return;
    out.push({name: nm, present: pr, total: tt});
  });
  return out;
}
function parseRecord(text){
  var tableRows = parseTableMode(text);
  if (tableRows.length >= 1) return tableRows;

  var blockRows = [];
  splitBlocks(text).forEach(function(b){
    var r = parseBlock(b);
    if (r) blockRows.push(r);
  });
  blockRows = dedupeRows(blockRows);

  var lineRows = parseManualLines(text);
  if (lineRows.length >= 2 && lineRows.length >= blockRows.length) return lineRows;
  return blockRows;
}
function doPasteParse(){
  var raw = document.getElementById('pasteBox').value;
  var rows = parseRecord(raw);
  var m = document.getElementById('pasteMsg');
  if (!rows.length){
    m.className = 'msg err';
    m.textContent = 'Paste lo attendance numbers kanipinchaledu. Confirm: (1) subject name line undali, (2) numbers "6/9" or "Total 9 Present 6" la undali, or (3) date + P/A list undali. Sample button tho try cheyandi.';
    return;
  }
  var lines = rows.map(function(r){ return r.name + ' ' + r.present + '/' + r.total; });
  document.getElementById('entrySubs').value = lines.join('\n');
  m.className = 'msg ok';
  m.textContent = '\u2705 ' + rows.length + ' subject(s) detected from paste! List below lo fill ayyindi \u2014 oka saari chusi (edaina miss ayite add/edit chesi) "Show My Attendance" nokkandi.';
  try {
    localStorage.setItem('jnt_esubs', lines.join('\n'));
  } catch(e){}
}
function fillSample(){
  document.getElementById('pasteBox').value =
'Power System Operation and Control\nAttendance log : 9 attended, 2 missed\n30-06-2026  1:45 PM - 2:45 PM  Absent\n06-07-2026  10:30 AM - 11:30 AM  Absent\n07-07-2026  1:45 PM - 2:45 PM  Present\n08-07-2026  10:30 AM - 11:30 AM  Present\n13-07-2026  10:30 AM - 11:30 AM  Present\n14-07-2026  1:45 PM - 2:45 PM  Present\n15-07-2026  10:30 AM - 11:30 AM  Present\n20-07-2026  10:30 AM - 11:30 AM  Present\n21-07-2026  1:45 PM - 2:45 PM  Present\n22-07-2026  10:30 AM - 11:30 AM  Present\n\nManagement Science\nTotal 8  Present 6  Absent 2\n\nElectric Vehicle Technology\n05-08-2026  Present\n06-08-2026  Absent\n07-08-2026  Present\n08-08-2026  Present\n09-08-2026  Absent\n10-08-2026  Present\n11-08-2026  Present\n12-08-2026  Absent\n13-08-2026  Present\n14-08-2026  Present\n15-08-2026  Present\n16-08-2026  Absent\n17-08-2026  Present\n18-08-2026  Present\n19-08-2026  Absent\n20-08-2026  Present\nTotal 16  Present 11  Absent 5';
  doPasteParse();
}

var BM_CODE = (function(){
  // Build the bookmarklet from THIS page's own URL, so it works from any host.
  var u = location.href.split('#')[0].split('?')[0];
  var dir = u.substring(0, u.lastIndexOf('/') + 1);   // folder of this page
  return "javascript:(function(){window.__jnApp='" + u + "';var s=document.createElement('script');s.src='" + dir + "bm.js';s.onload=function(){window.__jnBM&&console.log('JNTUACEA helper ready')};document.body.appendChild(s)})();";
})();
// Make the drag-link carry the bookmarklet code (PC drag-to-bookmarks-bar)
(function(){
  try {
    var a = document.getElementById('bmDragLink');
    if (a){
      a.href = BM_CODE;
      a.addEventListener('dragstart', function(e){
        e.dataTransfer.setData('text/uri-list', BM_CODE);
        e.dataTransfer.setData('text/plain', BM_CODE);
      });
    }
  } catch(e){}
})();
function copyBM(){
  document.getElementById('bmCode').value = BM_CODE;
  var t = document.getElementById('bmCode');
  t.select();
  try { document.execCommand('copy'); } catch(e){}
  try { navigator.clipboard.writeText(BM_CODE); } catch(e){}
  var b = document.querySelector('#bmCard .btn.green');
  b.textContent = 'Copied! Add as bookmark now';
  setTimeout(function(){ b.textContent = '\uD83D\uDCCB Copy Bookmarklet Code'; }, 2500);
}
(function(){ document.getElementById('bmCode').value = BM_CODE; })();

function clipboardPaste(){
  if (!navigator.clipboard || !navigator.clipboard.readText){
    msg('pasteMsg','err','This browser does not support clipboard read. Please paste manually.');
    return;
  }
  navigator.clipboard.readText().then(function(txt){
    if (!txt || !txt.trim()){ msg('pasteMsg','err','Clipboard lo emi ledu. Portal lo attendance copy chesi malli try cheyandi.'); return; }
    var rows = parseRecord(txt);
    if (!rows.length){ msg('pasteMsg','err','Clipboard lo attendance format kanipinchaledu. Manual ga paste cheyandi.'); return; }
    document.getElementById('pasteBox').value = txt;
    doPasteParse();
  }).catch(function(){
    msg('pasteMsg','err','Clipboard read avvaledu (browser permission). Manual ga paste cheyandi.');
  });
}
function tryAutoClipboard(){
  // Student portal lo copy chesi app tab ki return ayyinappudu auto-detect
  try {
    if (!navigator.clipboard || !navigator.clipboard.readText) return;
    navigator.clipboard.readText().then(function(txt){
      if (!txt || !txt.trim()) return;
      var pb = document.getElementById('pasteBox');
      if (pb.value && pb.value.trim()) return;
      if (!/(\d{1,3}\s*\/\s*\d{1,3})|present|absent|attended|missed|total|percentage/i.test(txt)) return;
      var rows = parseRecord(txt);
      if (!rows.length) return;
      pb.value = txt;
      doPasteParse();
    }).catch(function(){});
  } catch(e){}
}
if (typeof window.addEventListener === 'function'){
  window.addEventListener('focus', function(){ setTimeout(tryAutoClipboard, 500); });
}

// Read bookmarklet data from URL hash:  #d=roll|name|line1\nline2...
function readHashData(){
  try {
    var h = location.hash;
    if (!h || h.indexOf('#d=') !== 0) return false;
    var raw = decodeURIComponent(h.substring(3));
    var bar1 = raw.indexOf('|');
    var bar2 = raw.indexOf('|', bar1 + 1);
    if (bar1 < 0 || bar2 < 0) return false;
    var roll = raw.substring(0, bar1);
    var name = raw.substring(bar1 + 1, bar2);
    var lines = raw.substring(bar2 + 1);
    if (!roll || !lines) return false;
    document.getElementById('entryRoll').value = roll;
    document.getElementById('entryName').value = name;
    document.getElementById('entrySubs').value = lines;
    doEntry();
    try { history.replaceState(null, '', location.pathname); } catch(e){}
    return true;
  } catch(e){ return false; }
}

function renderDash(name, roll, rows, rowsBySubj){
  STATE.name = name; STATE.roll = roll;
  var tot = 0, pres = 0;
  STATE.subs = rows.map(function(r, i){
    tot += r.total; pres += r.present;
    return {name:r.name, total:r.total, present:r.present, rows: rowsBySubj[i] || r.rows || []};
  });
  document.getElementById('dName').textContent = name.toUpperCase();
  document.getElementById('dRoll').textContent = roll;
  var pct = tot ? Math.round(pres*1000/tot)/10 : 0;
  var ov = document.getElementById('dOverall');
  ov.textContent = pct + '%';
  ov.style.color = tot ? (pct>=75?'var(--green)':'var(--red)') : 'var(--muted)';
  document.getElementById('dTot').textContent = tot;
  document.getElementById('dAtt').textContent = pres;
  document.getElementById('dAbs').textContent = tot - pres;
  var adv = document.getElementById('dAdv');
  if (!tot){
    adv.textContent = 'No attendance recorded yet.';
    adv.style.color = 'var(--muted)';
  } else if (pct >= 75){
    var can = Math.max(0, Math.floor(pres/0.75 - tot));
    adv.textContent = can>0 ? ('Overall safe to skip '+can+' class'+(can===1?'':'es')+' while staying above 75%') : 'You are safely above 75% overall.';
    adv.style.color = 'var(--green)';
  } else {
    var need = Math.max(1, Math.ceil((0.75*tot - pres)/0.25));
    adv.textContent = 'Attend '+need+' more class'+(need===1?'':'es')+' to reach 75% overall.';
    adv.style.color = 'var(--red)';
  }
  buildSubs();
}

function buildSubs(){
  var list = document.getElementById('subjList');
  list.innerHTML = '';
  STATE.subs.forEach(function(s){
    var pct = s.total ? Math.round(s.present*1000/s.total)/10 : 0;
    var color = s.total ? (pct>=75?'var(--green)':(pct>=60?'var(--amber)':'var(--red)')) : 'var(--muted)';
    var adv;
    if (!s.total) adv = 'No classes recorded yet';
    else if (pct >= 75){
      var can = Math.max(0, Math.floor(s.present/0.75 - s.total));
      adv = can>0 ? ('Skip '+can+' class'+(can===1?'':'es')) : 'Keep attending';
    } else {
      var need = Math.max(1, Math.ceil((0.75*s.total - s.present)/0.25));
      adv = 'Attend '+need+' more';
    }
    var div = document.createElement('div');
    div.className = 'subj';
    div.setAttribute('data-name', s.name.toLowerCase());
    var logHtml = '';
    if (s.rows && s.rows.length){
      logHtml = '<div class="log">' + s.rows.map(function(r){
        var absent = (r.s||r.status||'').toUpperCase() === 'A';
        var d = r.d || r.date || '';
        var t = r.t || r.time || '';
        return '<div class="li"><b>'+d+'</b><span style="color:'+(absent?'var(--red)':'var(--green)')+
               ';font-weight:700">'+(absent?'Absent':'Present')+'</span><span>'+t+'</span></div>';
      }).join('') + '</div>';
    }
    div.innerHTML = '<div class="row1"><span class="nm">'+s.name+'</span>'+
      '<span class="pct" style="color:'+color+'">'+pct+'%</span></div>'+
      '<div class="meta">Tot '+s.total+' \u00B7 Att '+s.present+' \u00B7 Abs '+(s.total-s.present)+'</div>'+
      '<div class="adv" style="color:'+color+'">'+adv+'</div>' + logHtml;
    div.onclick = function(){
      var lg = this.querySelector('.log');
      if (lg) lg.style.display = lg.style.display === 'block' ? 'none' : 'block';
    };
    list.appendChild(div);
  });
}

function filterSubs(){
  var q = document.getElementById('searchInput').value.toLowerCase();
  document.querySelectorAll('.subj').forEach(function(el){
    el.style.display = el.getAttribute('data-name').indexOf(q) >= 0 ? '' : 'none';
  });
}

(function init(){
  try {
    var roll = localStorage.getItem('jnt_roll') || '';
    var pass = localStorage.getItem('jnt_pass') || '';
    if (roll){ document.getElementById('syncRoll').value = roll; }
    if (pass){ document.getElementById('syncPass').value = pass; }
  } catch(e){}
  if (readHashData()) return;   // bookmarklet opened us with data → dashboard direct
  checkStatus(function(d){
    if (d.open){
      var roll = document.getElementById('syncRoll').value.trim().toUpperCase();
      var pass = document.getElementById('syncPass').value;
      if (roll.length >= 5 && pass){
        doSyncNow(roll, pass, true);
      }
    } else if (d.captcha){
      document.getElementById('captchaBox').style.display = 'block';
    }
  });
})();

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(function(){});
}
</script>
</body>
</html>'''


def app_page_html():
    return APP_HTML


def app_sync_json(username, password):
    """Server-side sync attempt. Returns a dict with 'error' or dashboard data."""
    if not HAS_SCRAPER:
        return {'error': 'Auto-sync engine is not available right now. Use Paste & Calculate below.'}
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import scraper  # noqa: F401 - imported lazily
        data = scraper.full_fetch(username, password)
    except Exception as e:
        msg = str(e)
        if 'no subjects' in msg.lower() or 'route' in msg.lower() or 'missing' in msg.lower():
            return {'error': 'Your login was ACCEPTED, but the portal copy we reached '
                             'does not host the student pages. Use Paste & Calculate '
                             'below (always works).'}
        if 'CAPTCHA' in msg or 'Use https' in msg or 'verification' in msg:
            return {'error': 'CAPTCHA::Mee credentials tappu kadu - portal CAPTCHA '
                             '(Cloudflare security) server login ni block chestundi. '
                             'Browser lo portal open chesi login ayyi attendance COPY chesi '
                             'ikkada return aithe automatic ga vastundi - Paste & Calculate '
                             '100% works.'}
        if 'rejected' in msg.lower() or 'credential' in msg.lower():
            return {'error': 'Login failed: ' + msg[:160]}
        return {'error': 'Could not connect to the official portal. Try again in a minute.'}
    out = []
    for subj in data.get('subjects', []):
        out.append({
            'Subject': subj.get('Subject', 'Subject'),
            'total': int(subj.get('Total Days') or 0),
            'present': int(subj.get('No. of Present') or 0),
            'rows': subj.get('Details', []),
        })
    details = data.get('details') or {}
    name = ''
    cls = details.get('classname') or details.get('Class') or ''
    acy = details.get('acad_year') or ''
    for k, v in details.items():
        if 'name' in k.lower() and v:
            name = str(v).strip()
            break
    return {'name': name or username, 'subjects': out,
            'diag': data.get('diag', []), 'cls': cls, 'acy': acy}
