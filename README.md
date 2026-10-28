# macro-monitor-sec

Copia semanal, filtrada y sin transformar, de los estados financieros anuales (20-F, XBRL) que presentan a la SEC los
emisores de `sec/tickers.txt`. La lee el módulo de crédito de la planilla Montos (Apps Script), que no puede consultar a
la SEC directamente (la SEC rechaza las consultas que salen de los servidores compartidos de Google).

- Fuente: API oficial de la SEC (`data.sec.gov/api/xbrl/companyfacts`). Cada hecho conserva `accn` (número de
  presentación) y `filed` (fecha), para rastrear el dato hasta el formulario original.
- Filtro: formularios anuales (20-F, 20-F/A, 40-F, 10-K, 10-K/A), monedas USD y ARS, cierres desde 2017.
- Corre los lunes (y a mano desde Actions › "Datos SEC (20-F) para Montos" › Run workflow).
- Secreto requerido: `SEC_CONTACTO` (contacto para el User-Agent que exige la SEC).
