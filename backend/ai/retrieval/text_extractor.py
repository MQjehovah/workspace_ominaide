import os


async def extract_text(file_path: str, mime_type: str | None = None) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    if ext in ('.txt', '.md', '.csv', '.json', '.xml', '.yaml', '.yml', '.ini', '.cfg', '.log'):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read(32000)
        except Exception:
            return ""

    if ext in ('.pdf', '.docx', '.xlsx', '.xlsm', '.pptx'):
        # Reuse the same extractors as knowledge-base import so semantic search
        # indexes real document text instead of just the filename.
        try:
            from plugins.notes.backend.importers import extract_document

            with open(file_path, 'rb') as f:
                data = f.read()
            _, text = extract_document(os.path.basename(file_path), data)
            return (text or "").strip()[:32000]
        except Exception:
            return os.path.basename(file_path)

    if ext in ('.doc', '.xls', '.ppt'):
        return os.path.basename(file_path)

    if ext in ('.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.scss', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.sh', '.bat', '.ps1'):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read(16000)
        except Exception:
            return ""

    return os.path.basename(file_path)


def extract_text_sync(file_path: str, mime_type: str | None = None) -> str:
    import asyncio
    return asyncio.run(extract_text(file_path, mime_type))
