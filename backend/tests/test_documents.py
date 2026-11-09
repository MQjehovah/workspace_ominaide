import io

from docx import Document
from pptx import Presentation

from ai.mcp.tools.documents import (
    _safe_filename,
    build_pptx_bytes,
    build_word_bytes,
)


def test_word_document_builder():
    data = build_word_bytes(
        "OmniAide 测试文档",
        "# 概览\n## 细节\n- 第一条\n- 第二条\n\n| 指标 | 数值 |\n|---|---|\n| 用户 | 1 |\n",
    )
    assert data[:2] == b"PK"
    doc = Document(io.BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "OmniAide 测试文档" in text
    assert "第一条" in text
    assert len(doc.tables) == 1


def test_presentation_builder():
    data = build_pptx_bytes(
        "季度汇报",
        [
            {"title": "现状", "bullets": ["营收增长", "成本下降"], "notes": "讲稿"},
            {"title": "计划", "bullets": ["扩展渠道"]},
        ],
        subtitle="2026 Q4",
        closing="谢谢",
    )
    assert data[:2] == b"PK"
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == 4
    texts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                texts.append(shape.text)
    joined = "\n".join(texts)
    assert "季度汇报" in joined
    assert "营收增长" in joined
    assert "谢谢" in joined


def test_safe_filename():
    name = _safe_filename('a/b:*? 报告', ".docx")
    assert name.endswith(".docx")
    assert "/" not in name
    assert ":" not in name
