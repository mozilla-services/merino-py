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
docker build -t cloudflare/ohttp:local path/to/ohttp
```

Start the tunnel (for Ingress to work on localhost):
Leave this running in a separate terminal.
```bash
minikube tunnel
```

Deploy the stack:
```bash
kubectl apply -k k8s/overlays/development/
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
curl -s "http://localhost/api/v2/ohttp-keys" | xxd -p | tr -d '\n ' > config.hex
set CONFIG (cat config.hex)
```

### Create request.txt
```bash
echo -e "GET /api/v2/suggest?q=weather&country=US&region=CA&city=San%20Francisco HTTP/1.1\r\nHost: localhost\r\nUser-Agent: ohttp-test-client\r\nAccept: application/json\r\n\r\n" > request.txt
```

### Request

```bash
./target/debug/ohttp-client \
    "http://localhost/api/v2/gateway" \
    "$CONFIG" \
    -i request.txt
```


# Overview

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                   OHTTP CLIENT                                      │
│                                                                                     │
│  1. GET /api/v2/ohttp-keys  →  Gets OHTTP config                                    │
│  2. Encrypts HTTP request:                                                          │
│     GET /api/v2/suggest?q=weather&country=US&region=CA&city=SF                      │
│  3. POST /api/v2/gateway + encrypted payload                                        │
│  4. Receives encrypted response, decrypts it                                        │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              MINIKUBE TUNNEL (127.0.0.1:80)                         │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                NGINX INGRESS CONTROLLER                             │
│                                                                                     │
│  Routes based on path:                                                              │
│  • /api/v1/*           →  merino-service:8000 (direct to Merino)                    │
│  • /api/v2/gateway     →  merino-service:8080 (OHTTP Gateway)                       │
│  • /api/v2/ohttp-keys  →  merino-service:8080 (OHTTP Gateway)                       │
│                                                                                     │
│  Note: /api/v2/suggest is NOT directly exposed - only via gateway                   │
└─────────────────────────────────────────────────────────────────────────────────────┘
                        │                                    │
            /api/v1/*   │                                    │ /api/v2/gateway
                        │                                    │ /api/v2/ohttp-keys
                        ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            KUBERNETES SERVICE: merino-service                       │
│                                                                                     │
│  Port 8000: Direct to Merino container                                              │
│  Port 8080: Direct to OHTTP Gateway container                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
                        │                                    │
                        ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                               POD: merino-deployment                                │
│                                                                                     │
│  ┌─────────────────────────────┐    ┌─────────────────────────────────────────┐     │
│  │     CONTAINER: merino       │    │      CONTAINER: ohttp-gateway           │     │
│  │                             │    │                                         │     │
│  │  • Python FastAPI app       │    │  • Cloudflare Privacy Gateway           │     │
│  │  • Port 8000                │    │  • Port 8080                            │     │
│  │  • Handles /api/v1/*        │    │  • Provides /ohttp-keys                 │     │
│  │  • Handles /api/v2/*        │    │  • Handles /gateway                     │     │
│  │    (when called internally) │    │  • Decrypts OHTTP requests              │     │
│  │                             │    │  • Forwards to localhost:8000           │     │
│  └─────────────────────────────┘    └─────────────────────────────────────────┘     │
│                   ▲                                         │                       │
│                   │                                         │                       │
│                   └─────────────────────────────────────────┘                       │
│                        Internal HTTP call for /api/v2/suggest                       │
└─────────────────────────────────────────────────────────────────────────────────────┘

### FLOW FOR OHTTP REQUEST:
1. Client → /api/v2/ohttp-keys → Ingress → Gateway container → Returns OHTTP config
2. Client encrypts: GET /api/v2/suggest?q=weather&country=US&region=CA&city=SF
3. Client → /api/v2/gateway + encrypted payload → Ingress → Gateway container
4. Gateway decrypts → Makes internal HTTP call to localhost:8000/api/v2/suggest
5. Merino container processes request → Returns response to Gateway
6. Gateway encrypts response → Returns to client via Ingress
7. Client decrypts response

### FLOW FOR DIRECT V1 REQUEST:
1. Client → /api/v1/curated-recommendations → Ingress → Merino container directly

#### KEY POINTS:
• V1 API is directly accessible (no OHTTP protection)
• V2 API endpoints (except gateway/ohttp-keys) are only accessible via OHTTP gateway
• Both containers run in the same pod, so gateway can reach merino via localhost
• Ingress routes different paths to different container ports
