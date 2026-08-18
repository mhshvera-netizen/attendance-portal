import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flask import Flask, Response
try:
    import app_page
    import scraper
    MSG = 'all imports OK'
except Exception as e:
    import traceback
    MSG = 'IMPORT FAIL: ' + traceback.format_exc()
app = Flask(__name__)

@app.route('/', defaults={'path': ''})
@app.route('/api/index', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    return Response('<pre>%s</pre>' % MSG, mimetype='text/html')
