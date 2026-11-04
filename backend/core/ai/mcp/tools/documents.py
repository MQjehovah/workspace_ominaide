"""Document generation tools: Word (.docx) and PowerPoint (.pptx).

These are capabilities of the default personal assistant, not separate Bots.
Generated files are stored in MinIO and registered in the Files plugin so they
show up in the normal file library with a download URL.
"""
import io
import re

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from pptx import Presentation
from pptx.util import Inches
from pptx.util import Pt as PPt

from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPTool

WORD_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPT_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


def _safe_filename(name: str, ext: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "-", (name or "").strip())
    name = name.strip(" .-") or "document"
    if not name.lower().endswith(ext):
        name += ext
    return name[:180]


def _setup_word(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.4)
    section.right_margin = Cm(2.4)
    style = doc.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.font.size = Pt(11)
    try:
        style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    except Exception:
        pass


def _add_table(doc: Document, lines: list[str]) -> None:
    rows: list[list[str]] = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        rows.append(cells)
    if not rows:
        return
    cols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=cols)
    table.style = "Table Grid"
    for r, row in enumerate(rows):
        for c in range(cols):
            table.cell(r, c).text = row[c] if c < len(row) else ""


def _add_markdown(doc: Document, content: str) -> None:
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        if stripped.startswith("|") and stripped.endswith("|"):
            block: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            _add_table(doc, block)
            continue

        if stripped.startswith("```"):
            i += 1
            code: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            p = doc.add_paragraph("\n".join(code))
            for run in p.runs:
                run.font.name = "Consolas"
                run.font.size = Pt(9)
            continue

        if not stripped:
            i += 1
            continue

        if stripped == "---":
            doc.add_page_break()
        elif stripped.startswith("### "):
            doc.add_heading(stripped[4:], level=3)
        elif stripped.startswith("## "):
            doc.add_heading(stripped[3:], level=2)
        elif stripped.startswith("# "):
            doc.add_heading(stripped[2:], level=1)
        elif stripped.startswith(("- ", "* ", "• ")):
            doc.add_paragraph(stripped[2:], style="List Bullet")
        elif re.match(r"^\d+\.\s+", stripped):
            doc.add_paragraph(re.sub(r"^\d+\.\s+", "", stripped), style="List Number")
        elif stripped.startswith("> "):
            p = doc.add_paragraph(stripped[2:])
            for run in p.runs:
                run.italic = True
        else:
            doc.add_paragraph(stripped)
        i += 1


def build_word_bytes(title: str, content: str) -> bytes:
    doc = Document()
    _setup_word(doc)
    doc.add_heading(title, level=0)

    lines = content.splitlines()
    if lines and lines[0].strip() == f"# {title}".strip():
        content = "\n".join(lines[1:])
    _add_markdown(doc, content)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _bullets(value) -> list[tuple[str, int]]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [x for x in value.splitlines() if x.strip()]
    out: list[tuple[str, int]] = []
    for item in value:
        if isinstance(item, dict):
            out.append((str(item.get("text") or item.get("title") or ""), int(item.get("level") or 0)))
        else:
            out.append((str(item), 0))
    return out


def build_pptx_bytes(
    title: str,
    slides: list,
    subtitle: str = "",
    closing: str | None = None,
) -> bytes:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    cover = prs.slides.add_slide(prs.slide_layouts[0])
    cover.shapes.title.text = title
    if subtitle and len(cover.placeholders) > 1:
        cover.placeholders[1].text = subtitle

    for item in slides or []:
        if isinstance(item, str):
            item = {"title": item, "bullets": []}
        layout = prs.slide_layouts[2] if item.get("layout") == "section" else prs.slide_layouts[1]
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = str(item.get("title") or "")
        if len(slide.placeholders) > 1:
            body = slide.placeholders[1].text_frame
            body.clear()
            for idx, (text, level) in enumerate(_bullets(item.get("bullets") or item.get("content"))):
                p = body.paragraphs[0] if idx == 0 else body.add_paragraph()
                p.text = text
                p.level = min(max(level, 0), 4)
                for run in p.runs:
                    run.font.size = PPt(18)
        notes = item.get("notes")
        if notes:
            slide.notes_slide.notes_text_frame.text = str(notes)

    if closing:
        end = prs.slides.add_slide(prs.slide_layouts[0])
        end.shapes.title.text = closing

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


