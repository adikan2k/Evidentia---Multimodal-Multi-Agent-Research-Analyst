# Deploying Evidentia

Two pieces: the API on Google Cloud Run, the site on Vercel. Deploy the API first, because the
site needs its address.

All commands run from the repository root with `gcloud` signed in and a default project set.
The region used here is `us-central1`.

Current deployment (2026-11-24): project `evidentia-515709`, service `evidentia-api`, at
https://evidentia-api-499389159505.us-central1.run.app

The site is the Vercel project `evidentia`, at https://evidentia-green.vercel.app , building the
`web` folder of the `rebuild` branch.

## 1. The API on Cloud Run

### 1a. Switch on the services (once per project)

```
gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com
```

### 1b. Store the keys as secrets (once; done by a person)

In the Google Cloud console, open **Security > Secret Manager** and create one secret for each
name below, pasting the value from your `.env`. The names must match exactly.

```
ANTHROPIC_API_KEY
TAVILY_API_KEY
VOYAGE_API_KEY
QDRANT_URL
QDRANT_API_KEY
LANGFUSE_PUBLIC_KEY
LANGFUSE_SECRET_KEY
```

`LANGFUSE_HOST` is not needed: the code defaults to the US region this project uses.

### 1c. Give the API its own identity that can read only these secrets (once per project)

```
gcloud iam service-accounts create evidentia-api --display-name "Evidentia API"
```

Then, once for each of the seven secret names (shown here for the first):

```
gcloud secrets add-iam-policy-binding ANTHROPIC_API_KEY --member="serviceAccount:evidentia-api@YOUR-PROJECT-ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

### 1d. Build and deploy

```
gcloud run deploy evidentia-api --source . --region us-central1 --service-account evidentia-api@YOUR-PROJECT-ID.iam.gserviceaccount.com --allow-unauthenticated --max-instances 1 --min-instances 0 --memory 1Gi --cpu 1 --timeout 300 --set-secrets "ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,TAVILY_API_KEY=TAVILY_API_KEY:latest,VOYAGE_API_KEY=VOYAGE_API_KEY:latest,QDRANT_URL=QDRANT_URL:latest,QDRANT_API_KEY=QDRANT_API_KEY:latest,LANGFUSE_PUBLIC_KEY=LANGFUSE_PUBLIC_KEY:latest,LANGFUSE_SECRET_KEY=LANGFUSE_SECRET_KEY:latest"
```

If `gcloud` is pointed at a different project by default, add `--project YOUR-PROJECT-ID` to
every command on this page.

Why these flags:

- `--service-account`: the API runs as an identity that can read the seven secrets and nothing
  else in the project.

- `--max-instances 1`: the spend limits are counted in memory, so there must be one instance.
- `--min-instances 0`: nothing runs, and nothing is billed, while nobody is using it. The first
  request after a quiet spell takes a few seconds longer.
- `--timeout 300`: a run streams for about half a minute; this leaves plenty of room.
- `--allow-unauthenticated`: the site calls it from visitors' browsers.

The command prints the service URL. Check it:

```
curl https://YOUR-SERVICE-URL/health
```

## 2. The site on Vercel

In the Vercel dashboard:

1. **Add New > Project**, and import this GitHub repository.
2. Set **Root Directory** to `web`. Vercel detects Next.js by itself.
3. Add an environment variable: `NEXT_PUBLIC_API_URL` = the Cloud Run URL from step 1d, with no
   trailing slash.
4. Deploy.
5. Until `rebuild` is merged into `main`: under **Settings > Git**, set **Production Branch** to
   `rebuild`, then redeploy.

## 3. Tell the API which site may call it

Browsers only let the site call the API if the API names the site's address. Use the address
Vercel gave you:

```
gcloud run services update evidentia-api --region us-central1 --update-env-vars ALLOWED_ORIGINS=https://YOUR-SITE.vercel.app
```

Several addresses can be given, separated by commas.

## 4. Spend limits

In code (`evidentia/config.py`), changeable with environment variables of the same name in
capitals:

| Setting | Default | Meaning |
|---|---|---|
| `daily_budget_usd` | 1.00 | All live runs and checks in one UTC day |
| `public_run_cap_usd` | 0.25 | One live run |
| `max_runs_per_ip` | 3 | Live runs per address per day |
| `max_checks_per_ip` | 30 | "Try to break it" checks per address per day |
| `max_concurrent_runs` | 2 | Runs at the same moment |

The counters live in memory and reset if the instance restarts. Set a monthly spend limit in
the Anthropic console as well; that is the limit that cannot be bypassed.

## Redeploying

- API: run the command in 1d again.
- Site: push to the production branch; Vercel rebuilds by itself.
- New recorded runs: `uv run python -m evidentia.record <id> "<question>"`, commit the files it
  writes under `web/public/replays/`, and push.
