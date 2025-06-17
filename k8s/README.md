## Setup Summary
- Kubernetes (Minikube) local cluster with:
  * Merino service (port 8000)
  * OHTTP privacy gateway (Cloudflare) as a sidecar (port 8080)
- Ingress routes:
  * /api/v1/* → Merino directly
  * /api/v2/* → OHTTP gateway (requires OHTTP encapsulation)
- All access is via Ingress on port 80

## How to Start
Start Minikube:
```bash
minikube start
```

Enable Ingress:
```bash
minikube addons enable ingress
```

Build Docker images for Merino and OHTTP locally:
Use the Minikube Docker daemon so images are available to the cluster:
```bash
eval $(minikube docker-env)
```

Then build your images:
```bash
docker build -t merino:local .
docker build -t fastly-mock:local k8s/mock-fastly
```

For the gateway, we assume to either use the Cloudflare Go gateway, or the self-implemented Rust one:
```bash
git clone https://github.com/cloudflare/privacy-gateway-server-go
docker build -t cloudflare/ohttp:local path/to/cloudflare-go-gateway
```

or:

```bash
git clone https://github.com/gruberb/ohttp
cd ohttp
git fetch --all
git checkout gateway
docker build -t rust-ohttp-gateway:local -f Dockerfile.ohttp .
```

Start the tunnel (for Ingress to work on localhost):
Leave this running in a separate terminal.
```bash
minikube tunnel
```

Deploy the Cloudflare gateway stack:
```bash
kubectl apply -k k8s/overlays/development/
```

Or deploy the Rust gateway stack
```bash
kubectl apply -k k8s/overlays/rust-ohttp/
```

Check pod and service status:
```bash
kubectl get pods
kubectl get svc
kubectl get ingress
```

> Important: Wait about 1 minute until everything is up and running.

Example curl (v1 endpoint)
```bash
curl -X POST http://127.0.0.1/api/v1/curated-recommendations \
  -H "Content-Type: application/json" \
  -d '{"locale": "en-US", "count": 1}'
  ```

## Test OHTTPs

### Cloning and building this OHTTP client:
```
>  git clone git@github.com:martinthomson/ohttp.git
>  cd ohttp
>  cargo build --bin ohttp-client --features rust-hpke
```

### Get Keys

```bash
curl -s "http://localhost/fastly/ohttp-keys" | xxd -p | tr -d '\n ' > config.hex
set CONFIG (cat config.hex)
```

### Create request.txt
```bash
echo -e "POST /api/v2/curated-recommendations HTTP/1.1\r\nHost: localhost\r\nUser-Agent: ohttp-test-client\r\nAccept: application/json\r\nContent-Type: application/json\r\n\r\n{\"locale\": \"en-US\", \"count\": 1}" > request.txt
```

### Request

```bash
./target/debug/ohttp-client \
    "http://localhost/fastly/gateway" \
    "$CONFIG" \
    -i request.txt
```

# Overview

We just use a mock fastly instance. A simple NGINX server, which adds a 10ms delay and forwards the requests to the OHTTP (Cloudflare) sidecar:

```bash
> time curl -s "http://localhost/api/v2/ohttp-keys" > /dev/null

________________________________________________________
Executed in   29.88 millis    fish           external
   usr time    7.15 millis    0.30 millis    6.85 millis
   sys time   11.05 millis    2.23 millis    8.82 millis

> time curl -s "http://localhost/fastly/ohttp-keys" > /dev/null

________________________________________________________
Executed in   38.49 millis    fish           external
   usr time    7.43 millis    0.22 millis    7.21 millis
   sys time    9.70 millis    1.32 millis    8.38 millis
```


### FLOW FOR OHTTP REQUEST:
1. Client → /api/v2/ohttp-keys → Ingress → Fastly mock → Returns OHTTP config
2. Client encrypts: GET /api/v2/suggest?q=weather&country=US&region=CA&city=SF
3. Client → /fastly/gateway + encrypted payload → Fastly Mock → Ingress → Gateway container
4. Gateway decrypts → Makes internal HTTP call to localhost:8000/api/v2/suggest
5. Merino container processes request → Returns response to Gateway
6. Gateway encrypts response → Returns to Fastly Mock
7. Fastly returns the response via Ingress
8. Client decrypts response

### FLOW FOR DIRECT V1 REQUEST:
1. Client → /api/v1/curated-recommendations → Ingress → Merino container directly

#### KEY POINTS:
• V1 API is directly accessible (no OHTTP protection)
• V2 API endpoints (except gateway/ohttp-keys) are only accessible via Fastly and OHTTP gateway
• Both containers run in the same pod, so gateway can reach merino via localhost
• Ingress routes different paths to different container ports