async def create_word_document(user_id: int, args: dict) -> MCPCallResponse:
    title = (args.get("title") or "").strip()
    content = args.get("content") or ""
    if not title or not content.strip():
        return _err("title 和 content 必填")
    try:
        data = build_word_bytes(title, content)
        filename = _safe_filename(args.get("filename") or title, ".docx")

        from core.database.session import async_session
        from plugins.files.backend import service as files_service

        async with async_session() as db:
            file = await files_service.save_generated_file(
                db,
                user_id,
                filename,
                data,
                WORD_MIME,
                folder_path=args.get("folder") or "/",
                index_text=content,
            )
            await db.commit()
            url = await files_service.get_download_url(file)
            file_id = file.id
        return _ok(
            f"已生成 Word 文档《{filename}》。\n"
            f"文件 ID: {file_id}\n下载链接: {url or '（MinIO 未配置）'}"
        )
    except Exception as e:
        return _err(f"生成 Word 失败: {e}")


async def create_presentation(user_id: int, args: dict) -> MCPCallResponse:
    title = (args.get("title") or "").strip()
    slides = args.get("slides") or []
    if not title or not isinstance(slides, list) or not slides:
        return _err("title 和 slides 必填")
    try:
        subtitle = str(args.get("subtitle") or "")
        data = build_pptx_bytes(title, slides, subtitle=subtitle, closing=args.get("closing"))
        filename = _safe_filename(args.get("filename") or title, ".pptx")

        index_text = title + "\n" + "\n".join(
            str(s.get("title") if isinstance(s, dict) else s) for s in slides
        )

        from core.database.session import async_session
        from plugins.files.backend import service as files_service

        async with async_session() as db:
            file = await files_service.save_generated_file(
                db,
                user_id,
                filename,
                data,
                PPT_MIME,
                folder_path=args.get("folder") or "/",
                index_text=index_text,
            )
            await db.commit()
            url = await files_service.get_download_url(file)
            file_id = file.id
        return _ok(
            f"已生成 PPT《{filename}》，共 {len(slides) + 1} 页。\n"
            f"文件 ID: {file_id}\n下载链接: {url or '（MinIO 未配置）'}"
        )
    except Exception as e:
        return _err(f"生成 PPT 失败: {e}")


TOOLS = [
    (
        MCPTool(
            name="create_word_document",
            description=(
                "生成 Word 文档（.docx），保存到用户文件库并返回下载链接。"
                "content 支持 Markdown：#/##/### 标题、- 列表、1. 编号、"
                "| 表格 |、```代码块```、--- 分页。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "文档标题"},
                    "content": {"type": "string", "description": "文档正文，Markdown 风格"},
                    "filename": {"type": "string", "description": "可选文件名，默认用标题"},
                    "folder": {"type": "string", "description": "保存目录，默认 /"},
                },
                "required": ["title", "content"],
            },
        ),
        create_word_document,
    ),
    (
        MCPTool(
            name="create_presentation",
            description=(
                "生成 PowerPoint（.pptx），保存到用户文件库并返回下载链接。"
                "slides 是正文页数组，每页含 title、bullets、notes；可选 closing 结束页。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "演示文稿标题"},
                    "subtitle": {"type": "string", "description": "副标题"},
                    "slides": {
                        "type": "array",
                        "description": "正文页列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "bullets": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "notes": {"type": "string"},
                                "layout": {"type": "string", "enum": ["content", "section"]},
                            },
                        },
                    },
                    "closing": {"type": "string", "description": "可选结束页标题"},
                    "filename": {"type": "string", "description": "可选文件名，默认用标题"},
                    "folder": {"type": "string", "description": "保存目录，默认 /"},
                },
                "required": ["title", "slides"],
            },
        ),
        create_presentation,
    ),
]
