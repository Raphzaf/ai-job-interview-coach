from fastapi import APIRouter, Depends

from app import __version__
from app.api.dependencies import Container, get_container
from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service status and active configuration")
def health(container: Container = Depends(get_container)) -> HealthResponse:
    pipeline = container.pipeline
    return HealthResponse(
        status="ok",
        version=__version__,
        llm_provider="offline" if pipeline.llm is None else container.settings.llm_provider,
        llm_model="-" if pipeline.llm is None else container.settings.llm_model,
        llm_configured=pipeline.llm is not None,
        embedding_model=pipeline.embedder.model_name,
        active_sessions=len(pipeline.sessions),
    )
