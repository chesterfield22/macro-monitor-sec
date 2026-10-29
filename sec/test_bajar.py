"""Pruebas del filtro (sin conexión)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bajar import filtrar, hechos_instancia  # noqa: E402

cf = {'cik': 904851, 'entityName': 'YPF', 'facts': {
    'ifrs-full': {
        'Borrowings': {'units': {'USD': [
            {'end': '2025-12-31', 'val': 10581000000, 'form': '20-F', 'accn': 'A', 'fy': 2025, 'filed': '2026-03-26'},
            {'end': '2025-06-30', 'val': 1, 'form': '6-K', 'accn': 'B', 'fy': 2025, 'filed': '2025-08-01'},
            {'end': '2012-12-31', 'val': 2, 'form': '20-F', 'accn': 'C', 'fy': 2012, 'filed': '2013-04-01'}],
            'EUR': [{'end': '2025-12-31', 'val': 3, 'form': '20-F', 'accn': 'A', 'fy': 2025, 'filed': '2026-03-26'}]}},
        'SoloTrimestral': {'units': {'USD': [{'end': '2025-06-30', 'val': 1, 'form': '6-K', 'accn': 'B', 'fy': 2025, 'filed': '2025-08-01'}]}}},
    'otra': {'X': {'units': {'USD': [{'end': '2025-12-31', 'val': 1, 'form': '20-F'}]}}}}}
out, n = filtrar(cf)
fallas = []
if n != 1:
    fallas.append('cantidad de hechos: %s' % n)
if list(out['facts'].keys()) != ['ifrs-full'] or list(out['facts']['ifrs-full'].keys()) != ['Borrowings']:
    fallas.append('taxonomías/etiquetas: %s' % out['facts'])
if out['facts']['ifrs-full']['Borrowings']['units']['USD'][0]['val'] != 10581000000:
    fallas.append('valor alterado')
xml = b'''<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:ifrs-full="https://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full"
 xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:iso4217="http://www.xbrl.org/2003/iso4217">
 <context id="c1"><entity><identifier scheme="x">1</identifier></entity><period><instant>2025-12-31</instant></period></context>
 <context id="c2"><entity><identifier scheme="x">1</identifier></entity><period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period></context>
 <context id="c3"><entity><identifier scheme="x">1</identifier><segment><xbrldi:explicitMember dimension="a">b</xbrldi:explicitMember></segment></entity><period><instant>2025-12-31</instant></period></context>
 <unit id="usd"><measure>iso4217:USD</measure></unit><unit id="ars"><measure>iso4217:ARS</measure></unit>
 <ifrs-full:Borrowings contextRef="c1" unitRef="usd" decimals="-6">2079000000</ifrs-full:Borrowings>
 <ifrs-full:Borrowings contextRef="c3" unitRef="usd" decimals="-6">1</ifrs-full:Borrowings>
 <ifrs-full:Revenue contextRef="c2" unitRef="usd" decimals="-6">1876000000</ifrs-full:Revenue>
 <ifrs-full:Revenue contextRef="c2" unitRef="usd" decimals="-6">1876000000</ifrs-full:Revenue>
</xbrl>'''
hi = hechos_instancia(xml, '0001-26-1', '20-F', '2026-04-09', 2025)
b = hi.get('ifrs-full', {}).get('Borrowings', {}).get('units', {}).get('USD', [])
rv = hi.get('ifrs-full', {}).get('Revenue', {}).get('units', {}).get('USD', [])
if len(b) != 1 or b[0]['val'] != 2079000000 or 'start' in b[0]:
    fallas.append('instancia: saldo sin dimensiones %s' % b)
if len(rv) != 1 or rv[0]['start'] != '2025-01-01' or rv[0]['accn'] != '0001-26-1':
    fallas.append('instancia: flujo y duplicados %s' % rv)
print('Pruebas del filtro:', 'OK' if not fallas else 'FALLAS ' + '; '.join(fallas))
sys.exit(1 if fallas else 0)
