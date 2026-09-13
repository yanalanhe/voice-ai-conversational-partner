# Deploying the backend to Azure Container Apps

**This template has not been validated against a live Azure subscription or
even syntax-checked with the Bicep CLI** — neither `az` nor `bicep` was
available in the environment this was authored in. Run `az bicep build
--file main.bicep` yourself before deploying, and expect to fix small
things.

## Why Azure Container Apps and not Vercel

Vercel's serverless and edge runtimes do not support persistent WebSocket
servers, which the backend's `/ws/session` endpoint requires. See
`docs/COMPLIANCE.md` for the full reasoning — this is a platform constraint
that was discovered while planning deployment, not an arbitrary choice.

## Steps

1. **Build and push the backend image** to a registry ACA can pull from
   (Azure Container Registry is the natural choice):

   ```
   az acr create --name <registry-name> --resource-group <rg> --sku Basic
   az acr login --name <registry-name>
   docker build -t <registry-name>.azurecr.io/parlons-backend:latest -f server/Dockerfile .
   docker push <registry-name>.azurecr.io/parlons-backend:latest
   ```

2. **Validate the template**:

   ```
   az bicep build --file infra/main.bicep
   ```

3. **Deploy**:

   ```
   az group create --name parlons-rg --location canadacentral

   az deployment group create \
     --resource-group parlons-rg \
     --template-file infra/main.bicep \
     --parameters \
       containerImage=<registry-name>.azurecr.io/parlons-backend:latest \
       registryServer=<registry-name>.azurecr.io \
       registryUsername=<registry-username> \
       registryPassword=<registry-password> \
       demoAccessCode=<a-shared-secret-you-choose> \
       dailyTurnCeiling=500
   ```

   To run `DEMO_SCRIPT=generic` against real Azure AI Speech + Azure OpenAI instead of
   mocks (see `server/app/providers/azure.py`), add:

   ```
       demoScript=generic \
       azureSpeechKey=<speech-resource-key> \
       azureSpeechRegion=<speech-resource-region> \
       azureOpenAiEndpoint=https://<openai-resource>.openai.azure.com/ \
       azureOpenAiApiKey=<openai-resource-key> \
       azureOpenAiDeployment=<chat-deployment-name>
   ```

   All five must be set together, or `main.py` falls back to the fully-mocked generic
   script. TTS stays mocked either way — only STT and the LLM become real.

4. **Get the backend URL** from the deployment output (`backendUrl`), and use
   it as `VITE_WS_URL` when building the frontend (see the repo root
   README's deployment section) — note the scheme flips from `https://` to
   `wss://` for the WebSocket URL itself.

## What this does NOT do

- No custom domain, no TLS certificate management beyond what Container
  Apps' default `*.azurecontainerapps.io` ingress provides.
- No autoscaling — pinned to exactly 1 replica, because the demo-hardening
  guards (`server/app/security/demo_guard.py`) are in-memory and
  process-local. Scaling out would let each replica enforce its own
  independent daily spend ceiling, silently multiplying the intended budget.
- No verification that realtime voice models are available in
  `canadacentral` — see `docs/VENDOR_BENCHMARK.md`'s open finding. This
  matters only once a realtime adapter exists (see ADR-004); the cascaded
  pipeline this template deploys does not depend on it.
