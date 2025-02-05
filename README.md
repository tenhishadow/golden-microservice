# golden-microservice

## purpose

Needed to write simple code that would serve http requests, good for
docker/kubernetes for testing purposes.
Namely it is just a convenient container that runs and listens to
traffic-port and status-port as well as outputting variable values
for service tasks

## Defaults

Traffic port 8080
Status port 8081

Configurable via APP_PORT_TRAFFIC APP_PORT_STATUS env vars

## Example run

```bash
ENV=prod CLUSTER=eu-lalala-west VARS_LIST="ENV,CLUSTER" python main.py
Main server running on port 8080...
Health server running on port 8081...
```

Check on traffic port:
```bash
curl 127.0.0.1:8080/
golden-microservice
Listen on port 8080
ENV to show:
ENV is prod
CLUSTER is eu-lalala-west
```

Check on status port:
```bash
curl 127.0.0.1:8081/status
OK
```
