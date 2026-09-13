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

var logAnalyticsName = '${namePrefix}-logs'
var envName = '${namePrefix}-env'
var appName = '${namePrefix}-backend'

var hasRegistry = !empty(registryServer)
var hasAccessCode = !empty(demoAccessCode)

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
            [
              {
                name: 'DEMO_DAILY_TURN_CEILING'
                value: string(dailyTurnCeiling)
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
