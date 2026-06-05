"""공용 유틸: 텍스트 평문화, 청킹, 프로젝트 루트 sys.path 보정."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

_ROOT = Path(__file__).resolve().parent


def ensure_root_on_path() -> None:
    """서브패키지(ingest/retrieval/...)에서 루트 모듈을 import 할 수 있게 한다."""
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t ]+")
_MULTINL_RE = re.compile(r"\n{3,}")


def normalize_text(raw: str) -> str:
    """XML/HTML 태그 제거 및 공백 정규화(평문화)."""
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = text.replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _MULTINL_RE.sub("\n\n", text)
    # 표/구분선 잔여 기호 정리
    text = re.sub(r"[│┃|]{1,}", " ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> List[str]:
    """문자 단위 슬라이딩 윈도우 청킹(overlap 포함)."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: List[str] = []
    step = max(1, size - overlap)
    for start in range(0, len(text), step):
        chunk = text[start : start + size].strip()
        if chunk:
            chunks.append(chunk)
        if start + size >= len(text):
            break
    return chunks


def chunk_by_h2(markdown: str) -> List[dict]:
    """마크다운을 ## (H2) 섹션 단위로 분할. 각 섹션의 제목을 section 메타로 보존."""
    sections: List[dict] = []
    current_title = "intro"
    current_lines: List[str] = []

    def flush():
        body = "\n".join(current_lines).strip()
        if body:
            sections.append({"section": current_title, "text": f"## {current_title}\n{body}"
                             if current_title != "intro" else body})

    for line in markdown.splitlines():
        if line.startswith("## "):
            flush()
            current_title = line[3:].strip()
            current_lines = []
        elif line.startswith("# "):
            continue  # 최상위 제목은 건너뜀
        else:
            current_lines.append(line)
    flush()
    return sections
