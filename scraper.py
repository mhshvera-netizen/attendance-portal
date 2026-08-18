#!/usr/bin/env python3
"""
JNTUACEA Official Portal Scraper
================================
Exactly like the popular JNTUA student attendance app architecture:

    student_login(username, password)   -> logs into the official portal
                                            (solves the CDN JS challenge +
                                             obfuscated integrity token)
    get_student_details(session)        -> name, roll, class, acad year
    get_subjects(session, details)      -> subject list for the student
    fetch_attendance(session, subjects) -> subject-wise records + math

All reads are for the ONE student who logged in with THEIR OWN credentials.
The password is used in memory only and never stored anywhere.

If the portal is showing Cloudflare Turnstile CAPTCHA (human bot-check),
automated login is not possible for any server app — a clear PortalError
is raised with a friendly message.
"""

import hashlib
import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = 'https://jntuaceastudents.classattendance.in/'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
TIMEOUT = 15


class PortalError(Exception):
    """Friendly, user-displayable error from the official portal."""
    pass


# ---------------------------------------------------------------- login ----
def _find_login_form(soup):
    form = soup.find('form', id='loginForm')
    if form:
        return form
    for form in soup.find_all('form'):
        if form.find('input', attrs={'name': 'username'}) and \
           form.find('input', attrs={'name': 'password'}):
            return form
    return None


def _solve_cdn_challenge(session, response):
    """Solve Hostinger CDN JS SHA-256 browser verification."""
    if response.status_code != 403:
        return response
    soup = BeautifulSoup(response.text, 'html.parser')
    script = soup.find('script', src=lambda v: v and 'hcdn-cgi/jschallenge' in v)
    if not script:
        raise PortalError(
            'Official portal is showing a CAPTCHA (human verification) right now, '
            'so automated login is blocked at the moment. '
            'Please try again later — the official portal enables and disables it.')
    try:
        script_res = session.get(urljoin(response.url, script['src']),
                                 headers={'Referer': response.url}, timeout=TIMEOUT)
        script_res.raise_for_status()
        cjs = re.search(r"const\s+cjs\s*=\s*(['\"])(.*?)\1\s*;", script_res.text)
        endpoint = re.search(r"const\s+jsChallengeUrl\s*=\s*(['\"])(.*?)\1\s*;", script_res.text)
        uri = re.search(r"const\s+uri\s*=\s*(['\"])(.*?)\1\s*;", script_res.text)
        if not cjs or not endpoint:
            raise PortalError('Official portal login verification changed. Please try again later.')
        challenge = hashlib.sha256(cjs.group(2).encode()).hexdigest()
        time.sleep(1.0)
        val_res = session.post(urljoin(response.url, endpoint.group(2)),
                               data={'challenge': challenge},
                               headers={
                                   'Content-Type': 'application/x-www-form-urlencoded',
                                   'Origin': response.url.rsplit('/', 1)[0],
                                   'Referer': response.url}, timeout=TIMEOUT)
        if val_res.status_code != 200:
            raise PortalError('Official portal verification failed. Please try again later.')
        target = urljoin(response.url, uri.group(2)) if uri else response.url
        time.sleep(1.0)
        return session.get(target, timeout=TIMEOUT)
    except PortalError:
        raise
    except Exception:
        raise PortalError('Official portal verification failed. Please try again later.')


def _load_login_page(session):
    response = session.get(BASE_URL, timeout=TIMEOUT)
    response = _solve_cdn_challenge(session, response)
    soup = BeautifulSoup(response.text, 'html.parser')
    if _find_login_form(soup):
        return response, soup
    if response.status_code == 403:
        raise PortalError('Official portal blocked this login request (403). Please try again later.')
    if 'cf-turnstile' in response.text or 'challenges.cloudflare.com' in response.text:
        raise PortalError(
            'Official portal is showing a CAPTCHA (human verification) right now, '
            'so automated login is blocked at the moment. '
            'Please try again later — the official portal enables and disables it.')
    raise PortalError('Official portal login page is unavailable right now. Please try again later.')


