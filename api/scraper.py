#!/usr/bin/env python3
"""Minimal server-side scraper for the JNTUACEA portal (used by /app/sync)."""
import concurrent.futures
import hashlib
import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URLS = [
    'https://jntuacea.classattendance.in/',
    'https://ekr.classattendance.in/',
    'https://jntuaceastudents.classattendance.in/',
]
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
TIMEOUT = 15


class PortalError(Exception):
    pass


def _find_login_form(soup):
    form = soup.find('form', id='loginForm')
    if form:
        return form
    for form in soup.find_all('form'):
        if form.find('input', attrs={'name': 'username'}) and \
           form.find('input', attrs={'name': 'password'}):
            return form
    return None


def _login_on(session, base, username, password):
    r = session.get(base, timeout=TIMEOUT)
    soup = BeautifulSoup(r.text, 'html.parser')
    if 'cf-turnstile' in r.text:
        raise PortalError('CAPTCHA')
    form = _find_login_form(soup)
    if not form:
        raise PortalError('route')
    payload = {}
    for inp in form.find_all('input'):
        n = inp.get('name')
        if n:
            payload[n] = inp.get('value', '')
    payload['username'] = username
    payload['password'] = password
    time.sleep(0.3)
    session.headers.update({
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': base.rstrip('/'),
        'Referer': base,
    })
    auth = session.post(base, data=payload, timeout=TIMEOUT, allow_redirects=True)
    if 'studenthome.php' not in auth.url.lower():
        asoup = BeautifulSoup(auth.text, 'html.parser')
        el = asoup.find(class_=['alert', 'text-danger', 'invalid-feedback'])
        detail = el.text.strip() if el else 'Invalid credentials or session mismatch.'
        raise PortalError('login-failed::' + detail)
    return base, session


def student_login(username, password):
    last = 'All endpoints failed.'
    for base in BASE_URLS:
        s = requests.Session()
        s.headers.update({'User-Agent': UA, 'Accept': 'text/html,*/*',
                          'Accept-Language': 'en-US,en;q=0.9'})
        try:
            return _login_on(s, base, username, password)
        except PortalError as e:
            msg = str(e)
            if msg.startswith('login-failed::'):
                raise PortalError(msg.split('::', 1)[1])
            last = msg
            continue
        except Exception:
            continue
    raise PortalError(last)


def get_student_details(session, base):
    r = session.get(base + 'studenthome.php', timeout=TIMEOUT)
    if r.status_code != 200 or not r.text:
        raise PortalError('Failed to load your official home page.')
    soup = BeautifulSoup(r.text, 'html.parser')
    d = {}
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


def get_subjects(session, base, info):
    payload = {
        'student_id': info.get('student_id'),
        'class_id': info.get('class_id'),
        'classname': info.get('classname'),
        'acad_year': info.get('acad_year'),
    }
    session.headers.update({'Referer': base + 'studenthome.php'})
    r = session.post(base + 'studentsubjects.php', data=payload, timeout=TIMEOUT)
    soup = BeautifulSoup(r.text, 'html.parser')
    subs = []
    for form in soup.find_all('form', action='studentsubatt.php'):
        data = {}
        for inp in form.find_all('input'):
            if inp.get('name'):
                data[inp['name']] = inp.get('value', '')
        if data:
            subs.append(data)
    return subs


def _parse_rows(html):
    rows = []
    for tr in re.findall(r'<tr[^>]*>[\s\S]*?</tr>', html):
        low = tr.lower()
        if 'present' not in low and 'absent' not in low:
            continue
        if '<th' in low:
            continue
        cells = [re.sub(r'<[^>]+>', ' ', c) for c in re.findall(r'<t[dh][^>]*>[\s\S]*?</t[dh]>', tr)]
        texts = [re.sub(r'\s+', ' ', c).strip() for c in cells]
        if not texts:
            continue
        status = texts[-1].lower()
        date = texts[0]
        time_s = ''
        for t in texts:
            if re.search(r'\d{1,2}:\d{2}\s*(AM|PM)', t, re.I):
                time_s = t
                break
        if status == 'present':
            rows.append({'date': date, 'status': 'P', 'time': time_s})
        elif status == 'absent':
            rows.append({'date': date, 'status': 'A', 'time': time_s})
    return rows


def _sub_attendance(session, base, payload):
    session.headers.update({'Referer': base + 'studentsubjects.php',
                            'Content-Type': 'application/x-www-form-urlencoded'})
    r = session.post(base + 'studentsubatt.php', data=payload, timeout=TIMEOUT)
    name = payload.get('sub_fullname') or payload.get('subname') or 'Subject'
    recs = _parse_rows(r.text)
    total = len(recs)
    present = sum(1 for x in recs if x['status'] == 'P')
    return {'Subject': name, 'Total Days': total, 'No. of Present': present,
            'No. of Absent': total - present, 'Details': recs}


def full_fetch(username, password):
    base, session = student_login(username, password)
    info = get_student_details(session, base)
    subjects = get_subjects(session, base, info)
    if not subjects:
        raise PortalError('Official portal returned no subjects for this account.')
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_sub_attendance, session, base, s): s for s in subjects[:16]}
        for f in concurrent.futures.as_completed(futs):
            s = futs[f]
            try:
                rows.append(f.result())
            except Exception:
                rows.append({'Subject': s.get('sub_fullname', 'Subject'),
                             'Total Days': 0, 'No. of Present': 0,
                             'No. of Absent': 0, 'Details': []})
    rows.sort(key=lambda r: r['Subject'])
    return {'details': info, 'subjects': rows}
