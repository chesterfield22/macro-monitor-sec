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
                      todavía no tiene datos XBRL en companyfacts. En ese caso los hechos se leen de la instancia XBRL de
                      la propia presentación (EDGAR Archives, archivo *_htm.xml) y se agregan con el mismo formato;
                      agregados_de_instancia lista el accn y el archivo usados.
Si un emisor falla, se conserva el archivo anterior y el error queda en index.json.
"""
import json
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
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


def pedir(url, contacto, intentos=3, crudo=False):
    req = urllib.request.Request(url, headers={'User-Agent': 'MacroMonitor-Montos ' + contacto, 'Accept-Encoding': 'identity'})
    for k in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                b = r.read()
                return b if crudo else json.loads(b.decode('utf-8'))
        except Exception as e:      # noqa: BLE001 — se reintenta y se informa
            ultimo = e
            time.sleep(2 * (k + 1))
    raise ultimo


TAX_NS = {'ifrs-full': 'xbrl.ifrs.org/taxonomy/', 'us-gaap': 'fasb.org/us-gaap/'}


def hechos_instancia(xml_bytes, accn, form, filed, fy):
    """Instancia XBRL (archivo *_htm.xml de la presentación) → {tax: {tag: {units: {MON: [hechos]}}}}.
    Solo contextos SIN dimensiones (cifras consolidadas totales), monedas USD/ARS y valores numéricos."""
    raiz = ET.fromstring(xml_bytes)
    ns_x = '{http://www.xbrl.org/2003/instance}'
    ctx = {}
    for c in raiz.iter(ns_x + 'context'):
        ent = c.find(ns_x + 'entity')
        if (ent is not None and ent.find(ns_x + 'segment') is not None) or c.find(ns_x + 'scenario') is not None:
            continue
        per = c.find(ns_x + 'period')
        if per is None:
            continue
        ini, fin, inst = per.find(ns_x + 'startDate'), per.find(ns_x + 'endDate'), per.find(ns_x + 'instant')
        if inst is not None:
            ctx[c.get('id')] = (None, inst.text.strip()[:10])
        elif ini is not None and fin is not None:
            ctx[c.get('id')] = (ini.text.strip()[:10], fin.text.strip()[:10])
    uni = {}
    for u in raiz.iter(ns_x + 'unit'):
        m = u.find(ns_x + 'measure')
        if m is not None and m.text:
            uni[u.get('id')] = m.text.strip().split(':')[-1].upper()
    out, vistos = {}, set()
    for el in raiz:
        if not isinstance(el.tag, str) or not el.tag.startswith('{'):
            continue
        ns, tag = el.tag[1:].split('}', 1)
        tax = next((t for t, marca in TAX_NS.items() if marca in ns), None)
        c, u = el.get('contextRef'), el.get('unitRef')
        if not tax or c not in ctx or uni.get(u) not in MONEDAS or el.text is None:
            continue
        try:
            val = float(el.text.strip())
        except ValueError:
            continue
        ini, fin = ctx[c]
        clave = (tax, tag, uni[u], ini, fin)
        if clave in vistos:
            continue
        vistos.add(clave)
        h = {'end': fin, 'val': int(val) if val == int(val) else val, 'accn': accn, 'fy': fy, 'fp': 'FY', 'form': form, 'filed': filed}
        if ini:
            h['start'] = ini
        out.setdefault(tax, {}).setdefault(tag, {'units': {}})['units'].setdefault(uni[u], []).append(h)
    return out


def completar_con_instancias(filtrado, anuales, cik, contacto):
    """Si un 20-F presentado (con XBRL) todavía no aparece en companyfacts, se leen sus hechos de la instancia XBRL
    de la propia presentación (EDGAR Archives) y se agregan con el mismo formato. Devuelve la lista de accn agregados."""
    presentes = set()
    for tags in filtrado['facts'].values():
        for d in tags.values():
            for lista in d['units'].values():
                for x in lista:
                    presentes.add(x.get('accn'))
    agregados = []
    for a in anuales if isinstance(anuales, list) else []:
        if a['accn'] in presentes or not (a.get('xbrl') or a.get('ixbrl')) or str(a.get('periodo', ''))[:4] < str(ANIO_MIN):
            continue
        carpeta = 'https://www.sec.gov/Archives/edgar/data/%d/%s/' % (int(cik), a['accn'].replace('-', ''))
        items = pedir(carpeta + 'index.json', contacto)['directory']['item']
        nombres = [i['name'] for i in items]
        inst = [n for n in nombres if n.endswith('_htm.xml')] or \
               [n for n in nombres if n.endswith('.xml') and not n.startswith(('FilingSummary', 'R')) and not n.endswith(('_cal.xml', '_def.xml', '_lab.xml', '_pre.xml'))]
        if not inst:
            continue
        time.sleep(PAUSA)
        nuevos = hechos_instancia(pedir(carpeta + inst[0], contacto, crudo=True), a['accn'], a['form'], a['presentado'], int(str(a['periodo'])[:4]))
        for tax, tags in nuevos.items():
            for tag, d in tags.items():
                for mon, lista in d['units'].items():
                    filtrado['facts'].setdefault(tax, {}).setdefault(tag, {'units': {}})['units'].setdefault(mon, []).extend(lista)
        agregados.append({'accn': a['accn'], 'archivo': carpeta + inst[0]})
        time.sleep(PAUSA)
    return agregados


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
            reg.update({'cik': cik, 'nombre': mapa[t]['title'], 'actualizado': ahora, 'hechos': n, 'fuente': url, 'error': '',
                        'ultimo_en_xbrl': ultimo_en_xbrl(filtrado)})
            time.sleep(PAUSA)
            try:
                reg['anuales_presentados'] = ultimos_anuales(pedir(URL_SUBM.format(cik=cik), contacto))
                time.sleep(PAUSA)
                reg['agregados_de_instancia'] = completar_con_instancias(filtrado, reg['anuales_presentados'], cik, contacto)
            except Exception as e:  # noqa: BLE001
                reg['error_instancias'] = '%s' % e
            with open(os.path.join(DATA, t + '.json'), 'w', encoding='utf-8') as f:
                json.dump(filtrado, f, ensure_ascii=False, separators=(',', ':'))
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
