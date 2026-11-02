"""Lokaler Server für den KI-Fahrzeugschein-Scanner. Nur für eigenen Rechner."""
import base64, json, os, threading, urllib.request, urllib.error, secrets, re
import psycopg
from functools import wraps
from flask import Response
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_file

ROOT=Path(__file__).resolve().parent
DATABASE_URL=os.getenv('DATABASE_URL','')
LOCK=threading.Lock()
LIMIT_CENTS=500
SCAN_CENTS=10 # konservative Anrechnung pro Versuch, keine API-Abrechnung
app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=12*1024*1024


def month(): return datetime.now().strftime('%Y-%m')

def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        expected=os.getenv('APP_PASSWORD','')
        provided=request.authorization
        if not expected:
            return jsonify(error='APP_PASSWORD fehlt: Zugriff gesperrt'),503
        if not provided or not secrets.compare_digest(provided.username or '',os.getenv('APP_USER','werkstatt')) or not secrets.compare_digest(provided.password or '',expected):
            return Response('Anmeldung erforderlich',401,{'WWW-Authenticate':'Basic realm="Fahrzeugannahme", charset="UTF-8"','Cache-Control':'no-store'})
        return fn(*args,**kwargs)
    return wrapper

@app.after_request
def no_cache(response):
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    return response

def db():
    if not DATABASE_URL:
        raise RuntimeError('DATABASE_URL fehlt. Eine dauerhafte PostgreSQL-Datenbank ist erforderlich.')
    c=psycopg.connect(DATABASE_URL)
    c.execute('CREATE TABLE IF NOT EXISTS budget (month TEXT PRIMARY KEY, cents INTEGER NOT NULL)')
    c.commit()
    return c

def current():
    with db() as c:
        row=c.execute('SELECT cents FROM budget WHERE month=%s',(month(),)).fetchone()
        return row[0] if row else 0

@app.get('/')
@auth_required
def home(): return send_file(ROOT/'index.html')

@app.get('/api/budget')
@auth_required
def budget(): return jsonify(used_eur=current()/100,limit_eur=5.0,scan_reservation_eur=.10)

@app.post('/api/scan')
@auth_required
def scan():
    origin=request.headers.get('Origin')
    if origin and origin != request.host_url.rstrip('/'):
        return jsonify(error='Ungültige Herkunft'),403
    if not os.getenv('OPENAI_API_KEY'):
        return jsonify(error='OPENAI_API_KEY fehlt. Bitte Anleitung lesen.'),503
    f=request.files.get('image')
    if not f or f.mimetype not in ('image/jpeg','image/png','image/webp'):
        return jsonify(error='Bitte JPG, PNG oder WebP hochladen.'),400
    raw=f.read()
    if not raw or len(raw)>12*1024*1024: return jsonify(error='Bild zu groß oder leer.'),400
    # Dauerhafte atomare Reservierung: sicher bei mehreren Server-Prozessen.
    # 0,10 € sind eine Scan-Quote, KEINE exakte Abrechnung.
    try:
        with db() as c:
            with c.transaction():
                c.execute('INSERT INTO budget(month,cents) VALUES (%s,0) ON CONFLICT(month) DO NOTHING',(month(),))
                row=c.execute('UPDATE budget SET cents=cents+%s WHERE month=%s AND cents+%s<=%s RETURNING cents',
                              (SCAN_CENTS,month(),SCAN_CENTS,LIMIT_CENTS)).fetchone()
                if not row:
                    return jsonify(error='Monatliche Scan-Quote ausgeschöpft.'),429
    except Exception:
        return jsonify(error='Budgetdatenbank nicht erreichbar; Scan vorsorglich gesperrt.'),503
    prompt="""Lies ausschließlich die sichtbaren Angaben aus der deutschen Zulassungsbescheinigung Teil I. Gib ein JSON-Objekt mit dem Schlüssel fields und genau diesen Schlüsseln zurück: halter, adresse_halter, hersteller, kennzeichen, typ, vin, ez, leistung, hubraum, farbe, kba. Fehlende/unsichere Werte sind leere Strings. Keine Vermutungen. C.1.1 Name und C.1.2/C.1.3 Anschrift; D.1 Hersteller; D.2/D.3 Modell; A Kennzeichen; E 17-stellige VIN; B Erstzulassung; P.2 kW; P.1 ccm; R Farbe; 2.1/2.2 HSN/TSN. Keine Angaben aus freiem Fließtext mit ähnlichen Buchstaben als VIN übernehmen. Bei Namen und Anschrift nichts erfinden. Nur JSON."""
    payload={'model':'gpt-4.1-mini','temperature':0,'max_tokens':650,'response_format':{'type':'json_object'},'messages':[{'role':'user','content':[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':f'data:{f.mimetype};base64,{base64.b64encode(raw).decode()}','detail':'high'}}]}]}
    try:
        req=urllib.request.Request('https://api.openai.com/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=90) as resp: data=json.load(resp)
        fields=json.loads(data['choices'][0]['message']['content']).get('fields',{})
        allowed=('halter','adresse_halter','hersteller','kennzeichen','typ','vin','ez','leistung','hubraum','farbe','kba')
        fields={k:str(fields.get(k,'') or '').strip()[:160] for k in allowed}
        import re
        if fields['vin'] and not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}',fields['vin'].upper()):fields['vin']=''
        if fields['leistung'] and not re.fullmatch(r'\d{1,4}(?:[.,]\d+)?(?:\s*kW)?',fields['leistung'],re.I):fields['leistung']=''
        if fields['hubraum'] and not re.fullmatch(r'\d{2,5}(?:\s*(?:cm3|ccm))?',fields['hubraum'],re.I):fields['hubraum']=''
        return jsonify(fields=fields,note='Angaben können trotz KI-Erkennung fehlerhaft sein.')
    except Exception as exc:
        # Anfragen können beim Provider trotz Zeitüberschreitung berechnet werden:
        # vorsorgliche Budgetanrechnung bleibt daher bestehen.
        return jsonify(error='KI-Anfrage fehlgeschlagen: '+str(exc)[:250]+' (0,10 € Budget vorsorglich angerechnet).'),502

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.getenv('PORT','8765')),debug=False,threaded=True)
