from fastapi import APIRouter, Depends

from app.api.dependencies import get_pipeline
from app.models.schemas import AnswerRequest, ErrorResponse, EvaluationResponse, QuestionRequest, QuestionResponse
from app.rag.pipeline import CoachPipeline

router = APIRouter(prefix="/interview", tags=["interview"])


@router.post(
    "/question",
    response_model=QuestionResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Generate the next personalised interview question (RAG)",
)
def next_question(request: QuestionRequest, pipeline: CoachPipeline = Depends(get_pipeline)) -> QuestionResponse:
    return pipeline.next_question(request.session_id, request.category)


@router.post(
    "/answer",
    response_model=EvaluationResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Evaluate an answer against the question, the rubric and the retrieved context",
)
def evaluate_answer(request: AnswerRequest, pipeline: CoachPipeline = Depends(get_pipeline)) -> EvaluationResponse:
    return pipeline.evaluate(request.session_id, request.question_id, request.answer)
