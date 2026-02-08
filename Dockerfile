FROM python:3-alpine

ENV APP_PORT_TRAFFIC="8080" \
    APP_PORT_STATUS="8081" \
    PYTHONDONTWRITEBYTECODE="1" \
    PYTHONUNBUFFERED="1"

ARG APP_USER="app" \
    APP_GROUP="app" \
    APP_GROUP_ID="10001" \
    APP_USER_ID="10001" \
    APP_DATA="/app"

RUN addgroup -S -g ${APP_GROUP_ID} ${APP_GROUP} \
 && adduser  -S -D -H -u ${APP_USER_ID} -G ${APP_GROUP} -s /sbin/nologin ${APP_USER}

USER ${APP_USER}
WORKDIR ${APP_DATA}
COPY --chown=${APP_USER}:${APP_GROUP} main.py main.py
COPY --chown=${APP_USER}:${APP_GROUP} health.py /usr/local/bin/health.py

EXPOSE ${APP_PORT_TRAFFIC} ${APP_PORT_STATUS}

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python3 /usr/local/bin/health.py

CMD ["python3", "-S", "-OO", "main.py"]
