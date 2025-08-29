import json
import os
import datetime as dt
import sys
import requests

# config
PRED_ENTITY_ID = sys.argv[1]  # p.ej. sensor.co2_intensity_prophet_forecast_2

# mapea entidad de predicción -> archivo JSON
FILENAME_MAP = {
    "sensor.co2_intensity_persistence_forecast": "persistence_forecast_2025.json",
    "sensor.co2_intensity_prophet_forecast": "prophet_forecast_2025.json",
    "sensor.co2_intensity_autoarima_forecast": "autoarima_forecast_2025.json",
}
FILENAME = FILENAME_MAP.get(PRED_ENTITY_ID)
if not FILENAME:
    print(f"[ERROR] Entidad de predicción desconocida: {PRED_ENTITY_ID}")
    sys.exit(1)

LOG_PATH = f"/config/predicciones/{FILENAME}"

# entidad REAL a consultar en History API
REAL_ENTITY_ID = os.getenv("REAL_ENTITY_ID", "sensor.electricity_maps_co2_intensity_2")

# dónde vive tu HASS
BASE_URL = os.getenv("HASS_URL", "http://localhost:8123")

# token, remplazar TU_TOKEN por tu token de larga duración 
TOKEN = os.getenv("HASS_TOKEN", "TU_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# helpers
UTC = dt.timezone.utc

def parse_dt(s: str) -> dt.datetime | None:
    if not s:
        return None
    # aceptar 'Z' como +00:00
    s = s.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(s)
    except Exception:
        return None

def to_utc(d: dt.datetime) -> dt.datetime:
    if d.tzinfo is None:
        # asume que es UTC si viene naive
        return d.replace(tzinfo=UTC)
    return d.astimezone(UTC)

def get_real_values(start_utc: dt.datetime, end_utc: dt.datetime) -> dict:
    """Devuelve {timestamp_utc: valor_float} para la entidad REAL en el rango."""
    url = f"{BASE_URL}/api/history/period/{start_utc.isoformat()}"
    params = {
        "end_time": end_utc.isoformat(),
        "filter_entity_id": REAL_ENTITY_ID,
        "minimal_response": "true",
        "significant_changes_only": "false",
    }
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    except Exception as e:
        print(f"[ERROR] Llamando History API: {e}")
        return {}

    if resp.status_code != 200:
        print(f"[WARN] History API {resp.status_code}: {resp.text[:200]}")
        return {}

    payload = resp.json()
    if not payload or not payload[0]:
        print("[INFO] History vacío para el rango solicitado.")
        return {}

    real = {}
    for e in payload[0]:
        st = e.get("state")
        if st in ("unknown", "unavailable", None):
            continue
        ts = parse_dt(e.get("last_updated") or e.get("last_changed"))
        if not ts:
            continue
        ts = to_utc(ts)
        try:
            real[ts] = float(st)
        except Exception:
            continue

    print(f"[INFO] History: {len(real)} muestras reales.")
    return real

# validaciones básicas
if "TU_TOKEN" in TOKEN:
    print("[ERROR] Debes poner un Long-Lived Access Token en HASS_TOKEN (o SUPERVISOR_TOKEN si es add-on).")
    sys.exit(2)

if not os.path.exists(LOG_PATH):
    print(f"[INFO] No existe {LOG_PATH}. Nada que hacer.")
    sys.exit(0)

# cargar predicciones
try:
    with open(LOG_PATH, "r") as f:
        data = json.load(f)
except Exception as e:
    print(f"[WARN] No pude leer JSON ({e}).")
    data = []

if not data:
    print("[INFO] JSON vacío. Nada que procesar.")
    sys.exit(0)

now_utc = dt.datetime.now(UTC)
updated = False  # escribiremos el archivo si tocamos algo (incluyendo mape=None)

for entry in data:
    # si ya tiene MAPE numérico, lo dejamos
    if "mape" in entry and entry["mape"] is not None:
        continue

    forecast = entry.get("forecast")
    timestamps = entry.get("forecast_timestamps")
    if not forecast or not timestamps:
        continue

    # parsea tiempos de predicción a UTC
    ts_parsed = [to_utc(parse_dt(t)) for t in timestamps]
    if any(t is None for t in ts_parsed):
        print("[WARN] Timestamps de predicción con formato inválido. Saltando entrada.")
        entry["mape"] = None
        updated = True
        continue

    first_t, last_t = ts_parsed[0], ts_parsed[-1]

    # solo procesa cuando toda la ventana ya pasó
    if last_t > now_utc:
        continue

    # trae reales con un margen extra
    start_time = first_t
    end_time = last_t + dt.timedelta(minutes=30)

    real_values = get_real_values(start_time, end_time)
    if not real_values:
        entry["mape"] = None
        updated = True
        continue

    # empareja por vecino más cercano con tolerancia ±15 min
    tol = dt.timedelta(minutes=15)
    pairs = []
    for t_pred, y_pred in zip(ts_parsed, forecast):
        try:
            y_pred = float(y_pred)
        except Exception:
            continue
        closest_time = min(real_values.keys(), key=lambda rt: abs(rt - t_pred))
        if abs(closest_time - t_pred) <= tol:
            y_real = real_values[closest_time]
            pairs.append((y_real, y_pred))

    if pairs:
        # evita dividir por 0; cuenta solo los válidos también en el denominador
        valid = [(r, p) for (r, p) in pairs if r != 0]
        if not valid:
            entry["mape"] = None
            updated = True
        else:
            mape = sum(abs((r - p) / r) for r, p in valid) * 100.0 / len(valid)
            entry["mape"] = mape
            print(f"[INFO] MAPE calculado: {mape:.3f}% con {len(valid)}/{len(pairs)} pares válidos.")
            updated = True
    else:
        print("[INFO] Sin pares dentro de la tolerancia.")
        entry["mape"] = None
        updated = True

# guardar si hubo cambios
if updated:
    with open(LOG_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[OK] JSON actualizado en {LOG_PATH}")
else:
    print("[INFO] Nada que actualizar (aún no han pasado las ventanas, o ya estaba el MAPE).")