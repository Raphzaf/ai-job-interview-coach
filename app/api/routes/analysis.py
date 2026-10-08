from fastapi import APIRouter, Depends

from app.api.dependencies import get_pipeline
from app.models.schemas import AnalyzeRequest, AnalyzeResponse, ErrorResponse
from app.rag.pipeline import CoachPipeline

router = APIRouter(tags=["analysis"])


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={422: {"model": ErrorResponse}},
    summary="Run the full pipeline on a CV and a job description",
    description=(
        "Cleans and chunks both documents, embeds the chunks, builds a FAISS index, computes the "
        "transparent match score and generates grounded insights. Returns a `session_id` used by "
        "the interview endpoints."
    ),
)
def analyze(request: AnalyzeRequest, pipeline: CoachPipeline = Depends(get_pipeline)) -> AnalyzeResponse:
    return pipeline.analyze(request)
