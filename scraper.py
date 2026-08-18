#!/usr/bin/env python3
"""
Official JNTUACEA portal sync (Option A) — 'Sync from Official Portal'.

Logs into https://jntuaceastudents.classattendance.in/ with the STUDENT'S OWN
credentials (Roll Number + password), reads that ONE student's attendance and
returns structured records — exactly like the popular open-source student app.

Rules of politeness:
  * one student at a time, sequential requests with small delays
  * read-only — never writes anything to the official portal
  * the student's password is used in-memory only and NEVER stored

NOTE: the portal changes its protection often. If it blocks automated sign-in
(Cloudflare Turnstile / new challenge), this raises PortalError with a clear
message — the app shows it nicely and nothing breaks.
"""

import hashlib
import os
import re
import time

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = 'https://jntuaceastudents.classattendance.in/'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
TIMEOUT = 15


class PortalError(Exception):
    """Friendly, user-displayable error."""
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


def _solve_hcdn(session, response):
    """Solve Hostinger CDN's JS SHA-256 browser challenge (like the student app)."""
    if response.status_code != 403:
        return response
    soup = BeautifulSoup(response.text, 'html.parser')
    script = soup.find('script', src=lambda v: v and 'hcdn-cgi/jschallenge' in v)
    if not script:
        # Cloudflare Turnstile or some other protection
        if 'challenges.cloudflare.com' in response.text or 'turnstile' in response.text.lower():
            raise PortalError(
                'Official portal is showing Cloudflare CAPTCHA protection right now. '
                'Server-side sync is blocked for the moment. '
                'Please use the Import Data tab instead, or try again later.')
        return response
    try:
        script_res = session.get(urljoin(response.url, script['src']),
                                 headers={'Referer': response.url}, timeout=TIMEOUT)
        script_res.raise_for_status()
        cjs = re.search(r"const\s+cjs\s*=\s*(['\"])(.*?)\1\s*;", script_res.text)
        endpoint = re.search(r"const\s+jsChallengeUrl\s*=\s*(['\"])(.*?)\1\s*;", script_res.text)
        uri = re.search(r"const\s+uri\s*=\s*(['\"])(.*?)\1\s*;", script_res.text)
        if not cjs or not endpoint:
            raise PortalError('Portal login verification changed. Please try again later.')
        challenge = hashlib.sha256(cjs.group(2).encode()).hexdigest()
        validation_url = urljoin(response.url, endpoint.group(2))
        time.sleep(1.2)
        val_res = session.post(validation_url, data={'challenge': challenge},
                               headers={
                                   'Content-Type': 'application/x-www-form-urlencoded',
                                   'Origin': response.url.rsplit('/', 1)[0],
                                   'Referer': response.url}, timeout=TIMEOUT)
        if val_res.status_code != 200:
            raise PortalError('Portal verification failed. Please try again later.')
        target = urljoin(response.url, uri.group(2)) if uri else response.url
        time.sleep(1.0)
        return session.get(target, timeout=TIMEOUT)
    except PortalError:
        raise
    except Exception:
        raise PortalError('Portal verification failed. Please try again later.')


def _load_login_page(session):
    response = session.get(BASE_URL, timeout=TIMEOUT)
    response = _solve_hcdn(session, response)
    soup = BeautifulSoup(response.text, 'html.parser')
    if _find_login_form(soup):
        return response, soup
    if response.status_code == 403:
        raise PortalError('Official portal blocked this login request (403). Please try again later.')
    if 'turnstile' in response.text.lower() or 'challenges.cloudflare.com' in response.text:
        raise PortalError(
            'Official portal is showing Cloudflare CAPTCHA protection right now, so automated '
            'sync is blocked at the moment. Please try again later, or use the '
            'Admin → Import Data option instead.')
    raise PortalError('Official portal login page is unavailable right now.')


def _login(username, password):
    session = requests.Session()
    session.headers.update({
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Upgrade-Insecure-Requests': '1',
    })
    response, soup = _load_login_page(session)
    html_content = response.text

    # Obfuscated integrity token arrays (fallbacks from the student app)
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

    login_form = _find_login_form(soup)
    if login_form is None:
        raise PortalError('Login form not found on official portal (structure changed).')
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
        'Origin': BASE_URL.rstrip('/'),
        'Referer': BASE_URL,
    })
    auth = session.post(BASE_URL, data=payload, timeout=TIMEOUT, allow_redirects=True)
    if 'studenthome.php' not in auth.url.lower():
        fail_soup = BeautifulSoup(auth.text, 'html.parser')
        err_el = fail_soup.find(class_=['alert', 'text-danger', 'invalid-feedback'])
        detail = err_el.text.strip() if err_el else 'Invalid credentials or session mismatch.'
        raise PortalError('Official portal rejected login: %s' % detail)
    return session


