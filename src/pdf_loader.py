from typing import List, Dict
import re
from pypdf import PdfReader


def extract_pdf_text_chunks(
    pdf_path: str,
    chunk_size: int = 1500,
    overlap: int = 200,
) -> List[Dict[str, str]]:
    reader = PdfReader(pdf_path)
    chunks: List[Dict[str, str]] = []
    chunk_index = 0

    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = text.replace("\u0000", " ").strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end]
            chunks.append(
                {
                    "text": chunk_text,
                    "page": str(page_index),
                    "chunk_index": str(chunk_index),
                }
            )
            chunk_index += 1
            if end == len(text):
                break
            start = max(0, end - overlap)
    return chunks


FINANCIAL_KEYWORDS = [
    "Consolidated Statements of Operations",
    "Consolidated Statements of Income",
    "Consolidated Balance Sheets",
    "Consolidated Statements of Financial Position",
    "Consolidated Statements of Cash Flows",
    "Balance Sheets",
    "Cash Flows",
    "Revenue",
    "Net income",
    "Total assets",
    "Total liabilities",
    "Shareholders' equity",
    "Gross margin",
    "Operating income",
    "Operating activities",
    "Investing activities",
    "Financing activities",
    "Cash used in financing activities",
    "Depreciation and amortization",
    "Term debt",
]


REVENUE_KEYWORDS = [
    "Net sales by",
    "Net sales",
    "Revenue by",
    "Revenue",
    "Products and Services",
    "Segment",
    "Geographic",
    "Sales by",
]


CONTEXT_KEYWORDS = [
    "Item 1. Business",
    "Item 1A. Risk Factors",
    "Item 7. Management",
    "Business",
    "Risk Factors",
    "Management's Discussion",
    "Company Overview",
    "Segments",
    "Products and Services",
]


def extract_financial_statement_text(chunks: List[Dict[str, str]], max_chars: int = 16000) -> str:
    scored = []
    for idx, chunk in enumerate(chunks):
        text = chunk.get("text", "")
        score = _score_financial_chunk(text)
        if score > 0:
            chunk_idx = int(chunk.get("chunk_index", idx))
            scored.append((score, chunk_idx, text))
    scored.sort(key=lambda x: x[0], reverse=True)

    priority_keywords = [
        "financing activities",
        "cash used in financing activities",
        "cash provided by financing activities",
        "ending balances",
        "total shareholders",
        "term debt",
    ]
    priority = [
        (score, chunk_idx, text)
        for score, chunk_idx, text in scored
        if any(keyword in text.lower() for keyword in priority_keywords)
    ]

    # Prioritize chunks with key summary lines, then backfill with high-score chunks.
    ordered = priority + scored
    seen = set()
    selected = []
    total = 0
    for _, chunk_idx, text in ordered:
        if total >= max_chars:
            break
        if chunk_idx in seen:
            continue
        seen.add(chunk_idx)
        selected.append((chunk_idx, text))
        total += len(text)
    selected.sort(key=lambda x: x[0])
    return "\n".join(text for _, text in selected)


def extract_revenue_context(chunks: List[Dict[str, str]], max_chars: int = 6000) -> str:
    scored = []
    for chunk in chunks:
        text = chunk.get("text", "")
        score = _score_revenue_chunk(text)
        if score > 0:
            scored.append((score, text))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = []
    total = 0
    for _, text in scored[:20]:
        if total >= max_chars:
            break
        selected.append(text)
        total += len(text)
    return "\n".join(selected)


def extract_context_text(chunks: List[Dict[str, str]], max_chars: int = 8000) -> str:
    scored = []
    for chunk in chunks:
        text = chunk.get("text", "")
        score = _score_context_chunk(text)
        if score > 0:
            scored.append((score, text))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = []
    total = 0
    for _, text in scored[:20]:
        if total >= max_chars:
            break
        selected.append(text)
        total += len(text)
    return "\n".join(selected)


def score_financial_text(text: str) -> int:
    return _score_financial_chunk(text)


def score_revenue_text(text: str) -> int:
    return _score_revenue_chunk(text)


def score_context_text(text: str) -> int:
    return _score_context_chunk(text)


def _score_financial_chunk(text: str) -> int:
    if not text:
        return 0
    lower_text = text.lower()
    keyword_hits = sum(1 for kw in FINANCIAL_KEYWORDS if kw.lower() in lower_text)
    number_hits = len(re.findall(r"\b\d[\d,]*\.?\d*\b", text))
    table_lines = sum(1 for line in text.splitlines() if len(re.findall(r"\d", line)) >= 6)
    return keyword_hits * 6 + min(number_hits, 50) + table_lines * 4


def _score_revenue_chunk(text: str) -> int:
    if not text:
        return 0
    lower_text = text.lower()
    keyword_hits = sum(1 for kw in REVENUE_KEYWORDS if kw.lower() in lower_text)
    number_hits = len(re.findall(r"\b\d[\d,]*\.?\d*\b", text))
    return keyword_hits * 6 + min(number_hits, 80)


def _score_context_chunk(text: str) -> int:
    if not text:
        return 0
    lower_text = text.lower()
    keyword_hits = sum(1 for kw in CONTEXT_KEYWORDS if kw.lower() in lower_text)
    return keyword_hits * 10 + min(len(text) // 200, 20)


def extract_company_name(text: str) -> str:
    if not text:
        return ""
    head = text[:8000]
    lines = [line.strip() for line in head.splitlines() if line.strip()]
    for idx, line in enumerate(lines):
        if "exact name of registrant" in line.lower():
            for back in range(idx - 1, max(idx - 5, -1), -1):
                candidate = lines[back].strip()
                if _is_company_candidate(candidate):
                    return candidate
    for idx, line in enumerate(lines):
        if "form 10-k" in line.lower():
            for forward in range(idx + 1, min(idx + 6, len(lines))):
                candidate = lines[forward].strip()
                if _is_company_candidate(candidate):
                    return candidate
    match = re.search(
        r"\b[A-Z][A-Za-z&.,\s]{2,80}\b(?:Inc\.|Corporation|Corp\.|Limited|Ltd\.|LLC)\b",
        head,
    )
    if match:
        return match.group(0).strip()
    return ""


def _is_company_candidate(value: str) -> bool:
    if not value:
        return False
    lowered = value.lower()
    if "commission" in lowered or "file number" in lowered or "form 10-k" in lowered:
        return False
    if len(value) < 2 or len(value) > 80:
        return False
    return any(suffix in value for suffix in ["Inc", "INC", "Corp", "Corporation", "Ltd", "LLC"])
