"""API validation and end-to-end HTTP flow."""

from tests.conftest import VALID_EVALUATION, VALID_INSIGHTS, VALID_QUESTION, FakeLLM, make_client


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["llm_configured"] is False and body["llm_provider"] == "offline"


def test_ui_and_docs_are_served(client):
    assert "AI Job Interview" in client.get("/").text
    assert client.get("/docs").status_code == 200
    assert "/api/analyze" in client.get("/openapi.json").json()["paths"]


def test_samples(client):
    body = client.get("/api/documents/samples").json()
    assert "Alex Morgan".upper() in body["cv_text"] and "Machine Learning Engineer" in body["job_text"]


def test_extract_endpoint(client):
    ok = client.post("/api/documents/extract", files={"file": ("cv.txt", b"Python developer \xe2\x80\xa2 FAISS", "text/plain")})
    assert ok.status_code == 200 and ok.json()["text"] == "Python developer • FAISS"
    bad = client.post("/api/documents/extract", files={"file": ("cv.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 415 and bad.json()["error"] == "unsupported_format"
    empty = client.post("/api/documents/extract", files={"file": ("cv.txt", b"", "text/plain")})
    assert empty.status_code == 422 and "empty" in empty.json()["message"]
    missing = client.post("/api/documents/extract")
    assert missing.status_code == 422 and missing.json()["error"] == "invalid_request"


def test_extract_rejects_oversized_upload(settings):
    small = settings.model_copy(update={"max_upload_mb": 0.001})
    with make_client(small) as c:
        r = c.post("/api/documents/extract", files={"file": ("cv.txt", b"a" * 5_000, "text/plain")})
    assert r.status_code == 422 and "too large" in r.json()["message"]


def test_analyze_validation_errors(client, sample_job_text):
    missing = client.post("/api/analyze", json={"job_text": sample_job_text})
    assert missing.status_code == 422 and "cv_text" in missing.json()["message"]
    short = client.post("/api/analyze", json={"cv_text": "Python dev", "job_text": sample_job_text})
    assert short.status_code == 422 and short.json()["error"] == "document_error"
    assert "too short" in short.json()["message"]


def test_unknown_session_and_question(client, sample_cv_text, sample_job_text):
    r = client.post("/api/interview/question", json={"session_id": "nope"})
    assert r.status_code == 404 and r.json()["error"] == "session_not_found"
    sid = client.post("/api/analyze", json={"cv_text": sample_cv_text, "job_text": sample_job_text}).json()["session_id"]
    r = client.post("/api/interview/answer", json={"session_id": sid, "question_id": "x", "answer": "hi"})
    assert r.status_code == 400
    r = client.post("/api/interview/question", json={"session_id": sid, "category": "trivia"})
    assert r.status_code == 422


def test_full_flow_offline(client, sample_cv_text, sample_job_text):
    analysis = client.post("/api/analyze", json={"cv_text": sample_cv_text, "job_text": sample_job_text})
    assert analysis.status_code == 200
    body = analysis.json()
    assert body["pipeline"]["index_size"] == sum(d["chunks"] for d in body["documents"])
    assert body["match"]["matching_skills"] and body["match"]["breakdown"]
    q = client.post("/api/interview/question", json={"session_id": body["session_id"]}).json()
    e = client.post("/api/interview/answer", json={"session_id": body["session_id"], "question_id": q["question_id"],
                                                   "answer": "I built a RAG assistant with FAISS and FastAPI."})
    assert e.status_code == 200 and 0 <= e.json()["score"] <= 10


def test_full_flow_with_mocked_llm(settings, sample_cv_text, sample_job_text):
    llm = FakeLLM([VALID_INSIGHTS, VALID_QUESTION, VALID_EVALUATION])
    with make_client(settings, llm=llm) as c:
        assert c.get("/api/health").json()["llm_configured"] is True
        a = c.post("/api/analyze", json={"cv_text": sample_cv_text, "job_text": sample_job_text}).json()
        assert a["insights_generated_by"] == "llm"
        q = c.post("/api/interview/question", json={"session_id": a["session_id"]}).json()
        e = c.post("/api/interview/answer", json={"session_id": a["session_id"], "question_id": q["question_id"],
                                                  "answer": "Flat index because the corpus was small."}).json()
        assert e["score"] == 7.0 and e["evaluation"]["improved_answer"].startswith("At Brightleaf")


def test_unexpected_errors_are_not_leaked(settings, sample_cv_text, sample_job_text):
    class Boom:
        name = "boom"

        def complete(self, messages, json_mode=True):
            raise RuntimeError("secret internal detail /etc/passwd")

    with make_client(settings, llm=Boom(), raise_server_exceptions=False) as c:
        r = c.post("/api/analyze", json={"cv_text": sample_cv_text, "job_text": sample_job_text})
    assert r.status_code == 500
    assert "secret" not in r.text and r.json()["error"] == "internal_error"
