# Deploying the coach on Google Cloud Run

**Live app:** <https://ai-job-interview-coach-291756431151.europe-west1.run.app/> (deployed 2026-10-15)

**Why Cloud Run:**
- The coach loads PyTorch + sentence-transformers and needs about 1 GB of RAM, more than most free tiers (512 MB).
- Since mid-2026, Hugging Face only allows Docker Spaces on paid plans (PRO), so the [Hugging Face kit](../huggingface/README.md) now needs a PRO account.
- Cloud Run builds and runs the project's own `Dockerfile` unchanged. A demo fits in its free tier, and new Google Cloud accounts get free trial credits.

**What gets deployed:** the coach (FastAPI + web UI). Not the data pipeline or PostgreSQL: their results are already inside the app.

## Deploy (about 30 minutes, mostly waiting for the build)

1. On <https://console.cloud.google.com>, create a project and enable billing (the free trial is enough).
2. Open **Cloud Shell** (the `>_` icon, top right). It is a terminal in the browser with `gcloud` and `git` installed.
3. Build and deploy:

   ```bash
   git clone https://github.com/Raphzaf/ai-job-interview-coach.git
   cd ai-job-interview-coach
   gcloud run deploy ai-job-interview-coach --source . --region europe-west1 \
     --port 8000 --memory 2Gi --cpu 1 --allow-unauthenticated \
     --set-env-vars LLM_MODEL=gemini-flash-latest,LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
   ```

   Answer **Y** when asked to enable APIs or create an Artifact Registry repository. Cloud Build builds the image (10–15 minutes), then the command prints the service URL.
4. Add the Gemini key without echoing it on screen or storing it in the shell history:

   ```bash
   read -s -p "Gemini key: " K && gcloud run services update ai-job-interview-coach \
     --region europe-west1 --update-env-vars LLM_API_KEY=$K && unset K
   ```

   Without a key, the app runs in labelled offline mode.
5. **Check it:**
   - `<URL>/api/health` returns `"llm_configured": true` and `"llm_model": "gemini-flash-latest"`;
   - in the web UI, **Load sample documents → Analyze match**: the badge shows `gemini-flash-latest` and the "Job market context" panel appears.

**Updating after a code change:** run step 3 again from an up-to-date clone (`git pull`). The environment variables, including the key, are kept.

## Things to know

- **Cold start:** with no traffic, Cloud Run stops the container. The next visit waits about 30–60 seconds while the model loads. **Open the app a few minutes before presenting.** `--min-instances 1` removes the wait but is billed continuously.
- **Your API quota is public.** Anyone who opens the app uses your Gemini key. When the free quota is exhausted, the app falls back to offline mode and says so. Remove the key after the Demo Day if needed (`gcloud run services update ... --remove-env-vars LLM_API_KEY`).
- **Privacy:** visitors' CVs are processed in memory and sent to the LLM provider. Use the sample documents or fictional CVs.
- **Costs:** check *Billing → Reports* in the console. To stop everything: `gcloud run services delete ai-job-interview-coach --region europe-west1`.
