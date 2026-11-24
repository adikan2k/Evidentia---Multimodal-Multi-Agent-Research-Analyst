# Evidentia: the site

The Next.js app for Evidentia. It replays recorded runs from `public/replays/`, runs live ones
through the API, and shows the eval results from `src/data/evals.json`.

## Running it

```
npm install
npm run dev
```

Then open http://localhost:3000. Recorded runs and the Evals page work on their own. Live runs
and "Try to break it" need the API, started from the repository root:

```
uv run uvicorn evidentia.api:create_app --factory --port 8000
```

The site finds the API through `NEXT_PUBLIC_API_URL`, which defaults to `http://localhost:8000`.

## Where things come from

- `public/replays/*.json`: real runs, recorded with `python -m evidentia.record`.
- `src/data/evals.json`: written by `python -m evals report` from the files in `evals/results/`.
  Every number on the site is read from it.

Deployment is described in `docs/DEPLOY.md`.