def student_login(username, password):
    """Authenticate with the official portal. Returns a live requests.Session.
    Raises PortalError with a friendly message on any failure."""
    session = requests.Session()
    session.headers.update({
        'Host': 'jntuaceastudents.classattendance.in',
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

    response, login_form = _load_login_page(session)
    html_content = response.text

    # Obfuscated integrity token arrays (with the known fallbacks)
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


# ------------------------------------------------------------ details -----
def get_student_details(session):
    """Parse the student's My Details card + hidden tracking parameters."""
    home_res = session.get(BASE_URL + 'studenthome.php', timeout=TIMEOUT)
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


def get_subjects(session, student_info):
    """Fetch the student's subject list (hidden form payloads)."""
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
    return subjects


# ---------------------------------------------------------- attendance ----
def _parse_attendance_rows(html_text):
    """Parse studentsubatt.php table -> [{'date':..., 'status': 'P'|'A'}]"""
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
    records = _parse_attendance_rows(res.text)
    total = len(records)
    present = sum(1 for r in records if r['status'] == 'P')
    return {
        'Subject': name,
        'Start Date': records[0]['date'] if records else '',
        'End Date': records[-1]['date'] if records else '',
        'Total Days': total,
        'No. of Present': present,
        'No. of Absent': total - present,
        'Attendance %': round((present / total) * 100, 1) if total else 0,
        'Details': records,
    }


def fetch_attendance(session, subjects):
    """Fetch subject-wise attendance sequentially (gentle with the portal)."""
    results = []
    for s in subjects:
        try:
            results.append(_attendance_for_subject(session, s))
        except Exception:
            results.append({
                'Subject': s.get('sub_fullname', 'Unknown Subject'),
                'Start Date': '', 'End Date': '',
                'Total Days': 0, 'No. of Present': 0, 'No. of Absent': 0,
                'Attendance %': 0, 'Details': [],
            })
        time.sleep(0.3)
    return results


def full_fetch(username, password):
    """One-shot: login + details + subjects + attendance.
    Returns {'details': dict, 'subjects': [result rows]}."""
    session = student_login(username, password)
    details = get_student_details(session)
    subjects = get_subjects(session, details)
    if not subjects:
        raise PortalError('Official portal returned no subjects for this account.')
    rows = fetch_attendance(session, subjects)
    return {'details': details, 'subjects': rows, 'session': session}


# ------------------------------------------------------------ test mode ----
def _stub_fetch(username, password):
    """OFFICIAL_STUB=1 → fake portal responses (used only for local testing)."""
    time.sleep(0.1)
    return {
        'details': {'Student Name': 'Abhishek Reddy', 'username': username,
                    'classname': 'II CSE', 'acad_year': '2025-26'},
        'subjects': [
            {'Subject': 'Operating Systems', 'Start Date': '2026-06-01', 'End Date': '2026-08-17',
             'Total Days': 40, 'No. of Present': 36, 'No. of Absent': 4, 'Attendance %': 90.0,
             'Details': [{'date': '2026-08-17', 'status': 'P'}, {'date': '2026-08-16', 'status': 'P'},
                         {'date': '2026-08-15', 'status': 'A'}, {'date': '2026-08-14', 'status': 'P'}]},
            {'Subject': 'Database Management Systems', 'Start Date': '2026-06-01', 'End Date': '2026-08-17',
             'Total Days': 40, 'No. of Present': 30, 'No. of Absent': 10, 'Attendance %': 75.0,
             'Details': [{'date': '2026-08-17', 'status': 'P'}, {'date': '2026-08-16', 'status': 'A'}]},
            {'Subject': 'Design & Analysis of Algorithms', 'Start Date': '2026-06-01', 'End Date': '2026-08-17',
             'Total Days': 38, 'No. of Present': 25, 'No. of Absent': 13, 'Attendance %': 65.8,
             'Details': [{'date': '2026-08-17', 'status': 'A'}, {'date': '2026-08-16', 'status': 'A'}]},
        ],
        'session': None,
    }


if os.environ.get('OFFICIAL_STUB') == '1':
    full_fetch = _stub_fetch
