"""PDF tahlil qiluvchining xato ishlovi uchun testlar."""
import asyncio
import json
from unittest.mock import AsyncMock, patch

import anthropic
import httpx
import pytest

from app.pdf_parser import (
    MAX_ATTEMPTS,
    ParserUnavailableError,
    PdfParseError,
    _try_parse_json,
    parse_pdf_to_medications,
)


def _status_error(code: int) -> anthropic.APIStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(code, request=request, json={"error": {"message": "x"}})
    return anthropic.APIStatusError("xato", response=response, body=None)


def _run(coro):
    return asyncio.run(coro)


# ── Qayta urinish siyosati ────────────────────────────────────────────────────

def test_org_disabled_is_not_retried():
    """Regressiya: 'This organization has been disabled' (400) da bot
    ikki marta urinardi — bu behuda, javob aynan o'sha qaytadi."""
    calls = []

    def boom(_):
        calls.append(1)
        raise _status_error(400)

    with patch("app.pdf_parser._call_claude", side_effect=boom):
        with pytest.raises(ParserUnavailableError):
            _run(parse_pdf_to_medications(b"%PDF-1.4"))

    assert len(calls) == 1, "400 da faqat bitta urinish bo'lishi kerak"


@pytest.mark.parametrize("code", [400, 401, 403, 404, 413, 422])
def test_fatal_codes_raise_unavailable(code):
    with patch("app.pdf_parser._call_claude", side_effect=_status_error(code)):
        with pytest.raises(ParserUnavailableError):
            _run(parse_pdf_to_medications(b"%PDF"))


@pytest.mark.parametrize("code", [429, 500, 503, 529])
def test_transient_codes_are_retried(code):
    calls = []

    def boom(_):
        calls.append(1)
        raise _status_error(code)

    with patch("app.pdf_parser._call_claude", side_effect=boom), \
         patch("app.pdf_parser.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(PdfParseError):
            _run(parse_pdf_to_medications(b"%PDF"))

    assert len(calls) == MAX_ATTEMPTS


def test_unavailable_is_a_parse_error():
    """handlers.py umumiy except bloki ham уни ушлай олсин."""
    assert issubclass(ParserUnavailableError, PdfParseError)


# ── Muvaffaqiyatli holat ──────────────────────────────────────────────────────

def test_returns_data_on_success():
    payload = json.dumps({"medications": [{"name": "Aspirin", "dose": "1 ta"}]})
    with patch("app.pdf_parser._call_claude", return_value=payload):
        data = _run(parse_pdf_to_medications(b"%PDF"))
    assert len(data["medications"]) == 1


def test_retries_after_bad_json_then_succeeds():
    good = json.dumps({"medications": []})
    responses = iter(["{buzuq", good])

    with patch("app.pdf_parser._call_claude", side_effect=lambda _: next(responses)), \
         patch("app.pdf_parser.asyncio.sleep", new_callable=AsyncMock):
        data = _run(parse_pdf_to_medications(b"%PDF"))

    assert data == {"medications": []}


# ── Kesilgan JSON ni tiklash ──────────────────────────────────────────────────

def test_repairs_truncated_json():
    truncated = '{"medications": [{"name": "Aspirin"'
    assert _try_parse_json(truncated)["medications"][0]["name"] == "Aspirin"


def test_strips_markdown_fences():
    fenced = '```json\n{"medications": []}\n```'
    assert _try_parse_json(fenced) == {"medications": []}
