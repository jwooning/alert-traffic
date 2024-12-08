FROM python:3-alpine

WORKDIR /app

ENV PYTHONUNBUFFERED=1

VOLUME /maildir
VOLUME /logs

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alert.py ./

CMD ["./alert.py"]

