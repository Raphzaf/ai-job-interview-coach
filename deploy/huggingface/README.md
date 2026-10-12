# Deploying the coach on Hugging Face Spaces

**Why Hugging Face Spaces:**
- The coach loads PyTorch + sentence-transformers, so it needs about 1 GB of RAM.
- Free tiers of most hosts (512 MB) are too small. The free "CPU basic" Space hardware (2 vCPU, 16 GB RAM) runs the project's existing Docker image unchanged.
- The coach needs no database: its market context ships inside the image.

**What gets deployed:**
- the coach (FastAPI + web UI), from the repository's own `Dockerfile`;
- not the data pipeline or PostgreSQL. Those are offline analysis tools; their results are already in the app.

## Steps (about 15 minutes, done once)

1. Create a free account on <https://huggingface.co> and an **access token** with *write* permission (Settings → Access Tokens).
2. Create a new Space at <https://huggingface.co/new-space>:
   - **Name:** e.g. `ai-job-interview-coach`;
   - **SDK:** *Docker*, template *Blank*;
   - **Hardware:** *CPU basic (free)*;
   - **Visibility:** *Public* (needed for the "deployed link").
3. In the Space → **Settings → Variables and secrets**, add:

   | Name | Type | Value |
   |---|---|---|
   | `LLM_API_KEY` | **Secret** | your Gemini API key |
   | `LLM_MODEL` | Variable | `gemini-flash-latest` |
   | `LLM_BASE_URL` | Variable | `https://generativelanguage.googleapis.com/v1beta/openai/` |

   Without them, the Space still works in labelled offline mode.
4. From the repository root, build the Space content and push it:

   ```bash
   bash deploy/huggingface/prepare_space.sh /tmp/hf-space
   cd /tmp/hf-space
   git init -b main && git add . && git commit -m "Deploy AI Job Market & Interview Coach"
   git remote add origin https://huggingface.co/spaces/<your-username>/ai-job-interview-coach
   git push -f origin main          # username + the access token as password
   ```

5. The Space builds the image (about 5–10 minutes the first time) and then starts. Open `https://<your-username>-ai-job-interview-coach.hf.space`, then check `/api/health` and run the sample analysis.

## Things to know

- **Your API quota is public.** Anyone who opens the Space uses your LLM key. Gemini's free tier limits requests. When the quota is exhausted, the app falls back to offline mode and says so. Watch usage after the Demo Day, or remove the secret.
- **Privacy:** visitors' CVs are processed in memory and sent to the LLM provider. Recommend the sample documents or fictional CVs (the Space card says so).
- **Sleep:** free Spaces sleep after 48 h without visits. The first visit then takes about 1 minute to wake up, so **open the Space before you present**.
- **Updates:** rerun step 4 after changing the app.
