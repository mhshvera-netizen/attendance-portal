#!/usr/bin/env python3
# PythonAnywhere WSGI config — TEMPLATE
# 1. Replace YOUR_USERNAME with your PythonAnywhere username (2 places)
# 2. In the Web tab, set the WSGI file path to this file's location
#    (default: /var/www/YOUR_USERNAME_pythonanywhere_com_wsgi.py)
#    and paste the lines below into it.

import sys
path = '/home/YOUR_USERNAME'
if path not in sys.path:
    sys.path.insert(0, path)

from app import wsgi_application as application
