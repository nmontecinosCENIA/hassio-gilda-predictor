import json
import os
import datetime
import sys
import requests

entity_id = sys.argv[1]

filename_map = {
    "sensor.co2_intensity_persistence_forecast": "persistence_forecast_2025.json",
    "sensor.co2_intensity_prophet_forecast": "prophet_forecast_2025.json",
    "sensor.co2_intensity_autoarima_forecast": "autoarima_forecast_2025.json",
}

filename = filename_map.get(entity_id)
if not filename:
    sys.exit(1)

log_path = f"/config/predicciones/{filename}"

#TOKEN DE AUTENTICACIÓN
headers = {
    "Authorization": "Bearer TU_TOKEN_HASS",
    "Content-Type": "application/json",
}

# Leer archivo con predicciones
if not os.path.exists(log_path):
    sys.exit(0)

with open(log_path, "r") as f:
    try:
        data = json.load(f)
    except:
        data = []

if not data:
    sys.exit(0)

# Obtener tiempo actual
now = datetime.datetime.now()

# Función para obtener valor real del historial en un rango cercano al timestamp dado
def get_real_values(start_time, end_time):
    url = f"http://localhost:8123/api/history/period/{start_time.isoformat()}?end_time={end_time.isoformat()}&filter_entity_id=sensor.electricity_maps_co2_intensity_2"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return {}
    hist_data = resp.json()
    if not hist_data or not hist_data[0]:
        return {}
    real_vals = {}
    for entry in hist_data[0]:
        if entry["state"] in ("unknown", "unavailable"):
            continue
        try:
            dt = datetime.datetime.fromisoformat(entry["last_updated"])
            real_vals[dt] = float(entry["state"])
        except:
            continue
    return real_vals

updated = False

for entry in data:
    # Si ya calculamos MAPE, saltamos (o podemos recalcular si quieres)
    if "mape" in entry and entry["mape"] is not None:
        continue

    forecast = entry.get("forecast")
    timestamps = entry.get("forecast_timestamps")
    if not forecast or not timestamps:
        continue

    # Solo procesamos predicciones que ya pasaron (último timestamp < ahora)
    last_forecast_time = datetime.datetime.fromisoformat(timestamps[-1])
    if last_forecast_time > now:
        continue  # Todavía no pasó el período predicho

    # Obtener rango de tiempo para buscar datos reales: desde primer timestamp hasta el último de la predicción
    start_time = datetime.datetime.fromisoformat(timestamps[0])
    end_time = last_forecast_time + datetime.timedelta(minutes=30)  # un poco más para asegurar

    real_values = get_real_values(start_time, end_time)
    if not real_values:
        continue

    # Emparejar valores reales y predichos
    pairs = []
    for t, y_pred in zip(timestamps, forecast):
        try:
            ft = datetime.datetime.fromisoformat(t)
            # Buscar valor real más cercano dentro de ±15 minutos
            closest_time = min(real_values.keys(), key=lambda rt: abs(rt - ft))
            if abs((closest_time - ft).total_seconds()) <= 900:  # 15 minutos
                y_real = real_values[closest_time]
                pairs.append((y_real, y_pred))
        except Exception:
            continue

    if pairs:
        mape = sum(abs((r - p) / r) for r, p in pairs if r != 0) * 100 / len(pairs)
        entry["mape"] = mape
        updated = True
    else:
        entry["mape"] = None

if updated:
    with open(log_path, "w") as f:
        json.dump(data, f, indent=2)