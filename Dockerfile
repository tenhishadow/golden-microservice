FROM python:3-alpine

ENV APP_PORT_TRAFFIC=8080
ENV APP_PORT_STATUS=8081

RUN addgroup --system app \
 && adduser --system --ingroup app app

USER app
WORKDIR /app
COPY --chown=app:app main.py main.py

EXPOSE ${APP_PORT_TRAFFIC} ${APP_PORT_STATUS}
CMD ["python3", "main.py"]
