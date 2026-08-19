#!/usr/bin/env python3
"""Browser Helper script (kept for reference; bookmarklet is now self-contained)."""
BM_JS = r'''// ============================================================
// JNTUACEA Attendance — Browser Helper (bookmarklet script)
// Runs INSIDE the official portal page (after you log in).
// Uses YOUR browser session (same-origin fetch + cookies),
// so Cloudflare captcha is already solved by you → works.
// Shows the dashboard overlay, and can open the app with data.
// Hosted at: /bm.js on the app domain. Bookmarklet loads it.
// ============================================================
(function () {
  if (window.__jnBM) return;
  window.__jnBM = true;

  var APP_URL = (window.__jnApp || '__JNAPP__') + '';

  function strip(s) {
    return String(s == null ? '' : s).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function delay(ms) { return new Promise(function (res) { setTimeout(res, ms); }); }
  function post(u, b) {
    var p = [];
    for (var k in b) if (Object.prototype.hasOwnProperty.call(b, k))
      p.push(encodeURIComponent(k) + '=' + encodeURIComponent(b[k] || ''));
    return fetch(u, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: p.join('&'),
      credentials: 'same-origin'
    }).then(function (r) { return r.text(); });
  }
  function get(u) { return fetch(u, { credentials: 'same-origin' }).then(function (r) { return r.text(); }); }

  function parseDetails(html) {
    var d = {};
    var re = /<li[^>]*class="list-group-item"[\s\S]*?<\/li>/g, m;
    while ((m = re.exec(html)) !== null) {
      var li = m[0];
      var sm = li.match(/<strong[^>]*>([\s\S]*?)<\/strong>/);
      if (sm) d[strip(sm[1]).replace(/:$/, '')] = strip(li.replace(/<strong[^>]*>[\s\S]*?<\/strong>/, ''));
    }
    var fm = html.match(/<form[^>]*action=["']studentsubjects\.php["'][\s\S]*?<\/form>/);
    if (fm) {
      var ins = fm[0].match(/<input[^>]*>/g) || [];
      for (var i = 0; i < ins.length; i++) {
        var nm = ins[i].match(/name=["']([^"']+)["']/);
        var vl = ins[i].match(/value=["']([^"']*)["']/);
        if (nm && vl) d[nm[1]] = vl[1];
      }
    }
    return d;
  }

  function parseSubjects(html) {
    var out = [];
    var forms = html.match(/<form[^>]*action=["']studentsubatt\.php["'][\s\S]*?<\/form>/g) || [];
    for (var i = 0; i < forms.length; i++) {
      var o = {};
      var ins = forms[i].match(/<input[^>]*>/g) || [];
      for (var j = 0; j < ins.length; j++) {
        var nm = ins[j].match(/name=["']([^"']+)["']/);
        var vl = ins[j].match(/value=["']([^"']*)["']/);
        if (nm && vl) o[nm[1]] = vl[1];
      }
      if (Object.keys(o).length) out.push(o);
    }
    return out;
  }

  function parseRows(html) {
    var tables = html.match(/<table[^>]*>[\s\S]*?<\/table>/g) || [];
    for (var ti = 0; ti < tables.length; ti++) {
      var tbl = tables[ti];
      if (!/present|absent/i.test(tbl)) continue;
      var trs = tbl.match(/<tr[^>]*>[\s\S]*?<\/tr>/g) || [];
      var statusIdx = -1, rows = [];
      for (var i = 0; i < trs.length; i++) {
        var tr = trs[i];
        var cells = tr.match(/<t[dh][^>]*>[\s\S]*?<\/t[dh]>/g) || [];
        if (/<th/i.test(tr)) {
          for (var c = 0; c < cells.length; c++) {
            if (/status|attendance/i.test(strip(cells[c]))) { statusIdx = c; break; }
          }
          continue;
        }
        var texts = [];
        for (var c = 0; c < cells.length; c++) texts.push(strip(cells[c]));
        if (!texts.length) continue;
        var idx = statusIdx >= 0 ? statusIdx : texts.length - 1;
        var status = (texts[idx] || '').toLowerCase();
        var date = '', time = '';
        for (var c = 0; c < texts.length; c++) {
          if (!date && /\d{1,2}[-\/]\d{1,2}[-\/]\d{2,4}/.test(texts[c])) date = texts[c];
          if (!time && /\d{1,2}:\d{2}\s*(AM|PM)/i.test(texts[c])) time = texts[c];
        }
        if (!date) date = texts[0] || '';
        if (status === 'present') rows.push({ d: date, t: time, s: 'P' });
        else if (status === 'absent') rows.push({ d: date, t: time, s: 'A' });
      }
      if (rows.length) return rows;
    }
    return [];
  }

  // ---------- overlay UI ----------
  var ov = null;
  function openOverlay() {
    if (ov) { ov.remove(); ov = null; }
    ov = document.createElement('div');
    ov.id = 'jnBMOverlay';
    ov.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:#f6f9fe;'
      + 'z-index:2147483647;overflow:auto;font-family:system-ui,Arial,sans-serif;'
      + 'color:#10213d;padding:16px;box-sizing:border-box';
    document.body.appendChild(ov);
    return ov;
  }
  function closeOverlay() { if (ov) { ov.remove(); ov = null; } }

  function showSync(total) {
    var o = openOverlay();
    o.innerHTML = '<div style="text-align:center;padding-top:70px">'
      + '<div style="font-size:42px">&#127891;</div>'
      + '<div style="font-size:24px;font-weight:800;letter-spacing:3px;margin-top:14px">SYNCING</div>'
      + '<div style="color:#63728a;margin-top:6px">Reading your semester (in your browser)</div>'
      + '<div id="jnBMStep" style="margin-top:22px;font-size:15px;font-weight:700;color:#1171e9">Processed 0 of ' + total + ' subjects  0%</div>'
      + '<div style="max-width:280px;margin:12px auto 0;height:8px;background:#e3ecf7;border-radius:6px;overflow:hidden">'
      + '<div id="jnBMBar" style="width:0%;height:100%;background:linear-gradient(90deg,#1171e9,#073d92);border-radius:6px;transition:width .3s"></div></div>'
      + '<div style="margin-top:26px;font-size:11px;color:#63728a">Your browser session &middot; jntuaceastudents.classattendance.in</div></div>';
  }
  function setProgress(done, total) {
    var el = document.getElementById('jnBMStep');
    var bar = document.getElementById('jnBMBar');
    if (el) el.textContent = 'Processed ' + done + ' of ' + total + ' subjects  '
      + (total ? Math.round(done * 100 / total) : 0) + '%';
    if (bar) bar.style.width = (total ? Math.round(done * 100 / total) : 0) + '%';
  }
  function showFail(msg) {
    var o = openOverlay();
    o.innerHTML = '<div style="text-align:center;padding-top:80px">'
      + '<div style="font-size:40px">&#9888;&#65039;</div>'
      + '<div style="font-size:17px;font-weight:800;margin-top:14px">' + esc(msg) + '</div>'
      + '<div style="color:#63728a;font-size:13px;margin-top:8px">Official portal lo login ayyaka malli try cheyandi.</div>'
      + '<button onclick="var e=document.getElementById(\'jnBMOverlay\');if(e)e.remove()" '
      + 'style="margin-top:18px;padding:10px 22px;border:none;border-radius:10px;background:#1171e9;color:#fff;font-size:14px;font-weight:700;cursor:pointer">Close</button></div>';
  }

  function showDash(name, roll, cls, out, totD, totP) {
    var overall = totD ? Math.round(totP * 1000 / totD) / 10 : 0;
    var ovColor = totD ? (overall >= 75 ? '#059669' : '#DC2626') : '#63728a';
    var cards = '';
    out.forEach(function (s) {
      var color = s.total ? (s.pct >= 75 ? '#059669' : (s.pct >= 60 ? '#D97706' : '#DC2626')) : '#63728a';
      var adv;
      if (!s.total) adv = 'No classes recorded yet';
      else if (s.pct >= 75) {
        var can = Math.max(0, Math.floor(s.present / 0.75 - s.total));
        adv = can > 0 ? ('Skip ' + can + ' class' + (can === 1 ? '' : 'es')) : 'Keep attending';
      } else {
        var need = Math.max(1, Math.ceil((0.75 * s.total - s.present) / 0.25));
        adv = 'Attend ' + need + ' more';
      }
      var log = '';
      if (s.rows && s.rows.length) {
        log = '<div style="display:none;margin-top:8px;border-top:1px solid #e3ecf7;padding-top:8px">'
          + s.rows.map(function (r) {
            var absent = (r.s === 'A');
            return '<div style="display:flex;justify-content:space-between;font-size:12px;color:#63728a;padding:2px 0;gap:8px">'
              + '<b style="color:#10213d">' + esc(r.d) + '</b>'
              + '<span style="color:' + (absent ? '#DC2626' : '#059669') + ';font-weight:700">' + (absent ? 'Absent' : 'Present') + '</span>'
              + '<span>' + esc(r.t || '') + '</span></div>';
          }).join('') + '</div>';
      }
      cards += '<div style="background:#fff;border:1px solid #e3ecf7;border-radius:12px;padding:12px 14px;margin-bottom:8px;cursor:pointer" '
        + 'onclick="var l=this.querySelector(\'.jnBMlog\');if(l)l.style.display=l.style.display===\'block\'?\'none\':\'block\'">'
        + '<div style="display:flex;justify-content:space-between;align-items:center">'
        + '<span style="font-weight:800;font-size:14px">' + esc(s.nm) + '</span>'
        + '<span style="font-size:16px;font-weight:800;color:' + color + '">' + s.pct + '%</span></div>'
        + '<div style="color:#63728a;font-size:12px;margin-top:2px">Tot ' + s.total + ' &middot; Att ' + s.present + ' &middot; Abs ' + (s.total - s.present) + '</div>'
        + '<div style="font-size:12px;font-weight:700;margin-top:4px;color:' + color + '">' + adv + '</div>'
        + '<div class="jnBMlog">' + log + '</div></div>';
    });

    // Build "Name present/total" lines for the app
    var lines = out.map(function (s) {
      return s.nm + ' ' + s.present + '/' + s.total;
    });
    var payload = encodeURIComponent((roll || '') + '|' + (name || '') + '|' + lines.join('\n'));
    var appLink = APP_URL + '#d=' + payload;

    var o = openOverlay();
    o.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">'
      + '<div style="font-weight:800;color:#1171e9">&#127891; JNTUACEA Attendance <span style="font-size:10px;color:#059669">(in your browser)</span></div>'
      + '<button onclick="var e=document.getElementById(\'jnBMOverlay\');if(e)e.remove()" '
      + 'style="border:none;background:#eef1f6;border-radius:8px;padding:6px 12px;font-size:13px;font-weight:700;color:#63728a;cursor:pointer">Close</button></div>'
      + '<div style="font-size:20px;font-weight:800;text-transform:uppercase">' + esc(name || '') + '</div>'
      + '<div style="color:#63728a;font-size:13px;margin-top:2px">' + esc(roll || '') + (cls ? '  :  ' + esc(cls) : '') + '</div>'
      + '<div style="background:#fff;border:1px solid #e3ecf7;border-radius:16px;padding:16px;text-align:center;margin:14px 0">'
      + '<div style="font-size:10px;font-weight:800;letter-spacing:1.4px;color:#63728a">OVERALL ATTENDANCE</div>'
      + '<div style="font-size:44px;font-weight:800;color:' + ovColor + '">' + overall + '%</div>'
      + '<div style="display:flex;justify-content:center;gap:26px;margin-top:8px">'
      + '<div><div style="font-size:18px;font-weight:800">' + totD + '</div><div style="font-size:10px;letter-spacing:1px;color:#63728a;font-weight:800">TOTAL</div></div>'
      + '<div><div style="font-size:18px;font-weight:800;color:#059669">' + totP + '</div><div style="font-size:10px;letter-spacing:1px;color:#63728a;font-weight:800">ATT</div></div>'
      + '<div><div style="font-size:18px;font-weight:800;color:#DC2626">' + (totD - totP) + '</div><div style="font-size:10px;letter-spacing:1px;color:#63728a;font-weight:800">ABS</div></div></div>'
      + (totD ? '<div style="margin-top:10px;font-size:13px;font-weight:700;color:' + ovColor + '">'
        + (overall >= 75
          ? ('Overall safe to skip ' + Math.max(0, Math.floor(totP / 0.75 - totD)) + ' class'
             + (Math.max(0, Math.floor(totP / 0.75 - totD)) === 1 ? '' : 'es') + ' while staying above 75%')
          : ('Attend ' + Math.max(1, Math.ceil((0.75 * totD - totP) / 0.25)) + ' more classes to reach 75% overall'))
        + '</div>' : '')
      + '<a href="' + appLink + '" target="_blank" rel="noopener" '
      + 'style="display:block;text-align:center;margin-top:14px;padding:13px;border-radius:12px;background:linear-gradient(135deg,#1171e9,#073d92);color:#fff;font-size:15px;font-weight:800;text-decoration:none">&#128241; Open in App (auto-fills data)</a>'
      + '<button onclick="var t=document.createElement(\'textarea\');t.value=window.__jnBMLines||\'\';document.body.appendChild(t);t.select();try{document.execCommand(\'copy\')}catch(e){}t.remove();this.textContent=\'Copied!\';var b=this;setTimeout(function(){b.textContent=\'Copy lines\'},1500)" '
      + 'style="display:block;width:100%;margin-top:8px;padding:11px;border:1.5px solid #1171e9;border-radius:12px;background:#fff;color:#1171e9;font-size:14px;font-weight:800;cursor:pointer">&#128203; Copy lines</button>'
      + '<div style="font-size:11px;font-weight:800;letter-spacing:1.4px;color:#63728a;margin:16px 0 8px">SUBJECTS (' + out.length + ')</div>'
      + cards
      + '<p style="text-align:center;font-size:11px;color:#63728a;margin-top:16px">Subject click cheste date-wise log expand avthundi</p>';

    window.__jnBMLines = lines.join('\n');
  }

  // ---------- main flow (same logic as APK/extension) ----------
  function runSync() {
    var name = '', roll = '', cls = '', baseBody = {};
    get('studenthome.php').then(function (home) {
      if (/name=["']username["']/.test(home)) {
        showFail('Please login first (username + password + CAPTCHA), then try again.');
        throw 'stop';
      }
      var d = parseDetails(home);
      Object.keys(d).forEach(function (k) {
        var lk = k.toLowerCase();
        if (!name && lk.indexOf('name') >= 0) name = d[k];
        if (!roll && (lk.indexOf('roll') >= 0 || lk.indexOf('ht') >= 0 || lk.indexOf('admission') >= 0)) roll = d[k];
        if (!cls && (lk === 'class name' || lk === 'classname')) cls = d[k];
        if (!cls && lk.indexOf('class') >= 0 && !/^\d+$/.test(d[k])) cls = d[k];
      });
      if (!roll) roll = d.username || '';
      if (!name) name = roll;
      baseBody = { student_id: d.student_id, class_id: d.class_id,
        classname: d.classname, acad_year: d.acad_year };
      return post('studentsubjects.php', baseBody);
    }).then(function (html) {
      var subjects = parseSubjects(html);
      if (!subjects.length) { showFail('No subjects found. Login ayyaka malli try cheyandi.'); throw 'stop'; }
      showSync(subjects.length);
      var chain = Promise.resolve();
      var out = [], totD = 0, totP = 0;
      subjects.forEach(function (sub) {
        chain = chain.then(function () {
          var nm = sub.sub_fullname || sub.subname || 'Subject';
          return post('studentsubatt.php', sub).then(function (h) {
            var recs = parseRows(h);
            if (!recs.length) {
              var merged = {};
              for (var k in baseBody) merged[k] = baseBody[k];
              for (var k2 in sub) merged[k2] = sub[k2];
              return post('studentsubjects.php', merged).then(function (page) {
                var subs2 = parseSubjects(page);
                var fresh = null;
                for (var i = 0; i < subs2.length; i++) {
                  if ((subs2[i].sub_fullname || subs2[i].subname || '') === nm) { fresh = subs2[i]; break; }
                }
                if (!fresh && subs2.length === 1) fresh = subs2[0];
                if (!fresh) return recs;
                return post('studentsubatt.php', fresh).then(function (h2) {
                  var r2 = parseRows(h2);
                  return r2.length ? r2 : recs;
                });
              });
            }
            return recs;
          }).then(function (recs) {
            var total = recs.length, present = 0;
            recs.forEach(function (r) { if (r.s === 'P') present++; });
            var pct = total ? Math.round(present * 1000 / total) / 10 : 0;
            totD += total; totP += present;
            out.push({ nm: nm, total: total, present: present, pct: pct, rows: recs.slice(-250) });
            setProgress(out.length, subjects.length);
            return delay(400);
          });
        });
      });
      return chain.then(function () { return { out: out, totD: totD, totP: totP }; });
    }).then(function (res) {
      if (!res) return;
      showDash(name, roll, cls, res.out, res.totD, res.totP);
    }).catch(function (e) {
      if (e !== 'stop') showFail('Could not read attendance. Please try again.');
    });
  }

  // Floating button on portal pages (manual trigger)
  function attachButton() {
    if (!document.body) { setTimeout(attachButton, 300); return; }
    if (document.getElementById('jnBMFloating')) return;
    var b = document.createElement('div');
    b.id = 'jnBMFloating';
    b.textContent = '\uD83D\uDCCA Attendance';
    b.style.cssText = 'position:fixed;bottom:20px;right:16px;z-index:2147483646;background:#1171e9;'
      + 'color:#fff;padding:13px 18px;border-radius:30px;font:bold 15px system-ui,Arial,sans-serif;'
      + 'box-shadow:0 4px 14px rgba(0,0,0,.4);cursor:pointer';
    b.onclick = function () { runSync(); };
    document.body.appendChild(b);
  }
  attachButton();

  // Auto-run when the student lands on their home page after login
  function looksLoggedIn(){
    try {
      var bodyText = document.body ? document.body.innerHTML : '';
      return /studenthome/i.test(location.href) || /logout/i.test(bodyText) || /my details/i.test(bodyText);
    } catch(e){ return false; }
  }
  if (looksLoggedIn()) {
    setTimeout(runSync, 700);
  }
})();
'''

def bm_js():
    return BM_JS
