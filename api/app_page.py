#!/usr/bin/env python3
"""The in-browser attendance checker - ONE clean flow.

Screen flow (no tabs, no bookmarks, nothing to install):
  1. LOGIN  - college username + password (remembered on this device)
  2. SYNCING - "Reading your semester" with live progress
  3. DASHBOARD - OVERALL % + SUBJECT-WISE % (all subjects) + tap for log

Auto behavior (user does nothing extra):
  * saved credentials + portal open  -> syncs automatically on page load
  * portal CAPTCHA ON                -> the page waits and re-tries by
    itself every 45 seconds; the moment the portal opens it syncs.
  * Quick Entry fallback             -> small link, always works
"""

import re

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
.btn.gray{background:#64748b}
.msg{display:none;padding:10px 13px;border-radius:10px;font-size:13px;margin-top:10px}
.msg.err{display:block;background:#FDE8E8;color:#9B1C1C;border:1px solid #F2C4C4}
.msg.ok{display:block;background:#E7F6EF;color:#046C4E;border:1px solid #BFE6CF}
.status{display:none;padding:11px 14px;border-radius:12px;font-size:13.5px;font-weight:700;margin-top:12px}
.status.red{display:block;background:#FDE8E8;color:#9B1C1C;border:1px solid #F2C4C4}
.status.green{display:block;background:#E7F6EF;color:#046C4E;border:1px solid #BFE6CF}
.status.gray{display:block;background:#EEF1F6;color:#66748f;border:1px solid #DFE4EC}
.links{text-align:center;margin-top:14px;font-size:12.5px}
.links a{color:var(--blue);font-weight:700;text-decoration:none}
/* syncing overlay */
#syncOverlay{display:none;position:fixed;inset:0;background:var(--bg);z-index:50;
text-align:center;padding-top:64px}
#syncOverlay .big{font-size:42px}
#syncOverlay .t1{font-size:26px;font-weight:800;letter-spacing:3px;margin-top:14px;color:var(--ink)}
#syncOverlay .t2{color:var(--muted);margin-top:6px;font-size:14px}
#syncOverlay .step{margin-top:22px;font-size:16px;font-weight:700;color:var(--blue)}
#syncOverlay .bar{max-width:280px;margin:12px auto 0;height:8px;background:var(--line);border-radius:6px;overflow:hidden}
#syncOverlay .bar div{width:0%;height:100%;background:linear-gradient(90deg,#1171e9,#073d92);border-radius:6px;transition:width .3s}
#syncOverlay .foot{margin-top:24px;font-size:11px;color:var(--muted)}
/* dashboard */
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
    <div class="top">
      <span class="brand">&#127891; JNTUACEA Attendance</span>
    </div>
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

    <div class="card" style="border:1.5px solid #1171e9">
      <label style="margin-top:0;font-size:12px;color:#1171e9">&#128273; CAPTCHA-FIRST METHOD &mdash; OFFICIAL WEBSITE + OUR CONCEPT</label>
      <p style="font-size:13px;color:var(--muted);margin-top:6px;line-height:1.7">
        Official portal lo <b>CAPTCHA ni mee finger tho solve</b> chestaru &mdash; appudu mana dashboard
        <b>official website meeda ne</b> open avthundi: SYNCING &rarr; Overall % + Subject-wise %.<br><br>
        <b style="color:var(--ink)">Option A &mdash; Bookmark (okkasari, best):</b><br>
        1. <b>&#128203; Copy Bookmark Script</b> tap &rarr; 2. <b>&#128279; Open Official Portal</b> &rarr;
        login (CAPTCHA) &rarr; 3. Chrome &#8942; &rarr; &#9733; Save &rarr; &#8942; &rarr; Bookmarks &rarr;
        &#8942; &rarr; Edit &rarr; URL delete &rarr; paste &rarr; Save.<br>
        <i>Taruvata prati roju:</i> portal login &rarr; bookmark tap &rarr; attendance!<br><br>
        <b style="color:var(--ink)">Option B &mdash; Address bar (bookmark ledu, prati sari 5 sec):</b><br>
        1. <b>&#128203; Copy Address Script</b> &rarr; 2. portal open &rarr; login (CAPTCHA) &rarr;
        3. Address bar tap &rarr; <b>javascript:</b> ani type cheyandi &rarr; paste &rarr; Enter &rarr; attendance!
      </p>
      <button class="btn" onclick="copyBookmark()">&#128203; Copy Bookmark Script</button>
      <button class="btn gray" onclick="copyAddress()">&#128203; Copy Address Script</button>
      <a class="btn green" href="https://jntuaceastudents.classattendance.in/"
         target="_blank" rel="noopener">&#128279; Open Official Portal &rarr;</a>
      <textarea readonly id="scriptBox" style="margin-top:10px;height:56px;font-size:11px"
        onclick="this.select()"></textarea>
      <div class="msg" id="copyMsg" style="display:none"></div>
    </div>

    <div class="links">
      <a href="#" onclick="showEntry();return false;">&#9998; Quick Entry (always works)</a>
      &nbsp;&middot;&nbsp;
      <a href="/downloads/app.apk">&#128241; Download Android App</a>
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
      <label>SUBJECTS - ONE PER LINE (Present/Total)</label>
      <textarea id="entrySubs" placeholder="Power Electronics 6/9&#10;Management Science 6/8&#10;Electrical Distribution 10/12"></textarea>
      <button class="btn green" onclick="doEntry()">Show My Attendance</button>
      <div class="msg" id="entryMsg"></div>
      <p style="font-size:11.5px;color:var(--muted);margin-top:10px">
        Open the official portal on your phone, read each subject's
        Present/Total numbers, type them here. Saved on this device.</p>
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

// ---------------- screens ----------------
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

// ---------------- sync animation ----------------
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

// ---------------- msg helpers ----------------
function msg(id, cls, text){
  var m = document.getElementById(id);
  m.className = 'msg ' + cls;
  m.textContent = text;
  if (cls === 'ok'){ /* keep ok visible */ }
}

// ---------------- status + auto wait ----------------
var AUTO = {timer: null};

function setStatus(txt, cls){
  var b = document.getElementById('statusBox');
  b.textContent = txt;
  b.className = 'status ' + cls;
}

function checkStatus(cb){
  fetch('/app/status').then(function(r){ return r.json(); }).then(function(d){
    var now = new Date().toLocaleTimeString();
    if (d.open){
      setStatus('\uD83D\uDFE2 Portal is OPEN \u2014 auto-sync works (checked ' + now + ')', 'green');
    } else if (d.captcha){
      setStatus('\uD83D\uDD34 Portal CAPTCHA is ON \u2014 page will retry by itself every '
        + '45s and sync the moment it opens (checked ' + now + ')', 'red');
    } else {
      setStatus('\u26AA Could not reach the portal (checked ' + now + ')', 'gray');
    }
    if (cb) cb(d);
  }).catch(function(){
    setStatus('\u26AA Could not reach the portal.', 'gray');
    if (cb) cb({open:false});
  });
}

function autoWait(){
  if (AUTO.timer) clearInterval(AUTO.timer);
  AUTO.timer = setInterval(function(){
    checkStatus(function(d){
      if (d.open){
        clearInterval(AUTO.timer);
        AUTO.timer = null;
        var roll = document.getElementById('syncRoll').value.trim().toUpperCase();
        var pass = document.getElementById('syncPass').value;
        if (roll.length >= 5 && pass){ doSyncNow(roll, pass, true); }
      }
    });
  }, 45000);
}

// ---------------- portal route (bookmark / address bar) ----------------
var BM_BOOKMARK = __BM_BOOKMARK__;
var BM_ADDRESS = __BM_ADDRESS__;

function copyBookmark(){ copyScript(BM_BOOKMARK); }
function copyAddress(){ copyScript(BM_ADDRESS); }

function copyScript(txt){
  document.getElementById('scriptBox').value = txt;
  var after = function(){
    var m = document.getElementById('copyMsg');
    m.className = 'msg ok';
    m.style.display = 'block';
    m.textContent = 'Copied! Ippudu Open Official Portal tap chesi login cheyandi (CAPTCHA), taruvata Option A/B step 3 cheyandi.';
  };
  if (navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(after).catch(function(){ selectBox(); after(); });
  } else { selectBox(); after(); }
}

function selectBox(){
  var b = document.getElementById('scriptBox');
  b.focus(); b.select();
}

// ---------------- sync ----------------
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
          checkStatus();
          autoWait();          // nothing for the user to do - page waits itself
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
      msg('syncMsg','err','Could not connect. Please try again.');
    });
}

// ---------------- quick entry ----------------
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

// ---------------- dashboard ----------------
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

// ---------------- init ----------------
(function init(){
  try {
    var roll = localStorage.getItem('jnt_roll') || '';
    var pass = localStorage.getItem('jnt_pass') || '';
    if (roll){ document.getElementById('syncRoll').value = roll; }
    if (pass){ document.getElementById('syncPass').value = pass; }
  } catch(e){}
  checkStatus(function(d){
    if (d.open){
      var roll = document.getElementById('syncRoll').value.trim().toUpperCase();
      var pass = document.getElementById('syncPass').value;
      if (roll.length >= 5 && pass){
        // saved credentials + portal open -> sync automatically, no taps
        doSyncNow(roll, pass, true);
      }
    } else if (d.captcha){
      autoWait();
    }
  });
})();

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(function(){});
}
</script>
</body>
</html>'''


BM_BOOKMARK = ("javascript:(function(){var s=document.createElement('script');"
               "s.src='https://attendance-portal-uk21.vercel.app/bm.js';"
               "document.body.appendChild(s);})();")

BM_ADDRESS = ("(function(){var s=document.createElement('script');"
              "s.src='https://attendance-portal-uk21.vercel.app/bm.js';"
              "document.body.appendChild(s);})();")


def app_page_html():
    import json as _j
    return (APP_HTML.replace('__BM_BOOKMARK__', _j.dumps(BM_BOOKMARK))
                    .replace('__BM_ADDRESS__', _j.dumps(BM_ADDRESS)))


def app_sync_json(username, password):
    """Server-side sync attempt. Returns a dict with 'error' or dashboard data."""
    if not HAS_SCRAPER:
        return {'error': 'Auto-sync engine is not available right now. Use Quick Entry.'}
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
                             'does not host the student pages. The page will keep retrying '
                             'automatically - or use Quick Entry (always works).'}
        if 'CAPTCHA' in msg or 'Use https' in msg or 'verification' in msg:
            return {'error': 'CAPTCHA::The official portal CAPTCHA is ON right now. '
                             'This page will retry by itself every 45 seconds and sync '
                             'the moment the portal opens - you do not need to do anything. '
                             'Or use Quick Entry (always works).'}
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
