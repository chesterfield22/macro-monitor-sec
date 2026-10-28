"""Pruebas del filtro (sin conexión)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bajar import filtrar  # noqa: E402

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
print('Pruebas del filtro:', 'OK' if not fallas else 'FALLAS ' + '; '.join(fallas))
sys.exit(1 if fallas else 0)
