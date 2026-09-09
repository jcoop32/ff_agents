#!/bin/bash
set -e

# ==============================================================================
# Gridiron AI Deployment Script
# Target: Multi-node K3s Kubernetes cluster over Tailscale mesh (x86_64 / amd64)
# Host Dev Machine: Apple Silicon (ARM64)
# ==============================================================================

BACKEND_IMAGE="jcooper23/gridiron-ai:latest"
FRONTEND_IMAGE="jcooper23/gridiron-ui:latest"

echo "========================================================"
echo "🚀 Step 1: Cross-compiling container images for linux/amd64..."
echo "Backend:  ${BACKEND_IMAGE}"
echo "Frontend: ${FRONTEND_IMAGE}"
echo "========================================================"

docker build --platform linux/amd64 -t ${BACKEND_IMAGE} .
docker build --platform linux/amd64 --no-cache -t ${FRONTEND_IMAGE} ./frontend

echo ""
echo "========================================================"
echo "📦 Step 2: Pushing images to Docker Hub registry..."
echo "========================================================"

docker push ${BACKEND_IMAGE}
docker push ${FRONTEND_IMAGE}

echo ""
echo "========================================================"
echo "☸️  Step 3: Applying Kubernetes manifests to K3s cluster..."
echo "========================================================"

# 1. Namespace
echo "Creating/Verifying namespace 'gridiron-ai'..."
kubectl apply -f k8s/namespace.yaml

# 2. Secret
if [ -f k8s/secrets.yaml ]; then
    echo "Applying k8s/secrets.yaml..."
    kubectl apply -f k8s/secrets.yaml
elif kubectl get secret gridiron-secrets -n gridiron-ai &> /dev/null; then
    echo "Existing secret 'gridiron-secrets' found in namespace 'gridiron-ai'."
else
    echo "⚠️ Warning: k8s/secrets.yaml not found and secret 'gridiron-secrets' does not exist in cluster."
    echo "Please create gridiron-secrets before starting application pods."
fi

# 3. Persistent Storage & Databases
echo "Applying persistent volumes & databases (PostgreSQL, Redis)..."
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml

# 4. Microservices
echo "Applying application deployments & services..."
kubectl apply -f k8s/app.yaml
kubectl apply -f k8s/frontend.yaml
kubectl apply -f k8s/worker.yaml
kubectl apply -f k8s/discord-bot.yaml

# 5. Rolling restart to pick up latest images
echo ""
echo "Triggering rolling restart for updated images..."
kubectl rollout restart deployment -n gridiron-ai app-deployment frontend-deployment worker-deployment discord-bot-deployment 2>/dev/null || true

echo ""
echo "========================================================"
echo "✅ Build, Push, and Deployment Applied Successfully!"
echo "========================================================"
echo ""
echo "📊 Checking Pod Status in namespace 'gridiron-ai':"
kubectl get pods -n gridiron-ai
echo ""
echo "Active K3s Cluster Node URLs (Tailscale NodePort):"
if command -v kubectl &> /dev/null && kubectl get nodes &> /dev/null; then
    kubectl get nodes -o custom-columns='NODE:.metadata.name,IP:.status.addresses[0].address' --no-headers 2>/dev/null | while read -r node ip; do
        echo "   • $node ($ip):"
        echo "     - Web GUI:  http://$ip:31081"
        echo "     - API Docs: http://$ip:31080/docs"
    done
else
    echo "   FastAPI Web API: http://<tailscale-node-ip>:31080/docs"
    echo "   Next.js Web GUI: http://<tailscale-node-ip>:31081"
fi
echo "========================================================"

