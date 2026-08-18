import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flask import Flask, Response
try:
    import app_page
    MSG = 'app_page OK len=%d' % len(app_page.app_page_html())
except Exception as e:
    MSG = 'IMPORT FAIL: %r' % e
app = Flask(__name__)

@app.route('/', defaults={'path': ''})
@app.route('/api/index', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    return Response(MSG, mimetype='text/plain')
