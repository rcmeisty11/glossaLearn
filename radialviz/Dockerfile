FROM python:3.10.7-alpine3.16

WORKDIR /app

RUN apk add --update \
    build-base libffi-dev openssl-dev ffmpeg \
    xmlsec xmlsec-dev libpq-dev \
  && rm -rf /var/cache/apk/*

ADD requirements.txt /tmp
RUN pip install --upgrade pip
RUN pip install -r /tmp/requirements.txt
# feels hacky

ENV DB_PATH=/data/greek_vocab.db

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--log-level", "info", "--workers", "2", "--timeout", "120", "--graceful-timeout", "3", "serve_api:app"]