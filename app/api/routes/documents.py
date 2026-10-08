from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.dependencies import Container, get_container
from app.core.errors import DocumentError
from app.document_processing.cleaner import clean_text
from app.document_processing.extractors import extract_text
from app.models.schemas import ErrorResponse, ExtractResponse, SampleDocuments

router = APIRouter(prefix="/documents", tags=["documents"])

EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "data" / "examples"


@router.post(
    "/extract",
    response_model=ExtractResponse,
    responses={415: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Extract and clean text from a PDF, DOCX or TXT file",
)
async def extract(file: UploadFile = File(...), container: Container = Depends(get_container)) -> ExtractResponse:
    max_bytes = int(container.settings.max_upload_mb * 1_048_576)
    # Read one byte more than allowed so oversized files are detected without
    # loading arbitrarily large uploads into memory.
    content = await file.read(max_bytes + 1)
    filename = file.filename or "upload"
    text = clean_text(extract_text(filename, content, max_bytes=max_bytes))
    if not text:
        raise DocumentError(f"No readable text was found in '{filename}'.")
    return ExtractResponse(filename=filename, characters=len(text), text=text)


@router.get("/samples", response_model=SampleDocuments, summary="Fictional sample CV and job description for demos")
def samples() -> SampleDocuments:
    return SampleDocuments(
        cv_name="sample_cv.txt",
        cv_text=(EXAMPLES_DIR / "sample_cv.txt").read_text(encoding="utf-8"),
        job_name="sample_job_description.txt",
        job_text=(EXAMPLES_DIR / "sample_job_description.txt").read_text(encoding="utf-8"),
    )
