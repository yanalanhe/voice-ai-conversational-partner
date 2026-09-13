// Azure Container Apps deployment for the Parlons backend.
//
// NOT VALIDATED against a live Azure subscription -- neither the Azure CLI
// nor the standalone Bicep CLI was available in the environment this was
// authored in (see infra/README.md). Run `az bicep build --file main.bicep`
// yourself before deploying to catch anything wrong here.
//
// Pinned to Canada Central throughout -- see docs/COMPLIANCE.md for why
// region pinning matters for this project and what was and wasn't verified
// about realtime-model availability in this region.

@description('Azure region. Pinned to Canada Central for the data-residency story -- see docs/COMPLIANCE.md.')
param location string = 'canadacentral'

@description('Name prefix for all resources.')
param namePrefix string = 'parlons'

@description('Full container image reference, e.g. myregistry.azurecr.io/parlons-backend:latest. Build and push it yourself first -- see infra/README.md.')
param containerImage string

@description('Container registry server. Leave empty if containerImage is public.')
param registryServer string = ''

@description('Container registry username, required if registryServer is set.')
param registryUsername string = ''

@secure()
@description('Container registry password, required if registryServer is set.')
param registryPassword string = ''

@secure()
@description('Optional shared demo access code -- see server/app/security/demo_guard.py. Leave empty to disable the guard (not recommended for a public deployment).')
param demoAccessCode string = ''

@description('Max turns allowed across ALL sessions per UTC day -- see DailySpendCeiling in demo_guard.py.')
param dailyTurnCeiling int = 500

@description('Max turns allowed within one session -- see TurnCapEnforcer in demo_guard.py.')
param turnsPerSession int = 20

@description('Which demo script main.py serves: "zh_hsk" (pedagogy-backed Mandarin demo, default) or "generic" (plain English, optionally backed by real providers -- see the azure* params).')
param demoScript string = 'zh_hsk'

@description('Azure AI Speech key. Only used by DEMO_SCRIPT=generic; all five real-provider params must be set together or main.py falls back to mocks -- see app/main.py _USE_REAL_GENERIC_PROVIDERS.')
@secure()
param azureSpeechKey string = ''

@description('Azure AI Speech region, e.g. canadacentral.')
param azureSpeechRegion string = ''

@description('Azure OpenAI resource endpoint, e.g. https://<resource>.openai.azure.com/.')
param azureOpenAiEndpoint string = ''

@secure()
@description('Azure OpenAI API key.')
param azureOpenAiApiKey string = ''

@description('Azure OpenAI chat deployment name (not the base model name).')
param azureOpenAiDeployment string = ''

var logAnalyticsName = '${namePrefix}-logs'
var envName = '${namePrefix}-env'
var appName = '${namePrefix}-backend'

var hasRegistry = !empty(registryServer)
var hasAccessCode = !empty(demoAccessCode)
var hasRealProviders = !empty(azureSpeechKey) && !empty(azureOpenAiApiKey)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource containerAppEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: appName
  location: location
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        // 'auto' negotiates HTTP/1.1 with WebSocket upgrade support, which
        // the backend's /ws/session endpoint requires (see docs/COMPLIANCE.md
        // for why this cannot be a Vercel serverless function instead).
        transport: 'auto'
      }
      secrets: concat(
        hasRegistry
          ? [
              {
                name: 'registry-password'
                value: registryPassword
              }
            ]
          : [],
        hasAccessCode
          ? [
              {
                name: 'demo-access-code'
                value: demoAccessCode
              }
            ]
          : [],
        hasRealProviders
          ? [
              {
                name: 'azure-speech-key'
                value: azureSpeechKey
              }
              {
                name: 'azure-openai-api-key'
                value: azureOpenAiApiKey
              }
            ]
          : []
      )
      registries: hasRegistry
        ? [
            {
              server: registryServer
              username: registryUsername
              passwordSecretRef: 'registry-password'
            }
          ]
        : []
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(
            hasAccessCode
              ? [
                  {
                    name: 'DEMO_ACCESS_CODE'
                    secretRef: 'demo-access-code'
                  }
                ]
              : [],
            hasRealProviders
              ? [
                  {
                    name: 'AZURE_SPEECH_KEY'
                    secretRef: 'azure-speech-key'
                  }
                  {
                    name: 'AZURE_SPEECH_REGION'
                    value: azureSpeechRegion
                  }
                  {
                    name: 'AZURE_OPENAI_ENDPOINT'
                    value: azureOpenAiEndpoint
                  }
                  {
                    name: 'AZURE_OPENAI_API_KEY'
                    secretRef: 'azure-openai-api-key'
                  }
                  {
                    name: 'AZURE_OPENAI_DEPLOYMENT'
                    value: azureOpenAiDeployment
                  }
                ]
              : [],
            [
              {
                name: 'DEMO_DAILY_TURN_CEILING'
                value: string(dailyTurnCeiling)
              }
              {
                name: 'DEMO_TURNS_PER_SESSION'
                value: string(turnsPerSession)
              }
              {
                name: 'DEMO_SCRIPT'
                value: demoScript
              }
            ]
          )
        }
      ]
      scale: {
        // A single replica by design: the demo guards in demo_guard.py are
        // in-memory and process-local (see their module docstring). Scaling
        // out would let each replica enforce its own independent rate limit
        // and daily ceiling, silently multiplying the intended budget.
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output backendUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
