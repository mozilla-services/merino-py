# Google Cloud Platform (GCP) Deployment Guide

This guide covers setting up, deploying, and managing the Merino OHTTP service on Google Kubernetes Engine (GKE).

## Table of Contents
- [Prerequisites](#prerequisites)
- [Initial Setup](#initial-setup)
- [First-Time Deployment](#first-time-deployment)
- [Re-deployment & Updates](#re-deployment--updates)
- [Monitoring & Debugging](#monitoring--debugging)
- [Cleanup](#cleanup)

## Architecture Overview

The GKE deployment simulates the production OHTTP flow:

```
Client → Fastly Mock (NGINX) → OHTTP Gateway (Cloudflare) → Merino API
```

### Components:

1. **Fastly Mock**: NGINX-based service that simulates Fastly's OHTTP relay behavior
2. **OHTTP Gateway**: Cloudflare's privacy gateway (sidecar container)
3. **Merino API**: Main application serving suggestions

### Traffic Flow:

1. **Client** makes encrypted OHTTP request
2. **Fastly Mock** receives request and forwards to OHTTP Gateway
3. **OHTTP Gateway** decrypts request and forwards to Merino
4. **Merino** processes request and returns response
5. **OHTTP Gateway** encrypts response
6. **Fastly Mock** forwards encrypted response back to client

This setup allows testing the complete production-like OHTTP flow in a controlled environment.

## Prerequisites

### Required Tools
- `gcloud` CLI (Google Cloud SDK)
- `kubectl`
- `docker`
- Access to the GCP project: `sandbox-merino-ohttp`

### Install Required Tools (if not already installed)

**macOS (using Homebrew):**
```bash
# Install Google Cloud SDK
brew install google-cloud-sdk

# Install kubectl (if not included with gcloud)
brew install kubectl

# Install docker
brew install docker
```

**Other platforms:** Follow the [official Google Cloud SDK installation guide](https://cloud.google.com/sdk/docs/install).

## Initial Setup

### 1. Authentication & Project Setup

```bash
# Login to Google Cloud
gcloud auth login

# Set your project
gcloud config set project sandbox-merino-ohttp

# Verify your configuration
gcloud config list

# Configure Docker to use gcloud as a credential helper
gcloud auth configure-docker gcr.io
```

### 2. Get Cluster Credentials

```bash
# Get GKE cluster credentials (replace with actual cluster name and zone)
gcloud container clusters get-credentials merino-cluster --zone us-central1-a

# Verify cluster connection
kubectl cluster-info
kubectl get nodes
```

### 3. Verify Current Deployment

```bash
# Check current deployments
kubectl get deployments
kubectl get services
kubectl get ingress

# Check pod status
kubectl get pods -o wide
```

## First-Time Deployment

### 1. Build and Push Images

From the project root directory:

```bash
# Set environment variables
export PROJECT_ID=sandbox-merino-ohttp
export IMAGE_TAG=v$(date +%Y%m%d-%H%M%S)  # Creates timestamp-based tag

# Build Merino image
docker build -t gcr.io/$PROJECT_ID/merino:$IMAGE_TAG .
docker build -t gcr.io/$PROJECT_ID/merino:latest .

# Build OHTTP Gateway image (assuming you have the Dockerfile)
docker build -t gcr.io/$PROJECT_ID/ohttp-gateway:$IMAGE_TAG -f Dockerfile.ohttp .
docker build -t gcr.io/$PROJECT_ID/ohttp-gateway:latest .

# Build Fastly Mock image (NGINX-based relay simulator)
docker build -t gcr.io/$PROJECT_ID/fastly-mock:$IMAGE_TAG -f Dockerfile.fastly .
docker build -t gcr.io/$PROJECT_ID/fastly-mock:latest .

# Push images to Google Container Registry
docker push gcr.io/$PROJECT_ID/merino:$IMAGE_TAG
docker push gcr.io/$PROJECT_ID/merino:latest
docker push gcr.io/$PROJECT_ID/ohttp-gateway:$IMAGE_TAG
docker push gcr.io/$PROJECT_ID/ohttp-gateway:latest
docker push gcr.io/$PROJECT_ID/fastly-mock:$IMAGE_TAG
docker push gcr.io/$PROJECT_ID/fastly-mock:latest
```

### Deploy to GKE

```bash
# Navigate to the k8s directory
cd k8s/overlays/gke

# Apply the configuration
kubectl apply -k .

# Watch the deployment progress
kubectl rollout status deployment/merino-deployment
kubectl rollout status deployment/fastly-mock-deployment

# Check pod status
kubectl get pods -l app=merino
kubectl get pods -l app=fastly-mock
```

### Verify Deployment

```bash
# Get external IP of the load balancer
kubectl get services
kubectl get ingress
```

### Test the endpoints

# Get the external IP
```bash
export EXTERNAL_IP=$(kubectl get ingress merino-ingress-v1 -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
```

# Test V1 API (direct)
```bash
curl -f "http://$EXTERNAL_IP/api/v1/curated-recommendations" \
  -H "Content-Type: application/json" \
  -d '{"locale": "en-US", "count": 1}' || echo "V1 API test failed"
```

## Test OHTTPs

### Cloning and building this OHTTP client:
```bash
>  git clone git@github.com:martinthomson/ohttp.git
>  cd ohttp
>  cargo build --bin ohttp-client --features rust-hpke
```
### Get external IP
```bash
export EXTERNAL_IP=$(kubectl get ingress merino-ingress-v1 -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
```

### Get keys

```bash
curl -s "http://$EXTERNAL_IP/fastly/ohttp-keys" | xxd -p | tr -d '\n ' > config.hex
set CONFIG (cat config.hex)
```

### Create request.txt
```bash
echo -e "POST /api/v2/curated-recommendations HTTP/1.1\r\nHost: localhost\r\nUser-Agent: ohttp-test-client\r\nAccept: application/json\r\nContent-Type: application/json\r\n\r\n{\"locale\": \"en-US\", \"count\": 1}" > request.txt
```

### Request

```bash
./target/debug/ohttp-client \
    "http://$EXTERNAL_IP/fastly/gateway" \
    "$CONFIG" \
    -i request.txt
```

### Expected response
```bash
Request: 80002000010001ea0b3bf461f...
Response: 28474c06b550349eb85c7b...
HTTP/1.1 200 Reason
Content-Length: 870
content-length: 870
content-type: application/json
x-request-id: ebe562467443463fab0be0f78193215e
date: Fri, 27 Jun 2025 12:20:29 GMT
server: uvicorn

{"recommendedAt":1751026830057,"surfaceId":"NEW_TAB_EN_US","data":[{"corpusItemId":"aba82a9e-11dd-4b2e-a23b-a27673cdeb75","scheduledCorpusItemId":"ca88f4ee-280a-4ab1-875c-32a268ef796d","url":"https://getpocket.com/explore/item/fake-it-till-you-make-it-good-advice-or-a-setup-for-failure?utm_source=firefox-newtab-en-us","title":"Is ‘Fake It Till You Make It’ Good Advice or a Setup for Failure?","excerpt":"Imitating confidence, competency, and drive may work for some, but what are the long-term professional implications?","topic":"career","publisher":"Shondaland","isTimeSensitive":false,"imageUrl":"https://s3.us-east-1.amazonaws.com/pocket-curatedcorpusapi-prod-images/cde150b2-4622-4f8f-b6a6-99ea725e37b8.jpeg","iconUrl":null,"tileId":8848411409814941,"receivedRank":0,"features":{"t_career":1.0}}],"feeds":null,"interestPicker":null,"inferredLocalModel":null}
```


### Update Deployment Configuration

Edit the image tags in `k8s/overlays/gke/gke-patches.yaml`:

```bash
# Edit the patches file to use your new image tags
vim k8s/overlays/gke/gke-patches.yaml
```

Update the image references:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: merino-deployment
spec:
  template:
    spec:
      containers:
        - name: merino
          image: gcr.io/sandbox-merino-ohttp/merino:latest  # or specific tag
          imagePullPolicy: Always
        - name: ohttp-gateway
          image: gcr.io/sandbox-merino-ohttp/ohttp-gateway:latest  # or specific tag
          imagePullPolicy: Always
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastly-mock-deployment
spec:
  template:
    spec:
      containers:
        - name: fastly-mock
          image: gcr.io/sandbox-merino-ohttp/fastly-mock:latest  # or specific tag
          imagePullPolicy: Always
```


## Re-deployment & Updates

### Quick Update (same configuration, new code)

```bash
# 1. Build and push new images
export IMAGE_TAG=v$(date +%Y%m%d-%H%M%S)
docker build -t gcr.io/sandbox-merino-ohttp/merino:$IMAGE_TAG .
docker push gcr.io/sandbox-merino-ohttp/merino:$IMAGE_TAG

# 2. Update the deployment with new image
kubectl set image deployment/merino-deployment \
  merino=gcr.io/sandbox-merino-ohttp/merino:$IMAGE_TAG \
  ohttp-gateway=gcr.io/sandbox-merino-ohttp/ohttp-gateway:$IMAGE_TAG

# Update fastly-mock if needed
kubectl set image deployment/fastly-mock-deployment \
  fastly-mock=gcr.io/sandbox-merino-ohttp/fastly-mock:$IMAGE_TAG

# 3. Watch rollout
kubectl rollout status deployment/merino-deployment
kubectl rollout status deployment/fastly-mock-deployment

# 4. Verify pods are running
kubectl get pods -l app=merino
```

### Full Re-deployment (configuration changes)

```bash
# 1. Build and push images (if needed)
export IMAGE_TAG=v$(date +%Y%m%d-%H%M%S)
docker build -t gcr.io/sandbox-merino-ohttp/merino:$IMAGE_TAG .
docker push gcr.io/sandbox-merino-ohttp/merino:$IMAGE_TAG

# 2. Update gke-patches.yaml with new image tag
vim k8s/overlays/gke/gke-patches.yaml

# 3. Apply updated configuration
cd k8s/overlays/gke
kubectl apply -k .

# 4. Monitor deployment
kubectl rollout status deployment/merino-deployment
kubectl rollout status deployment/fastly-mock-deployment
```

### Rollback a Deployment

```bash
# View deployment history
kubectl rollout history deployment/merino-deployment

# Rollback to previous version
kubectl rollout undo deployment/merino-deployment
kubectl rollout undo deployment/fastly-mock-deployment

# Rollback to specific revision
kubectl rollout undo deployment/merino-deployment --to-revision=2
kubectl rollout undo deployment/fastly-mock-deployment --to-revision=2

# Check rollout status
kubectl rollout status deployment/merino-deployment
kubectl rollout status deployment/fastly-mock-deployment
```

## Monitoring & Debugging

### Check Pod Logs

```bash
# Get all pods
kubectl get pods

# View logs for a specific pod
kubectl logs <pod-name> -c merino
kubectl logs <pod-name> -c ohttp-gateway

# Follow logs in real-time
kubectl logs -f <pod-name> -c merino

# View logs for all pods with app=merino
kubectl logs -l app=merino -c merino --tail=100
```

### Debug Pod Issues

```bash
# Describe a pod to see events and configuration
kubectl describe pod <pod-name>

# Get detailed deployment information
kubectl describe deployment merino-deployment
kubectl describe deployment fastly-mock-deployment

# Check resource usage
kubectl top pods
kubectl top nodes
```

### Access Pod Shell

```bash
# Execute shell in merino container
kubectl exec -it <pod-name> -c merino -- /bin/bash

# Execute shell in ohttp-gateway container
kubectl exec -it <pod-name> -c ohttp-gateway -- /bin/sh

# Execute shell in fastly-mock container
kubectl exec -it <fastly-mock-pod-name> -c fastly-mock -- /bin/sh
```

### Check Service Connectivity

```bash
# Test internal service connectivity
kubectl run debug-pod --image=curlimages/curl --rm -it --restart=Never -- /bin/sh

# From inside the debug pod:
curl merino-service:8000/api/v1/curated-recommendations
curl merino-service:8080/api/v2/ohttp-keys
curl fastly-mock-service:80/health  # Health check for Fastly mock
```

### Check GKE Cluster Status

```bash
# Cluster info
kubectl cluster-info

# Node status
kubectl get nodes -o wide

# Check cluster events
kubectl get events --sort-by=.metadata.creationTimestamp

# Check persistent volumes (if any)
kubectl get pv,pvc
```

## Cleanup

### Delete Deployment Only

```bash
# Delete the deployment (keeps services, ingress)
kubectl delete deployment merino-deployment
kubectl delete deployment fastly-mock-deployment

# Delete everything from the overlay
cd k8s/overlays/gke
kubectl delete -k .
```

### Complete Cleanup

```bash
# Delete all resources
kubectl delete -k k8s/overlays/gke/

# Or delete specific resources
kubectl delete deployment,service,ingress -l app=merino
kubectl delete deployment,service,ingress -l app=fastly-mock

# Clean up images from GCR (optional)
gcloud container images list --repository=gcr.io/sandbox-merino-ohttp
gcloud container images delete gcr.io/sandbox-merino-ohttp/merino:TAG_NAME
gcloud container images delete gcr.io/sandbox-merino-ohttp/ohttp-gateway:TAG_NAME
gcloud container images delete gcr.io/sandbox-merino-ohttp/fastly-mock:TAG_NAME
```

## Troubleshooting

### Common Issues

**Pods not starting:**
```bash
kubectl describe pod <pod-name>
kubectl logs <pod-name> -c <container-name>
```

**Image pull errors:**
```bash
# Check if images exist in registry
gcloud container images list --repository=gcr.io/sandbox-merino-ohttp

# Verify Docker auth
gcloud auth configure-docker gcr.io
```

**Service not accessible:**
```bash
# Check ingress configuration
kubectl describe ingress merino-ingress-v1
kubectl describe ingress merino-ingress-v2

# Check service endpoints
kubectl get endpoints
```

### Useful Commands Quick Reference

```bash
# Quick status check
kubectl get pods,svc,ingress -o wide

# View all resources
kubectl get all

# Port forward for local testing
kubectl port-forward svc/merino-service 8080:8080

# View resource usage
kubectl top pods --containers

# Get external IPs
kubectl get ingress -o wide
```
