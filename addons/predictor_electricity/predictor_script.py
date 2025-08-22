from flask import Flask, request, jsonify
import pandas as pd
import numpy as np
from prophet import Prophet
from statsforecast import StatsForecast
from statsforecast.models import AutoARIMA, MSTL
import logging
from datetime import datetime
import pytz

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

def baseline_forecasts(data, periods):
    """Generar predicciones base para una serie temporal."""
    try:
        baseline_forecasts = {}
        baseline_forecasts['persistence'] = data['y'].values[-periods:]
        baseline_forecasts['mean'] = data['y'].mean() * np.ones(periods)
        baseline_forecasts['median'] = data['y'].median() * np.ones(periods)
        return baseline_forecasts
    except Exception as e:
        _LOGGER.error("Error en baseline_forecasts: %s", e)
        raise

def prophet_forecast(data, periods, freq='h'):
    """Generar predicción con Prophet."""
    try:

        
        # Configura la zona horaria local (por ejemplo, America/Santiago para Chile)
        local_tz = pytz.timezone('America/Santiago')  # Cambia según tu zona horaria        
        # Asegúrate de que los datos de entrada tengan la zona horaria correcta
        data_prophet = data.rename(columns={'ds': 'ds', 'y': 'y'}).copy()
        data_prophet['ds'] = data_prophet['ds'].dt.tz_localize(local_tz)


        prophet_model = Prophet(daily_seasonality=True, weekly_seasonality=True, n_changepoints=60)
        prophet_model.add_country_holidays(country_name="Chile")
        prophet_model.fit(data_prophet)
        
        future_prophet = prophet_model.make_future_dataframe(periods=periods, freq=freq)
        
        # Localiza las fechas generadas en la zona horaria correcta
        future_prophet['ds'] = future_prophet['ds'].dt.tz_localize(local_tz)        
        
        forecast_prophet = prophet_model.predict(future_prophet)
        forecast = forecast_prophet['yhat'][-periods:].reset_index(drop=True).clip(lower=0)
        lower_ci = forecast_prophet['yhat_lower'][-periods:].reset_index(drop=True).clip(lower=0)
        upper_ci = forecast_prophet['yhat_upper'][-periods:].reset_index(drop=True).clip(lower=0)
        
        forecast_dates = forecast_prophet['ds'][-periods:].dt.strftime('%Y-%m-%d %H:%M:%S').tolist()
        return forecast.tolist(), lower_ci.tolist(), upper_ci.tolist(), forecast_dates
    except Exception as e:
        _LOGGER.error("Error en prophet_forecast: %s", e)
        raise

def autoarima_forecast(data, periods, freq='h'):
    """Generar predicción con AutoARIMA."""
    try:
        data_arima = data[['ds', 'y']].copy()
        data_arima['unique_id'] = 'series_1'
        models = [MSTL(
            season_length=[24, 24 * 7],
            trend_forecaster=AutoARIMA(nmodels=96)
        )]
        model = StatsForecast(models=models, freq=freq)
        model.fit(data_arima)
        forecast_arima = model.predict(periods, level=[95])
        forecast = forecast_arima['MSTL'].clip(lower=0)
        lower_ci = forecast_arima['MSTL-lo-95'].clip(lower=0)
        upper_ci = forecast_arima['MSTL-hi-95'].clip(lower=0)
        return forecast.tolist(), lower_ci.tolist(), upper_ci.tolist()
    except Exception as e:
        _LOGGER.error("Error en autoarima_forecast: %s", e)
        raise

@app.route('/predict', methods=['POST'])
def predict():
    """Endpoint para recibir datos y devolver predicciones."""
    try:
        input_data = request.json
        periods = input_data['periods']
        freq = input_data.get('freq', 'h')
        data = pd.DataFrame(input_data['data'])

        # Convertir las fechas de entrada a un formato con zona horaria
        local_tz = pytz.timezone('America/Santiago')  # Cambia según tu zona horaria
        data['ds'] = pd.to_datetime(data['ds']).dt.tz_convert(local_tz)


        data['y'] = data['y'].astype(float)

        baseline = baseline_forecasts(data, periods)
        prophet_fc, prophet_lower, prophet_upper, forecast_dates = prophet_forecast(data, periods, freq)
        arima_fc, arima_lower, arima_upper = autoarima_forecast(data, periods, freq)

        result = {
            'dates': forecast_dates,
            'persistence': baseline['persistence'].tolist(),
            'mean': baseline['mean'].tolist(),
            'median': baseline['median'].tolist(),
            'prophet': prophet_fc,
            'prophet_lower': prophet_lower,
            'prophet_upper': prophet_upper,
            'arima': arima_fc,
            'arima_lower': arima_lower,
            'arima_upper': arima_upper
        }
        return jsonify(result)
    except Exception as e:
        _LOGGER.error("Error en predict: %s", e)
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)