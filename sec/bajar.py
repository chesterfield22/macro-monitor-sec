"""
Macro Monitor — descarga de estados financieros anuales de la SEC (XBRL companyfacts) para el módulo de crédito de Montos.

Fuente: API oficial de la SEC (https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json) y el listado oficial de
tickers (https://www.sec.gov/files/company_tickers.json). La SEC exige un User-Agent con contacto: variable de entorno
SEC_CONTACTO (secreto del repositorio; no queda en el código).

Salida (carpeta data/):
  data/<TICKER>.json  misma estructura que companyfacts, filtrada a: formularios anuales (20-F, 20-F/A, 40-F, 10-K, 10-K/A),
                      monedas USD y ARS, cierres desde ANIO_MIN. Sin transformar valores (trazabilidad: accn y filed de cada hecho).
  data/index.json     {ticker: {cik, nombre, actualizado, hechos, fuente, error, ultimo_en_xbrl, anuales_presentados}} y fecha
                      de la corrida. anuales_presentados (de data.sec.gov/submissions) permite ver si un 20-F ya presentado
                      todavía no tiene datos XBRL en companyfacts.
Si un emisor falla, se conserva el archivo anterior y el error queda en index.json.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(RAIZ, 'data')
FORMULARIOS = {'20-F', '20-F/A', '40-F', '10-K', '10-K/A'}
MONEDAS = {'USD', 'ARS'}
ANIO_MIN = 2017
PAUSA = 0.25          # la SEC admite hasta 10 consultas por segundo
URL_TICKERS = 'https://www.sec.gov/files/company_tickers.json'
URL_FACTS = 'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
URL_SUBM = 'https://data.sec.gov/submissions/CIK{cik}.json'


def pedir(url, contacto, intentos=3):
    req = urllib.request.Request(url, headers={'User-Agent': 'MacroMonitor-Montos ' + contacto, 'Accept-Encoding': 'identity'})
    for k in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:      # noqa: BLE001 — se reintenta y se informa
            ultimo = e
            time.sleep(2 * (k + 1))
    raise ultimo


def filtrar(cf, anio_min=ANIO_MIN):
    """companyfacts → misma estructura con solo hechos anuales en USD/ARS desde anio_min. Devuelve (dict, cantidad)."""
    out = {'cik': cf.get('cik'), 'entityName': cf.get('entityName'), 'facts': {}}
    n = 0
    for tax, tags in (cf.get('facts') or {}).items():
        if tax not in ('ifrs-full', 'us-gaap', 'dei'):
            continue
        for tag, d in tags.items():
            units = {}
            for mon, lista in (d.get('units') or {}).items():
                if mon not in MONEDAS:
                    continue
                sel = [x for x in lista if x.get('form') in FORMULARIOS and str(x.get('end', ''))[:4].isdigit()
                       and int(str(x['end'])[:4]) >= anio_min]
                if sel:
                    units[mon] = sel
                    n += len(sel)
            if units:
                out['facts'].setdefault(tax, {})[tag] = {'units': units}
    return out, n


def ultimos_anuales(sub):
    """submissions → los 3 formularios anuales más recientes: [{form, presentado, periodo, accn, xbrl, ixbrl}]."""
    r = (sub.get('filings') or {}).get('recent') or {}
    out = []
    for i, f in enumerate(r.get('form', [])):
        if f in FORMULARIOS:
            out.append({'form': f, 'presentado': r['filingDate'][i], 'periodo': r['reportDate'][i], 'accn': r['accessionNumber'][i],
                        'xbrl': r.get('isXBRL', [None] * (i + 1))[i], 'ixbrl': r.get('isInlineXBRL', [None] * (i + 1))[i]})
    return sorted(out, key=lambda x: x['presentado'], reverse=True)[:3]


def ultimo_en_xbrl(filtrado):
    """Fecha de presentación más reciente entre los hechos guardados."""
    mx = ''
    for tags in filtrado['facts'].values():
        for d in tags.values():
            for lista in d['units'].values():
                for x in lista:
                    mx = max(mx, x.get('filed', ''))
    return mx


def main():
    contacto = os.environ.get('SEC_CONTACTO', '').strip()
    if not contacto:
        print('Falta el secreto SEC_CONTACTO (contacto para el User-Agent de la SEC).')
        sys.exit(1)
    with open(os.path.join(RAIZ, 'sec', 'tickers.txt'), encoding='utf-8') as f:
        tickers = [t.strip().upper() for t in f if t.strip() and not t.startswith('#')]
    os.makedirs(DATA, exist_ok=True)
    ruta_idx = os.path.join(DATA, 'index.json')
    idx = json.load(open(ruta_idx, encoding='utf-8')) if os.path.exists(ruta_idx) else {}
    idx.setdefault('emisores', {})
    mapa = {str(v['ticker']).upper(): v for v in pedir(URL_TICKERS, contacto).values()}
    time.sleep(PAUSA)
    ahora = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    errores = 0
    for t in tickers:
        reg = idx['emisores'].setdefault(t, {})
        if t not in mapa:
            reg['error'] = 'ticker no figura en company_tickers.json de la SEC'
            errores += 1
            continue
        cik = str(mapa[t]['cik_str']).zfill(10)
        url = URL_FACTS.format(cik=cik)
        try:
            cf = pedir(url, contacto)
            filtrado, n = filtrar(cf)
            with open(os.path.join(DATA, t + '.json'), 'w', encoding='utf-8') as f:
                json.dump(filtrado, f, ensure_ascii=False, separators=(',', ':'))
            reg.update({'cik': cik, 'nombre': mapa[t]['title'], 'actualizado': ahora, 'hechos': n, 'fuente': url, 'error': '',
                        'ultimo_en_xbrl': ultimo_en_xbrl(filtrado)})
            time.sleep(PAUSA)
            try:
                reg['anuales_presentados'] = ultimos_anuales(pedir(URL_SUBM.format(cik=cik), contacto))
            except Exception as e:  # noqa: BLE001
                reg['anuales_presentados'] = 'error: %s' % e
            print(t, cik, n, 'hechos')
        except Exception as e:      # noqa: BLE001
            reg['error'] = '%s: %s (se conserva el archivo anterior)' % (ahora, e)
            errores += 1
            print(t, 'ERROR', e)
        time.sleep(PAUSA)
    idx['corrida'] = ahora
    with open(ruta_idx, 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    print('Listo:', len(tickers), 'tickers,', errores, 'errores')


if __name__ == '__main__':
    main()
