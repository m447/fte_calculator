# Deployment Configuration

## Production URL

**https://fte-calc-638044991573.europe-west1.run.app**

## Cloud Run Service

- **Service name:** `fte-calc`
- **Project:** `gen-lang-client-0415148507`
- **Region:** `europe-west1`

## Deploy Command

```bash
gcloud run deploy fte-calc --source . --region europe-west1 --allow-unauthenticated --memory 1Gi --timeout 300
```

## Notes

- Always use service name `fte-calc` (not `fte-calculator`)
- Memory: 1Gi
- Timeout: 300 seconds
