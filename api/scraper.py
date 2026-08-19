#!/usr/bin/env python3
"""
JNTUACEA portal scraper - server-side (used by /app/sync on Vercel).

FIX for the "only one subject has data" bug:
  The portal runs on PHP sessions. Sending attendance requests IN PARALLEL
  (ThreadPool) makes the portal's session lock drop every request except the
  first one. So we now fetch subjects SEQUENTIALLY, one after another, with a
  short polite delay - exactly like a real browser click flow.

Per subject we try up to 3 request patterns (like the working Android app):
  A. POST studentsubatt.php with the subject's hidden form fields
  B. Re-POST studentsubjects.php with base+subject fields, find the fresh
     form, then POST studentsubatt.php
  C. GET studentsubatt.php?field1=..&field2=.. (query string)

Login:
  * main portal (jntuaceastudents.classattendance.in) has the real data.
    When it shows Cloudflare Turnstile (CAPTCHA), server login is impossible
    - a clear 'CAPTCHA' PortalError is raised.
  * the mirror copies (jntuacea / ekr) accept credentials but are missing the
    student pages - they are used as fallback attempts only.
"""

import os
import re
import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

BASE_URLS = [
    'https://jntuaceastudents.classattendance.in/',
    'https://jntuacea.classattendance.in/',
    'https://ekr.classattendance.in/',
]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
TIMEOUT = 15

# allow local end-to-end testing against a mock portal
_ENV_BASE = os.environ.get('PORTAL_BASE')
if _ENV_BASE:
    BASE_URLS = [_ENV_BASE]


class PortalError(Exception):
    pass


# --------------------------------------------------------------- helpers --
def _find_login_form(soup):
    form = soup.find('form', id='loginForm')
    if form:
        return form
    for form in soup.find_all('form'):
        if form.find('input', attrs={'name': 'username'}) and \
           form.find('input', attrs={'name': 'password'}):
            return form
    return None


def _classify(html):
    if not html:
        return 'empty'
    if re.search(r'cf-turnstile|challenges\.cloudflare', html, re.I):
        return 'captcha-page'
    if re.search(r'This Page Does Not Exist', html, re.I):
        return '404'
    if re.search(r'name=["\']username["\']', html) and \
       re.search(r'name=["\']password["\']', html):
        return 'login-page'
    if re.search(r'present|absent', html, re.I):
        return 'has-rows'
    return 'no-data (%db)' % len(html)


def _post(session, url, fields):
    return session.post(url, data=fields,
                        headers={'Content-Type': 'application/x-www-form-urlencoded'},
                        timeout=TIMEOUT).text


