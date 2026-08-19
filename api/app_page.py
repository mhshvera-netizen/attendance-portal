#!/usr/bin/env python3
"""The in-browser attendance checker page (no APK needed).

Flow (all client-side rendering, works on any phone browser):
  Tab 1 - Auto Sync:   roll + password -> POST /app/sync -> server logs into
                       the official portal (works when the portal has no
                       CAPTCHA) -> JSON -> dashboard.
  Tab 2 - Quick Entry: type Present/Total per subject -> instant dashboard,
                       saved in localStorage.
"""
import re

try:
    import requests  # noqa
    from bs4 import BeautifulSoup  # noqa
    HAS_SCRAPER = True
except Exception:
    HAS_SCRAPER = False

BM_LOADER = ("javascript:(function(){var s=document.createElement('script');"
             "s.src='https://attendance-portal-uk21.vercel.app/bm.js';"
             "document.body.appendChild(s);})();")

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
h1{font-size:24px;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:13.5px;margin-top:4px}
.tabs{display:flex;gap:8px;margin:16px 0 12px}
.tab{flex:1;text-align:center;padding:10px;border-radius:12px;background:var(--card);
border:1px solid var(--line);font-size:13.5px;font-weight:700;color:var(--muted);cursor:pointer}
.tab.on{background:var(--blue);color:#fff;border-color:var(--blue)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:12px}
label{display:block;font-size:11px;font-weight:800;color:var(--muted);letter-spacing:.4px;margin:10px 0 4px}
input,textarea{width:100%;padding:11px 12px;border:1.5px solid var(--line);border-radius:10px;
font-size:14px;color:var(--ink);background:#fff;outline:none;font-family:inherit}
input:focus,textarea:focus{border-color:var(--blue)}
textarea{min-height:120px}
.btn{display:block;width:100%;padding:13px;border:none;border-radius:12px;background:var(--blue);
color:#fff;font-size:15px;font-weight:800;cursor:pointer;margin-top:14px}
.btn.green{background:var(--green)}
.msg{display:none;padding:10px 13px;border-radius:10px;font-size:13px;margin-top:10px}
.msg.err{display:block;background:#FDE8E8;color:#9B1C1C;border:1px solid #F2C4C4}
.msg.ok{display:block;background:#E7F6EF;color:#046C4E;border:1px solid #BFE6CF}
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
.log .li{display:flex;justify-content:space-between;font-size:12.5px;padding:3px 0;color:var(--muted)}
.log .li b{color:var(--ink)}
.btns{display:flex;gap:8px;margin-top:14px}
.btns .btn{flex:1}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <span class="brand">&#127891; JNTUACEA Attendance</span>
    <a href="/">&larr; Home</a>
  </div>
  <h1>Check Your Attendance</h1>
  <p class="sub">No app download needed &mdash; works right here in your browser.
  Add this page to your home screen for app-like use.</p>

  <div class="tabs">
    <div class="tab on" id="tabPortal" onclick="showTab('portal')">&#128273; Portal Route</div>
    <div class="tab" id="tabSync" onclick="showTab('sync')">&#128260; Auto Sync</div>
    <div class="tab" id="tabEntry" onclick="showTab('entry')">&#9998; Quick Entry</div>
  </div>

  <!-- PORTAL ROUTE (CAPTCHA tho official login -> reading semester -> dashboard) -->
  <div id="panelPortal">
    <div class="card" style="border:1.5px solid #1171e9">
      <label style="margin-top:0;font-size:12px">SETUP - OKKASARI (2 min), TARUVATA PRATI ROJU 30 SEC</label>
      <p style="font-size:14px;color:var(--ink);margin-top:8px;line-height:1.9">
        <b style="color:#1171e9">Step 1.</b> Kinda <b>&#128203; Copy Script</b> button tap cheyandi.<br>
        <b style="color:#1171e9">Step 2.</b> <b>&#128279; Open Official Portal</b> button tap chesi
        <b>login cheyandi</b> (CAPTCHA normal ga complete avthundi).<br>
        <b style="color:#1171e9">Step 3.</b> Bookmark create &rarr; Edit URL &rarr; paste &rarr; Save.<br>
        <b style="color:#059669">Then:</b> Portal lo login &rarr; bookmark tap &rarr;
        <b>&ldquo;Reading your semester&rdquo;</b> &rarr; <b>Overall % + Subject-wise %</b>!
      </p>
      <button class="btn" id="copyBtn" onclick="copyLoader()">&#128203; Copy Script</button>
      <div class="msg" id="copyMsg" style="display:none"></div>
      <textarea readonly id="loaderBox" style="margin-top:10px;min-height:0;height:64px;font-size:11px"
        onclick="this.select()">{{ loader }}</textarea>
      <div style="margin-top:12px">
        <a class="btn green" href="https://jntuaceastudents.classattendance.in/"
           target="_blank" rel="noopener">&#128279; Open Official Portal &rarr;</a>
      </div>
      <p style="font-size:12px;color:var(--muted);margin-top:12px;line-height:1.6">
        <b>Bookmark setup (oka sari):</b><br>
        &bull; Portal page open ayyaka Chrome &#8942; menu &rarr; <b>&#9733; (star)</b> &rarr;
        <b>Save</b> &rarr; bookmark name: <b>Attendance</b>.<br>
        &bull; &#8942; &rarr; <b>Bookmarks</b> &rarr; aa bookmark meeda &#8942; &rarr; <b>Edit</b>.<br>
        &bull; URL field lo unna text ni <b>delete</b> chesi, <b>paste</b> cheyandi
        (Step 1 lo copy chesindi) &rarr; <b>Save</b>. Done!<br>
        &bull; <b>Taruvata prati roju:</b> official portal lo login &rarr; <b>Attendance</b>
        bookmark tap &rarr; Reading your semester &rarr; attendance!
      </p>
    </div>
  </div>


  <!-- AUTO SYNC -->
  <div id="panelSync">
    <div class="card">
      <label>USERNAME (ROLL NUMBER)</label>
      <input id="syncRoll" placeholder="e.g. 23001A0204">
      <label>PASSWORD</label>
      <input id="syncPass" type="password" placeholder="Your college portal password">
      <button class="btn" id="syncBtn" onclick="doSync()">Check Attendance &rarr;</button>
      <button class="btn" id="autoBtn" onclick="toggleAutoWait()"
        style="background:#64748b;margin-top:8px">&#128276; Wait &amp; Auto-Sync when portal opens</button>
      <div class="msg" id="syncMsg"></div>
      <div class="msg" id="autoMsg" style="display:block;background:#EEF1F6;color:#66748f;
        border:1px solid #DFE4EC;margin-top:8px">Portal status: checking&hellip;</div>
      <p style="font-size:11.5px;color:var(--muted);margin-top:10px">
        We log into the official college portal with your credentials.
        Your password is never stored. If the portal is showing its CAPTCHA,
        tap <b>Wait &amp; Auto-Sync</b> &mdash; it checks every 45 seconds and syncs
        automatically the moment the portal opens. Or use Quick Entry.</p>
    </div>
  </div>

  <!-- SYNCING SCREEN (APK-style) -->
  <div id="panelSyncScreen" style="display:none;text-align:center;padding:46px 0">
    <div style="font-size:44px">&#127891;</div>
    <div id="syncTitle" style="font-size:30px;font-weight:800;letter-spacing:3px;margin-top:16px;color:#10213d">SYNCING</div>
    <div style="color:#63728a;font-size:15px;margin-top:8px">Reading your semester</div>
    <div id="syncStep" style="margin-top:22px;font-size:17px;font-weight:700;color:#1171e9">
      Processed 0 of 0 subjects &nbsp;0%</div>
    <div style="max-width:300px;margin:14px auto 0;height:8px;background:#e3ecf7;border-radius:6px;overflow:hidden">
      <div id="syncBar" style="width:0%;height:100%;background:linear-gradient(90deg,#1171e9,#073d92);border-radius:6px;transition:width .3s"></div>
    </div>
    <div style="margin-top:26px;font-size:11px;color:#63728a">Secure session &middot; jntuaceastudents.classattendance.in</div>
  </div>

  <!-- QUICK ENTRY -->
  <div id="panelEntry" style="display:none">
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

  <!-- DASHBOARD -->
  <div id="panelDash" style="display:none">
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
      <button class="btn" onclick="showTab('sync')">&#128260; Re-check</button>
      <button class="btn green" onclick="window.print()">&#128424; Print</button>
    </div>
  </div>

  <p style="text-align:center;margin-top:22px;font-size:11px;color:var(--muted)">
    &copy; 2026 JNTUACEA Attendance &middot; Secure session &middot; jntuaceastudents.classattendance.in</p>
</div>

<script>
var STATE = {name:'', roll:'', subs:[]};

function showTab(t){
  document.getElementById('panelPortal').style.display = t==='portal' ? '' : 'none';
  document.getElementById('panelSync').style.display = t==='sync' ? '' : 'none';
  document.getElementById('panelEntry').style.display = t==='entry' ? '' : 'none';
  document.getElementById('panelDash').style.display = t==='dash' ? '' : 'none';
  document.getElementById('panelSyncScreen').style.display = 'none';
  document.getElementById('tabPortal').className = 'tab' + (t==='portal'?' on':'');
  document.getElementById('tabSync').className = 'tab' + (t==='sync'?' on':'');
  document.getElementById('tabEntry').className = 'tab' + (t==='entry'?' on':'');
}

function copyLoader(){
  var txt = document.getElementById('loaderBox').value;
  if (navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(function(){
      var m = document.getElementById('copyMsg');
      m.className = 'msg ok';
      m.textContent = 'Copied! Now: Open Portal -> login -> bookmark create -> Edit URL -> paste -> Save.';
    }).catch(function(){ selectLoader(); });
  } else { selectLoader(); }
}
function selectLoader(){
  var b = document.getElementById('loaderBox');
  b.focus(); b.select();
  var m = document.getElementById('copyMsg');
  m.className = 'msg ok';
  m.textContent = 'Long-press the text above and choose Copy.';
}

var SYNC_ANIM = null;
function startSyncAnimation(){
  var total = 8;              // typical subject count; bar fills while waiting
  document.getElementById('panelPortal').style.display = 'none';
  document.getElementById('panelSync').style.display = 'none';
  document.getElementById('panelEntry').style.display = 'none';
  document.getElementById('panelDash').style.display = 'none';
  document.getElementById('panelSyncScreen').style.display = '';
  var done = 0;
  var stepEl = document.getElementById('syncStep');
  var barEl = document.getElementById('syncBar');
  stepEl.textContent = 'Processed 0 of ' + total + ' subjects  0%';
  barEl.style.width = '0%';
  SYNC_ANIM = setInterval(function(){
    done = Math.min(total, done + 1);
    var pct = Math.round(done * 100 / total);
    stepEl.textContent = 'Processed ' + done + ' of ' + total + ' subjects  ' + pct + '%';
    barEl.style.width = pct + '%';
  }, 1400);
}
function stopSyncAnimation(){
  if (SYNC_ANIM){ clearInterval(SYNC_ANIM); SYNC_ANIM = null; }
}

function msg(id, cls, text){
  var m = document.getElementById(id);
  m.className = 'msg ' + cls;
  m.textContent = text;
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
    localStorage.setItem('jnt_roll', roll);
    localStorage.setItem('jnt_name', name);
    localStorage.setItem('jnt_subs', subsText);
  } catch(e){}
  renderDash(name, roll, rows, []);
  showTab('dash');
}

function doSync(){
  var roll = document.getElementById('syncRoll').value.trim().toUpperCase();
  var pass = document.getElementById('syncPass').value;
  if (roll.length < 5 || !pass){ msg('syncMsg','err','Please enter username and password.'); return; }
  doSyncNow(roll, pass);
}

function doSyncNow(roll, pass){
  var btn = document.getElementById('syncBtn');
  btn.disabled = true; btn.textContent = 'Loading\u2026';
  msg('syncMsg','ok','');
  startSyncAnimation();
  fetch('/app/sync', {
    method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:'username='+encodeURIComponent(roll)+'&password='+encodeURIComponent(pass)
  }).then(function(r){ return r.json(); })
    .then(function(d){
      btn.disabled = false; btn.textContent = 'Check Attendance \u2192';
      stopSyncAnimation();
      if (d.error){
        if (d.error.indexOf('PORTAL-CAPTCHA-ON::') === 0){
          msg('syncMsg','err', d.error.substring('PORTAL-CAPTCHA-ON::'.length));
          showTab('portal');
        } else {
          showTab('sync');
          msg('syncMsg','err', d.error);
        }
        return;
      }
      var rows = (d.subjects||[]).map(function(s){
        return {name:s.Subject, total:s.total, present:s.present, rows:s.rows||[]};
      });
      renderDash(d.name||roll, roll + (d.cls?' : '+d.cls:''), rows, (d.subjects||[]).map(function(s){return s.rows||[];}));
      if (d.diag && d.diag.length){
        var dmsg = document.createElement('div');
        dmsg.style.cssText = 'font-size:11.5px;color:#B45309;background:#FEF3C7;border:1px solid #FDE68A;border-radius:10px;padding:10px 12px;margin-top:14px;white-space:pre-wrap';
        dmsg.textContent = 'Some subjects returned no data:\n' + d.diag.join('\n') + '\n\nRefresh try cheyandi - portal session ok aite anni vastayi.';
        document.getElementById('subjList').appendChild(dmsg);
      }
      showTab('dash');
    })
    .catch(function(e){
      btn.disabled = false; btn.textContent = 'Check Attendance \u2192';
      stopSyncAnimation();
      showTab('sync');
      msg('syncMsg','err','Could not connect. Please try again or use Quick Entry.');
    });
}

function renderDash(name, roll, rows, rowsBySubj){
  STATE.name = name; STATE.roll = roll;
  var tot = 0, pres = 0;
  STATE.subs = rows.map(function(r, i){
    tot += r.total; pres += r.present;
    return {name:r.name, total:r.total, present:r.present, rows: rowsBySubj[i] || r.rows || []};
  });
  document.getElementById('dName').textContent = name.toUpperCase();
  document.getElementById('dRoll').textContent = roll + ' : B.Tech \u00B7 JNTUACEA';
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
  STATE.subs.forEach(function(s, idx){
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

// restore quick entry values
try {
  document.getElementById('entryRoll').value = localStorage.getItem('jnt_roll')||'';
  document.getElementById('entryName').value = localStorage.getItem('jnt_name')||'';
  document.getElementById('entrySubs').value = localStorage.getItem('jnt_subs')||'';
} catch(e){}

var AUTO = {on:false, timer:null};

function setAutoMsg(t){
  var m = document.getElementById('autoMsg');
  m.textContent = t;
  m.style.display = 'block';
}

function checkStatus(cb){
  fetch('/app/status').then(function(r){ return r.json(); }).then(function(d){
    var now = new Date().toLocaleTimeString();
    if (d.open){
      setAutoMsg('\uD83D\uDFE2 Portal is OPEN (no CAPTCHA) \u2014 checked ' + now);
    } else if (d.captcha){
      setAutoMsg('\uD83D\uDD34 Portal CAPTCHA is ON \u2014 checked ' + now
        + (AUTO.on ? ' \u00B7 waiting for it to open\u2026' : ''));
    } else {
      setAutoMsg('\u26AA Could not reach the portal \u2014 checked ' + now);
    }
    if (cb) cb(d);
  }).catch(function(){
    setAutoMsg('\u26AA Could not reach the portal.');
    if (cb) cb({open:false});
  });
}

function toggleAutoWait(){
  var btn = document.getElementById('autoBtn');
  if (AUTO.on){
    AUTO.on = false;
    if (AUTO.timer) clearInterval(AUTO.timer);
    btn.textContent = '\uD83D\uDD14 Wait & Auto-Sync when portal opens';
    setAutoMsg('Auto-wait stopped.');
    return;
  }
  var roll = document.getElementById('syncRoll').value.trim().toUpperCase();
  var pass = document.getElementById('syncPass').value;
  if (roll.length < 5 || !pass){
    msg('syncMsg','err','Enter username + password first, then tap Wait & Auto-Sync.');
    return;
  }
  AUTO.on = true;
  btn.textContent = '\u23F9 Stop waiting';
  setAutoMsg('Waiting for the portal CAPTCHA to turn off\u2026 checking every 45 seconds.');
  var fire = function(d){
    if (d.open && AUTO.on){
      AUTO.on = false;
      if (AUTO.timer) clearInterval(AUTO.timer);
      btn.textContent = '\uD83D\uDD14 Wait & Auto-Sync when portal opens';
      doSyncNow(roll, pass);
      return true;
    }
    return false;
  };
  checkStatus(fire);
  AUTO.timer = setInterval(function(){ checkStatus(fire); }, 45000);
}

checkStatus();

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(function(){});
}
</script>
</body>
</html>'''


def app_page_html():
    return APP_HTML.replace('{{ loader }}', BM_LOADER)


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
                             'does not host the student pages (the portal runs multiple '
                             'copies; the one with your data has its CAPTCHA ON for servers). '
                             'Use the \u201cPortal Route\u201d tab: official website login '
                             '(CAPTCHA completes on your phone) \u2192 \u201cReading your '
                             'semester\u201d \u2192 all subject percentages.'}
        if 'CAPTCHA' in msg or 'Use https' in msg or 'verification' in msg:
            return {'error': 'PORTAL-CAPTCHA-ON::The official portal CAPTCHA is ON right now. '
                             'Servers cannot pass it - use the \u201cPortal Route\u201d tab: '
                             'official login (CAPTCHA solves on your phone) \u2192 Reading '
                             'your semester \u2192 all subjects. Or Quick Entry.'}
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
