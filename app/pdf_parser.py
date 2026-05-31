import json
import logging
import base64
import anthropic
from app.config import settings

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Сен тиббий рецептларни таҳлил қиладиган ёрдамчисан.
Берилган PDF дан ФАҚАТ JSON қайтар — бошқа ҳеч нарса ёзма, markdown ҳам йўқ, изоҳ ҳам йўқ.

JSON структураси:
{
  "patient_name": "Бемор исми ёки null",
  "diagnosis": "Ташхис ёки null",
  "start_date": "КК.ОО.ЙЙЙЙ ёки null",
  "medications": [
    {
      "name": "Дори номи — айнан PDFдагидек",
      "dose": "Миқдор — айнан PDFдагидек",
      "note": "Изоҳ — айнан PDFдагидек",
      "time_slot": "morning|before_breakfast|breakfast|afternoon|before_dinner|dinner|evening|night|injection|im",
      "time_label": "Вақт тавсифи",
      "start_day": 1,
      "end_day": 30
    }
  ],
  "daily_notes": ["эслатма 1", "эслатма 2"],
  "diet_note": "парҳез ёки null"
}

Қисқартмалар:
- "мах", "мах.", "махал", "маҳал" = марта/вақт. "1*1 мах" = кунига 1 марта 1 та; "2*3 мах" = 3 маҳал 2 тадан
- "овк", "овқ" = овқат
- "т.и" = томир ичига (капельница → injection)
- "м.о" = мушак орқали укол (→ im)
- "ч.к", "ч.қ" = чой қошиқ
- "ош қош", "ош.қош" = ош қошиқ
- "кн" = кейин
- "олд" = олдин

МУҲИМ — КЎП МАҲАЛ ДОРИЛАР:
Агар дори 2 ёки 3 маҳал берилса, уни алоҳида объект сифатида ТАКРОРЛА ҳар маҳал учун:
- "2 мах" ёки "2*..." → 2 та алоҳида объект (нонушта + кечки овқат)
- "3 мах" ёки "3*..." → 3 та алоҳида объект (нонушта + тушлик + кечки овқат)
- "2*2 мах" → 2 та объект, ҳар бирида dose="2 та"
Масалан: "Lypo Gold 2*3 мах овқат вақтида" → 3 та объект: breakfast, afternoon, dinner

time_slot:
- morning: бомдод, эрталаб (05:00-07:00)
- before_breakfast: нонушта олдин 30-60 дақиқа
- breakfast: нонушта вақтида (07:30-08:00)
- afternoon: тушлик вақтида (13:00)
- before_dinner: кечки овқат олдин (17:00-18:00)
- dinner: кечки овқат вақтида (19:00)
- evening: кечқурун овқатдан кейин (20:00)
- night: ухлаш олдин (21:00+)
- injection: капельница
- im: мушак ичига укол

end_day: "1 ой"=30, "2 ой"=60, "3 ой"=90, "4 ой"=120, "5 ой"=150, "6 ой"=180, "1 йил"=365, "доимо"=9999
Аниқ кунлар берилса (масалан "1-2-3-кунлари") end_day=охирги кун рақами.

МУҲИМ: JSON тўлиқ бўлиши шарт — охирги } ёпилган бўлсин."""


def _try_parse_json(raw: str) -> dict:
    """JSON ni parse qilishga harakat, agar kesilgan bo'lsa tuzatishga urinish."""
    raw = raw.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Kesilgan JSON ni tuzatishga urinish — oxiridan yopamiz
        fixed = raw
        # Ochiq string ni yopish
        open_strings = fixed.count('"') % 2
        if open_strings:
            fixed += '"'
        # Ochiq obyektlar va massivlarni yopish
        stack = []
        for ch in fixed:
            if ch in "{[":
                stack.append(ch)
            elif ch == "}" and stack and stack[-1] == "{":
                stack.pop()
            elif ch == "]" and stack and stack[-1] == "[":
                stack.pop()
        while stack:
            fixed += "}" if stack.pop() == "{" else "]"
        return json.loads(fixed)


async def parse_pdf_to_medications(pdf_bytes: bytes) -> dict:
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    for attempt in range(2):
        try:
            message = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": "Ушбу рецептдан барча дориларни ажратиб тўлиқ JSON қайтар. JSON охири } билан ёпилган бўлсин.",
                            },
                        ],
                    }
                ],
            )

            raw = message.content[0].text
            data = _try_parse_json(raw)
            meds_count = len(data.get("medications", []))
            logger.info(f"PDF tahlil qilindi (urinish {attempt+1}): {meds_count} ta dori")
            return data

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Urinish {attempt+1} xatosi: {e}")
            if attempt == 1:
                raise

    return {}
