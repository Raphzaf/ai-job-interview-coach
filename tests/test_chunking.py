"""Tokenization and section-aware chunking."""

import pytest

from app.document_processing.chunker import Chunker, is_heading, split_sections
from app.document_processing.tokenizer import ApproximateTokenCounter, build_token_counter


def test_approximate_counter_counts_words_and_punctuation():
    counter = ApproximateTokenCounter()
    assert counter.count("") == 0
    assert counter.count("Python, SQL") > counter.count("Python")


def test_build_token_counter_for_hashing_mode_is_approximate():
    assert isinstance(build_token_counter("hashing", "unused"), ApproximateTokenCounter)


@pytest.mark.parametrize("line, expected", [
    ("EXPERIENCE", True), ("Work Experience:", True), ("Requirements", True), ("NICE TO HAVE", True),
    ("- Built APIs", False), ("Python developer with 5 years of experience.", False), ("AWS", False),
])
def test_heading_detection(line, expected):
    assert is_heading(line) is expected


def test_split_sections_groups_bullets_and_paragraphs():
    text = "SUMMARY\nData scientist.\nLoves NLP.\n\nSKILLS\n- Python\n- SQL"
    sections = split_sections(text)
    assert [s.title for s in sections] == ["Summary", "Skills"]
    assert sections[0].units == ["Data scientist. Loves NLP."]
    assert sections[1].units == ["- Python", "- SQL"]


def test_chunks_respect_token_budget_and_keep_metadata(processor, sample_docs):
    cv, _ = sample_docs
    chunks = processor.chunk(cv)
    counter = processor.token_counter
    assert len(chunks) >= 5
    for i, c in enumerate(chunks):
        assert c.chunk_id == f"cv-{i}" and c.position == i
        assert c.doc_type == "cv" and c.doc_name == "sample_cv.txt"
        assert counter.count(c.embedding_text) <= processor.settings.chunk_max_tokens
    assert {"Work Experience", "Skills", "Education"} <= {c.section for c in chunks}


def test_chunks_never_cross_sections(processor, sample_docs):
    cv, _ = sample_docs
    for chunk in processor.chunk(cv):
        assert "EDUCATION" not in chunk.text and "SKILLS" not in chunk.text


def test_new_entry_starts_new_chunk(counter):
    text = ("EXPERIENCE\nEngineer - Acme\n2020 - 2022\n- Built A\n- Built B\n"
            "Analyst - Globex\n2018 - 2020\n- Did C")
    chunks = Chunker(counter, max_tokens=200, overlap_tokens=10).chunk(text, "cv", "cv")
    assert len(chunks) == 2
    assert chunks[1].text.startswith("Analyst - Globex")


def test_overlap_carries_previous_unit(counter):
    bullets = "\n".join(f"- Bullet number {i} describing a project with several words" for i in range(12))
    chunks = Chunker(counter, max_tokens=60, overlap_tokens=20).chunk("PROJECTS\n" + bullets, "cv", "cv")
    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:]):
        assert previous.text.split("\n")[-1] == current.text.split("\n")[0]


def test_oversized_unit_is_split(counter):
    long_paragraph = "SUMMARY\n" + " ".join(["Experienced engineer building reliable data systems."] * 40)
    chunker = Chunker(counter, max_tokens=50, overlap_tokens=5)
    chunks = chunker.chunk(long_paragraph, "cv", "cv")
    assert len(chunks) > 3
    assert all(counter.count(c.embedding_text) <= 50 for c in chunks)


def test_invalid_overlap_rejected(counter):
    with pytest.raises(ValueError):
        Chunker(counter, max_tokens=50, overlap_tokens=50)
