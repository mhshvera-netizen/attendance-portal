#!/usr/bin/env python3
"""
Official JNTUACEA portal scraper — multi-endpoint edition.

The same "JNTUACEA - Academic Record Book" application is reachable at two
hostnames:
    https://ekr.classattendance.in/            <- no CAPTCHA (preferred)
    https://jntuaceastudents.classattendance.in/ <- may show Cloudflare Turnstile

We try the CAPTCHA-free endpoint first and fall back to the other. Same
architecture as the popular JNTUA student attendance app:
    student_login() -> login (CDN JS challenge + hidden-field payload)
    get_student_details() -> name, class, academic year
    get_subjects() -> subject list
    full_fetch() -> subject-wise attendance (concurrent, gentle)

The student's password is used in memory only and never stored.
"""

import concurrent.futures
import hashlib
import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URLS = [
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


def _solve_cdn_challenge(session, response, base):
    if response.status_code != 403:
        return response
    soup = BeautifulSoup(response.text, 'html.parser')
    script = soup.find('script', src=lambda v: v and 'hcdn-cgi/jschallenge' in v)
    if not script:
        raise PortalError('Endpoint blocked this request. Trying another route.')
    try:
        script_res = session.get(urljoin(base, script['src']),
                                 headers={'Referer': response.url}, timeout=TIMEOUT)
        script_res.raise_for_status()
        cjs = re.search(r"const\s+cjs\s*=\s*(['\"])(.*?)\1\s*;", script_res.text)
        endpoint = re.search(r"const\s+jsChallengeUrl\s*=\s*(['\"])(.*?)\1\s*;", script_res.text)
        uri = re.search(r"const\s+uri\s*=\s*(['\"])(.*?)\1\s*;", script_res.text)
        if not cjs or not endpoint:
            raise PortalError('Endpoint verification changed. Trying another route.')
        challenge = hashlib.sha256(cjs.group(2).encode()).hexdigest()
        time.sleep(1.0)
        val_res = session.post(urljoin(base, endpoint.group(2)),
                               data={'challenge': challenge},
                               headers={
                                   'Content-Type': 'application/x-www-form-urlencoded',
                                   'Origin': base.rstrip('/'),
                                   'Referer': response.url}, timeout=TIMEOUT)
        if val_res.status_code != 200:
            raise PortalError('Endpoint verification failed. Trying another route.')
        target = urljoin(base, uri.group(2)) if uri else base
        time.sleep(1.0)
        return session.get(target, timeout=TIMEOUT)
    except PortalError:
        raise
    except Exception:
        raise PortalError('Endpoint verification failed. Trying another route.')


def _load_login_page(session, base):
    response = session.get(base, timeout=TIMEOUT)
    response = _solve_cdn_challenge(session, response, base)
    soup = BeautifulSoup(response.text, 'html.parser')
    if _find_login_form(soup):
        return response, soup
    if 'cf-turnstile' in response.text or 'challenges.cloudflare.com' in response.text:
        raise PortalError('Endpoint is showing a CAPTCHA. Trying another route.')
    if response.status_code == 403:
        raise PortalError('Endpoint blocked this login request. Trying another route.')
    raise PortalError('Endpoint login page unavailable. Trying another route.')


def _login_on(session, base, username, password):
    response, login_form = _load_login_page(session, base)
    html_content = response.text

    computed_name = 'a_3f754265'
    computed_value = '1c9e4f41f180f641253c1fbb861d3022'
    try:
        name_parts = re.findall(r'var nameParts = \[(.*?)\];', html_content)[0]
        computed_name = ''.join(re.findall(r'"([^"]*)"', name_parts))
    except (IndexError, TypeError):
        pass
    try:
        value_parts = re.findall(r'var valueParts = \[(.*?)\];', html_content)[0]
        computed_value = ''.join(re.findall(r'"([^"]*)"', value_parts))
    except (IndexError, TypeError):
        pass

    payload = {}
    for inp in login_form.find_all('input'):
        itype = inp.get('type')
        name_attr = inp.get('name')
        id_attr = inp.get('id')
        val_attr = inp.get('value', '')
        if itype == 'hidden':
            if name_attr == 'dummy_field' or id_attr == 'integrity_token':
                payload[computed_name] = computed_value
            elif name_attr:
                payload[name_attr] = val_attr
        elif itype == 'submit' and name_attr:
            payload[name_attr] = val_attr
    payload['username'] = username
    payload['password'] = password

    time.sleep(0.4)
    session.headers.update({
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': base.rstrip('/'),
        'Referer': base,
    })
    auth = session.post(base, data=payload, timeout=TIMEOUT, allow_redirects=True)

    if 'studenthome.php' not in auth.url.lower():
        fail_soup = BeautifulSoup(auth.text, 'html.parser')
        err_el = fail_soup.find(class_=['alert', 'text-danger', 'invalid-feedback'])
        detail = err_el.text.strip() if err_el else 'Invalid credentials or session mismatch.'
        raise PortalError('login-failed::%s' % detail)

    return base, session


def student_login(username, password):
    """Try each endpoint in order. Returns (base, session)."""
    last_err = 'All endpoints failed.'
    for base in BASE_URLS:
        session = requests.Session()
        session.headers.update({
            'Host': urljoin(base, '/').split('/')[2],
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Sec-Fetch-Dest': 'document',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        try:
            return _login_on(session, base, username, password)
        except PortalError as e:
            msg = str(e)
            if msg.startswith('login-failed::'):
                # credentials were checked — no point trying other endpoints
                raise PortalError(msg.split('::', 1)[1])
            last_err = msg
            continue
        except Exception:
            last_err = 'Could not connect to the official portal.'
            continue
    raise PortalError(last_err)


def get_student_details(session, base):
    home_res = session.get(base + 'studenthome.php', timeout=TIMEOUT)
    if home_res.status_code != 200 or not home_res.text:
        raise PortalError('Failed to load your official home page.')
    soup = BeautifulSoup(home_res.text, 'html.parser')
    details = {}
    for card in soup.find_all('div', class_='card'):
        header = card.find('div', class_='card-header')
        if header and 'My Details' in header.text:
            for li in card.find_all('li', class_='list-group-item'):
                strong = li.find('strong')
                if strong:
                    key = strong.text.replace(':', '').strip()
                    value = li.text.replace(strong.text, '').strip()
                    details[key] = value
            break
    form = soup.find('form', action='studentsubjects.php')
    if form:
        for inp in form.find_all('input', type='hidden'):
            name = inp.get('name')
            if name:
                details[name] = inp.get('value', '')
    details.setdefault('Role', 'Student')
    return details


def get_subjects(session, base, student_info):
    payload = {
        'student_id': student_info.get('student_id'),
        'class_id': student_info.get('class_id'),
        'classname': student_info.get('classname'),
        'acad_year': student_info.get('acad_year'),
    }
    session.headers.update({'Referer': base + 'studenthome.php'})
    res = session.post(base + 'studentsubjects.php', data=payload, timeout=TIMEOUT)
    if not res.text:
        return []
    soup = BeautifulSoup(res.text, 'html.parser')
    subjects = []
    for form in soup.find_all('form', action='studentsubatt.php'):
        data = {}
        for inp in form.find_all('input'):
            if inp.get('name'):
                data[inp['name']] = inp.get('value', '')
        if data:
            subjects.append(data)
    return subjects


def _parse_attendance_rows(html_text):
    soup = BeautifulSoup(html_text, 'html.parser')
    table = soup.find('table', class_='table')
    if not table:
        return []
    records = []
    for row in table.find_all('tr'):
        cols = row.find_all('td')
        if len(cols) >= 3:
            date_s = cols[0].text.strip()
            status_s = cols[2].text.strip().lower()
            if status_s in ('present', 'p'):
                st = 'P'
            elif status_s in ('absent', 'a'):
                st = 'A'
            else:
                continue
            records.append({'date': date_s, 'status': st})
    return records


def _attendance_for_subject(session, base, payload):
    session.headers.update({
        'Referer': base + 'studentsubjects.php',
        'Content-Type': 'application/x-www-form-urlencoded',
    })
    res = session.post(base + 'studentsubatt.php', data=payload, timeout=TIMEOUT)
    name = payload.get('sub_fullname') or payload.get('subname') or 'Unknown Subject'
    records = _parse_attendance_rows(res.text)
    total = len(records)
    present = sum(1 for r in records if r['status'] == 'P')
    return {
        'Subject': name,
        'Total Days': total,
        'No. of Present': present,
        'No. of Absent': total - present,
        'Attendance %': round((present / total) * 100, 1) if total else 0,
        'Details': records,
    }


def fetch_attendance(session, base, subjects):
    results = []
    for s in subjects:
        try:
            results.append(_attendance_for_subject(session, base, s))
        except Exception:
            results.append({'Subject': s.get('sub_fullname', 'Unknown Subject'),
                            'Total Days': 0, 'No. of Present': 0, 'No. of Absent': 0,
                            'Attendance %': 0, 'Details': []})
        time.sleep(0.3)
    return results


def portal_status():
    """'open' | 'captcha' | 'unknown' — best available endpoint status."""
    for base in BASE_URLS:
        try:
            r = requests.get(base, timeout=12, headers={'User-Agent': UA, 'Accept': 'text/html'})
            if r.status_code == 200 and _find_login_form(BeautifulSoup(r.text, 'html.parser')):
                if 'cf-turnstile' in r.text:
                    continue  # this endpoint has CAPTCHA; try the next
                return 'open'
        except Exception:
            continue
    return 'captcha'


def full_fetch(username, password, max_subjects=16):
    """Login (any working endpoint) + fetch everything for one student."""
    base, session = student_login(username, password)
    details = get_student_details(session, base)
    subjects = get_subjects(session, base, details)
    if not subjects:
        raise PortalError('Official portal returned no subjects for this account.')
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_attendance_for_subject, session, base, s): s
                for s in subjects[:max_subjects]}
        for f in concurrent.futures.as_completed(futs):
            s = futs[f]
            try:
                rows.append(f.result())
            except Exception:
                rows.append({'Subject': s.get('sub_fullname', 'Unknown Subject'),
                             'Total Days': 0, 'No. of Present': 0, 'No. of Absent': 0,
                             'Attendance %': 0, 'Details': []})
    rows.sort(key=lambda r: r['Subject'])
    return {'details': details, 'subjects': rows, 'base': base, 'session': session}


# ---------------------------------------------------------------- test mode --
def _stub_fetch(username, password, max_subjects=16):
    time.sleep(0.1)
    return {
        'details': {'Student Name': 'Abhishek Reddy', 'classname': 'II CSE', 'acad_year': '2025-26'},
        'subjects': [
            {'Subject': 'Operating Systems', 'Total Days': 40, 'No. of Present': 36,
             'No. of Absent': 4, 'Attendance %': 90.0,
             'Details': [{'date': '2026-08-17', 'status': 'P'}, {'date': '2026-08-16', 'status': 'P'},
                         {'date': '2026-08-15', 'status': 'A'}]},
            {'Subject': 'Database Management Systems', 'Total Days': 40, 'No. of Present': 30,
             'No. of Absent': 10, 'Attendance %': 75.0,
             'Details': [{'date': '2026-08-17', 'status': 'P'}, {'date': '2026-08-16', 'status': 'A'}]},
            {'Subject': 'Design & Analysis of Algorithms', 'Total Days': 38, 'No. of Present': 25,
             'No. of Absent': 13, 'Attendance %': 65.8,
             'Details': [{'date': '2026-08-17', 'status': 'A'}]},
        ],
    }


if os.environ.get('OFFICIAL_STUB') == '1':
    full_fetch = _stub_fetch