def _student_details(session):
    res = session.get(BASE_URL + 'studenthome.php', timeout=TIMEOUT)
    if res.status_code != 200 or not res.text:
        raise PortalError('Failed to load your official home page.')
    soup = BeautifulSoup(res.text, 'html.parser')
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
    return details


def _subjects(session, student_info):
    payload = {
        'student_id': student_info.get('student_id'),
        'class_id': student_info.get('class_id'),
        'classname': student_info.get('classname'),
        'acad_year': student_info.get('acad_year'),
    }
    session.headers.update({'Referer': BASE_URL + 'studenthome.php'})
    res = session.post(BASE_URL + 'studentsubjects.php', data=payload, timeout=TIMEOUT)
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
    return subjects[:25]


def parse_attendance_table(html_text):
    """Parse the studentsubatt.php response into [{date, status}] records.
    status: 'P' (Present) or 'A' (Absent). Non-marked rows are skipped."""
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


def _attendance_for_subject(session, payload):
    session.headers.update({
        'Referer': BASE_URL + 'studentsubjects.php',
        'Content-Type': 'application/x-www-form-urlencoded',
    })
    res = session.post(BASE_URL + 'studentsubatt.php', data=payload, timeout=TIMEOUT)
    name = payload.get('sub_fullname') or payload.get('subname') or 'Unknown Subject'
    return {'subject': name, 'records': parse_attendance_table(res.text)}


def _parse_class(cls):
    """Best-effort branch/year from official 'Class' text (e.g. 'II CSE' / '2 ECE')."""
    branch = 'CSE'
    year = 2
    cl = (cls or '').upper()
    for b in ('CSE', 'ECE', 'EEE', 'ME', 'CE'):
        if b in cl:
            branch = b
            break
    m = re.search(r'\bIV\b', cl)
    if m:
        year = 4
    elif re.search(r'\bIII\b', cl):
        year = 3
    elif re.search(r'\bII\b', cl):
        year = 2
    elif re.search(r'\bI\b', cl):
        year = 1
    else:
        m = re.search(r'\b([1-4])\b', cl)
        if m:
            year = int(m.group(1))
    return branch, year


def official_fetch(username, password, max_subjects=25, polite_delay=0.4):
    """Full sync for one student. Returns:
    {'name': str, 'branch': str, 'year': int,
     'subjects': [{'subject': name, 'records': [{'date','status'}...]}...]}
    Raises PortalError with a friendly message on any failure."""
    session = _login(username, password)
    info = _student_details(session)
    name = ''
    for k, v in info.items():
        if 'name' in k.lower() and v:
            name = v.strip()
            break
    if not name:
        name = username
    cls = info.get('Class') or info.get('Class Name') or ''
    branch, year = _parse_class(cls)
    subs = _subjects(session, info)
    if not subs:
        raise PortalError('Official portal returned no subjects for this account.')
    out = []
    for s in subs[:max_subjects]:
        try:
            out.append(_attendance_for_subject(session, s))
        except Exception:
            out.append({'subject': s.get('sub_fullname', 'Unknown Subject'), 'records': []})
        time.sleep(polite_delay)  # be gentle with the portal
    return {'name': name, 'branch': branch, 'year': year, 'subjects': out}


def _stub_fetch(username, password, max_subjects=12, polite_delay=0.1):
    """TEST MODE ONLY (OFFICIAL_STUB=1): fake official portal responses."""
    time.sleep(0.1)
    return {
        'name': username + ' (Stub Student)',
        'branch': 'CSE',
        'year': 2,
        'subjects': [
            {'subject': 'Operating Systems',
             'records': [{'date': '2026-06-01', 'status': 'P'},
                         {'date': '2026-06-02', 'status': 'A'},
                         {'date': '2026-06-03', 'status': 'P'}]},
            {'subject': 'Database Management Systems',
             'records': [{'date': '2026-06-01', 'status': 'P'},
                         {'date': '2026-06-03', 'status': 'P'}]},
        ],
    }


if os.environ.get('OFFICIAL_STUB') == '1':
    official_fetch = _stub_fetch
