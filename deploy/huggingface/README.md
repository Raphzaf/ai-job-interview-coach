# Deploying the coach on Hugging Face Spaces

> **Update (2026-10):** Hugging Face now requires a paid plan (PRO) to create Docker Spaces. The live app runs on Google Cloud Run instead: see [`../cloudrun/README.md`](../cloudrun/README.md). This kit still works with a PRO account.

**Why Hugging Face Spaces:**
- The coach loads PyTorch + sentence-transformers, so it needs about 1 GB of RAM.
- Free tiers of most hosts (512 MB) are too small. The free "CPU basic" Space hardware (2 vCPU, 16 GB RAM) runs the project's own `Dockerfile` unchanged.
- The coach needs no database: its market context ships inside the image.

**What gets deployed:**
- the coach (FastAPI + web UI);
- not the data pipeline or PostgreSQL. Those are offline analysis tools whose results are already in the app.

## Deploy in one command (about 5 minutes of your time)

1. Create a free account on <https://huggingface.co>, then an **access token** with *Write* permission (Settings → Access Tokens → *Create new token* → *Write*).
2. Optional but recommended: a free Gemini API key from <https://aistudio.google.com/apikey>. Without it, the app runs in labelled offline mode.
3. From the repository root, with the project's virtual environment active (`huggingface_hub` is already installed with the requirements):

   ```bash
   HF_TOKEN=hf_xxx LLM_API_KEY=your-gemini-key \
     python deploy/huggingface/deploy.py <your-hf-username>/ai-job-interview-coach
   ```

   On Windows PowerShell:

   ```powershell
   $env:HF_TOKEN="hf_xxx"; $env:LLM_API_KEY="your-gemini-key"
   python deploy/huggingface/deploy.py <your-hf-username>/ai-job-interview-coach
   ```

   The script:
   - creates the public Docker Space;
   - stores the Gemini key as a Space **secret**, plus `LLM_MODEL=gemini-flash-latest` and the Gemini endpoint as variables;
   - uploads the coach.

   To use another provider, set `LLM_MODEL` and `LLM_BASE_URL` in the same command.
4. Hugging Face builds the image. The first build takes about 10 minutes, and you can follow the logs on the Space page. The app is then live at the URL the script printed: `https://<username>-ai-job-interview-coach.hf.space`.
5. **Check it:** open the URL, click **Load sample documents → Analyze match**. The badge in the top-right corner must show `gemini-flash-latest`, and the analysis must show the "Job market context" panel.

**Updating after a code change:** run the same command again; it re-uploads the files and Hugging Face rebuilds.

**To only look at what would be uploaded:** `python deploy/huggingface/deploy.py --dry-run /tmp/hf-space`.

## Things to know

- **Your API quota is public.** Anyone who opens the Space uses your LLM key. Gemini's free tier limits requests per minute and per day. When the quota is exhausted, the app falls back to offline mode and says so. Watch usage after the Demo Day, or delete the secret in Space → Settings.
- **Privacy:** visitors' CVs are processed in memory and sent to the LLM provider. The Space card asks visitors to use the sample documents or fictional CVs.
- **Sleep:** free Spaces sleep after 48 h without visits, and the next visit takes about a minute to wake the Space. **Open the Space a few minutes before you present.**
- **Manual alternative:** you can also create the Space in the web interface (SDK *Docker*), add the secret and variables in Settings, and upload the folder produced by `--dry-run` with *Files → Upload files*. Don't use plain `git push`: the Hub rejects the sample PDF/DOCX unless Git Xet/LFS is set up.
