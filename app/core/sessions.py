"""In-memory session store.

A session holds everything computed during analysis (documents, chunks, the
FAISS index, the match report) so that interview questions and answer
evaluations reuse the same index instead of re-embedding the documents on every
request. Sessions are kept in memory with a TTL: no database is needed for the
MVP and no CV is ever written to disk.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from app.core.errors import SessionNotFoundError
from app.models.domain import Document, RetrievedChunk
from app.models.schemas import InterviewQuestion, MatchReport
from app.rag.interview_planner import InterviewPlanner
from app.retrieval.retriever import Retriever


@dataclass
class AskedQuestion:
    question_id: str
    question: InterviewQuestion
    context: list[RetrievedChunk]
    scores: list[float] = field(default_factory=list)


@dataclass
class Session:
    session_id: str
    cv: Document
    job: Document
    retriever: Retriever
    match: MatchReport
    planner: InterviewPlanner
    questions: dict[str, AskedQuestion] = field(default_factory=dict)
    last_access: float = field(default_factory=time.time)


class SessionStore:
    def __init__(self, ttl_seconds: int = 2 * 3600, max_sessions: int = 100):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions

    def __len__(self) -> int:
        return len(self._sessions)

    def create(self, **kwargs) -> Session:
        session = Session(session_id=uuid.uuid4().hex[:12], **kwargs)
        with self._lock:
            self._evict()
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or time.time() - session.last_access > self.ttl_seconds:
                self._sessions.pop(session_id, None)
                raise SessionNotFoundError("This analysis session has expired or does not exist. Please run the analysis again.")
            session.last_access = time.time()
            return session

    def _evict(self) -> None:
        now = time.time()
        for sid in [sid for sid, s in self._sessions.items() if now - s.last_access > self.ttl_seconds]:
            del self._sessions[sid]
        # Bound memory: drop the least recently used sessions (each holds an index + model outputs).
        while len(self._sessions) >= self.max_sessions:
            oldest = min(self._sessions.values(), key=lambda s: s.last_access)
            del self._sessions[oldest.session_id]