# --------------------------------------------------------------- parsing --
def _parse_rows(html):
    """Column-aware: header row locates the Status column; a data row counts
    only when that column says exactly Present/Absent. Summary rows are never
    counted."""
    rows = []
    tables = re.findall(r'<table[^>]*>[\s\S]*?</table>', html)
    for tbl in tables:
        if not re.search(r'present|absent', tbl, re.I):
            continue
        trs = re.findall(r'<tr[^>]*>[\s\S]*?</tr>', tbl)
        status_idx = -1
        for tr in trs:
            cells = re.findall(r'<t[dh][^>]*>[\s\S]*?</t[dh]>', tr)
            is_header = '<th' in tr.lower()
            if is_header:
                for c, cell in enumerate(cells):
                    if re.search(r'status|attendance',
                                 re.sub(r'<[^>]+>', ' ', cell), re.I):
                        status_idx = c
                        break
                continue
            texts = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', c)).strip()
                     for c in cells]
            if not texts:
                continue
            idx = status_idx if status_idx >= 0 else len(texts) - 1
            status = texts[idx].lower() if idx < len(texts) else ''
            date = ''
            time_s = ''
            for t in texts:
                if not date and re.search(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', t):
                    date = t
                if not time_s and re.search(r'\d{1,2}:\d{2}\s*(AM|PM)', t, re.I):
                    time_s = t
            if not date:
                date = texts[0]
            if status == 'present':
                rows.append({'date': date, 'status': 'P', 'time': time_s})
            elif status == 'absent':
                rows.append({'date': date, 'status': 'A', 'time': time_s})
        if rows:
            return rows
    return rows


def _parse_details(html):
    d = {}
    soup = BeautifulSoup(html, 'html.parser')
    for card in soup.find_all('div', class_='card'):
        header = card.find('div', class_='card-header')
        if header and 'My Details' in header.text:
            for li in card.find_all('li', class_='list-group-item'):
                strong = li.find('strong')
                if strong:
                    key = strong.text.replace(':', '').strip()
                    val = li.text.replace(strong.text, '').strip()
                    d[key] = val
            break
    form = soup.find('form', action='studentsubjects.php')
    if form:
        for inp in form.find_all('input', type='hidden'):
            if inp.get('name'):
                d[inp.get('name')] = inp.get('value', '')
    return d


def _parse_subject_forms(html):
    subs = []
    soup = BeautifulSoup(html, 'html.parser')
    for form in soup.find_all('form', action='studentsubatt.php'):
        data = {}
        for inp in form.find_all('input'):
            if inp.get('name'):
                data[inp['name']] = inp.get('value', '')
        if data:
            subs.append(data)
    return subs


# ----------------------------------------------------------------- login --
def student_login(username, password):
    # Fast check: if the MAIN portal is showing its CAPTCHA, server login is
    # impossible AND the mirror copies reject/confuse real credentials - so we
    # stop right here with a clean message instead of "Invalid credentials".
    try:
        r0 = requests.get(BASE_URLS[0], timeout=10,
                          headers={'User-Agent': UA, 'Accept': 'text/html'})
        if 'cf-turnstile' in (r0.text or ''):
            raise PortalError('CAPTCHA')
    except PortalError:
        raise
    except Exception:
        pass
    last = 'All endpoints failed.'
    for base in BASE_URLS:
        session = requests.Session()
        session.headers.update({
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        try:
            r = session.get(base, timeout=TIMEOUT)
            if 'cf-turnstile' in r.text:
                raise PortalError('CAPTCHA')
            form = _find_login_form(BeautifulSoup(r.text, 'html.parser'))
            if not form:
                raise PortalError('route')
            payload = {}
            for inp in form.find_all('input'):
                n = inp.get('name')
                if n:
                    payload[n] = inp.get('value', '')
            payload['username'] = username
            payload['password'] = password
            time.sleep(0.4)
            auth = session.post(base, data=payload, timeout=TIMEOUT,
                                allow_redirects=True)
            if 'studenthome.php' not in auth.url.lower():
                asoup = BeautifulSoup(auth.text, 'html.parser')
                el = asoup.find(class_=['alert', 'text-danger', 'invalid-feedback'])
                detail = el.text.strip() if el else 'Invalid credentials or session mismatch.'
                raise PortalError('login-failed::' + detail)
            time.sleep(0.5)
            return session, base
        except PortalError as e:
            msg = str(e)
            if msg.startswith('login-failed::'):
                # credentials were checked - no point trying other endpoints
                raise PortalError(msg.split('::', 1)[1])
            last = msg
            continue
        except Exception:
            last = 'could not connect'
            continue
    raise PortalError(last)


# -------------------------------------------------------------- fetching --
def _fetch_subject(session, base, base_body, sub):
    """Sequential 3-pattern fetch for ONE subject. Returns (rows, diagnostics)."""
    name = sub.get('sub_fullname') or sub.get('subname') or 'Subject'
    h1 = _post(session, base + 'studentsubatt.php', sub)
    c1 = _classify(h1)
    if c1 == 'has-rows':
        return _parse_rows(h1), 'A(' + c1 + ')'
    # attempt B: re-select to get a fresh form, then submit it
    merged = dict(base_body)
    merged.update(sub)
    h2 = _post(session, base + 'studentsubjects.php', merged)
    fresh = None
    subs2 = _parse_subject_forms(h2)
    for s2 in subs2:
        got = s2.get('sub_fullname') or s2.get('subname') or ''
        if got and got == name:
            fresh = s2
            break
    if fresh is None and len(subs2) == 1:
        fresh = subs2[0]
    if fresh:
        h3 = _post(session, base + 'studentsubatt.php', fresh)
        c3 = _classify(h3)
        if c3 == 'has-rows':
            return _parse_rows(h3), 'B(' + c1 + '->' + c3 + ')'
    else:
        c3 = 'B(no-fresh-form)'
    # attempt C: GET query string
    qs = urlencode(sub)
    h4 = session.get(base + 'studentsubatt.php?' + qs, timeout=TIMEOUT).text
    c4 = _classify(h4)
    if c4 == 'has-rows':
        return _parse_rows(h4), 'C(' + c1 + '->' + c4 + ')'
    return [], c1 + ' -> ' + c3 + ' -> ' + c4


def full_fetch(username, password, max_subjects=16):
    session, base = student_login(username, password)
    info = _parse_details(
        session.get(base + 'studenthome.php', timeout=TIMEOUT).text)
    subj_html = _post(session, base + 'studentsubjects.php', {
        'student_id': info.get('student_id'),
        'class_id': info.get('class_id'),
        'classname': info.get('classname'),
        'acad_year': info.get('acad_year'),
    })
    subjects = _parse_subject_forms(subj_html)
    if not subjects:
        raise PortalError('Official portal returned no subjects for this account.')
    base_body = {
        'student_id': info.get('student_id'),
        'class_id': info.get('class_id'),
        'classname': info.get('classname'),
        'acad_year': info.get('acad_year'),
    }
    out = []
    diag = []
    # SEQUENTIAL - the portal's PHP session cannot handle parallel requests
    for sub in subjects[:max_subjects]:
        rows, diag_msg = _fetch_subject(session, base, base_body, sub)
        name = sub.get('sub_fullname') or sub.get('subname') or 'Subject'
        total = len(rows)
        present = sum(1 for r in rows if r['status'] == 'P')
        if total == 0:
            diag.append('%s: %s' % (name, diag_msg))
        out.append({
            'Subject': name,
            'Total Days': total,
            'No. of Present': present,
            'No. of Absent': total - present,
            'Details': rows,
        })
        time.sleep(0.6)  # polite delay - keeps the session alive and unthrottled
    out.sort(key=lambda r: r['Subject'])
    return {'details': info, 'subjects': out, 'diag': diag}


def portal_status():
    """'open' | 'captcha' | 'unknown' for the main portal."""
    try:
        r = requests.get(BASE_URLS[0], timeout=10,
                         headers={'User-Agent': UA, 'Accept': 'text/html'})
        txt = r.text or ''
        if r.status_code == 200 and 'loginForm' in txt and 'cf-turnstile' not in txt:
            return 'open'
        if 'cf-turnstile' in txt:
            return 'captcha'
    except Exception:
        pass
    return 'unknown'
