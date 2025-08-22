FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY predictor_script.py .
COPY run.sh .

RUN chmod +x run.sh

CMD ["./run.sh"]
