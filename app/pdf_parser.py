import json
import logging
import base64
import anthropic
from app.config import settings

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Сен тиббий рецептларни таҳлил қиладиган ёрдамчисан.
Берилган PDF дан ФАҚАТ JSON қайтар — бошқа ҳеч нарса ёзма, markdown ҳам йўқ.

JSON структураси:
{
  "patient_name": "Бемор исми (топилмаса null)",
  "diagnosis": "Ташхис матни (топилмаса null)",
  "start_date": "КК.ОО.ЙЙЙЙ (топилмаса null)",
  "medications": [
    {
      "name": "Дори номи — айнан PDFдагидек",
      "dose": "Миқдор — айнан PDFдагидек",
      "note": "Изоҳ — айнан PDFдагидек",
      "time_slot": "morning|before_breakfast|breakfast|afternoon|before_dinner|dinner|evening|night|injection|im",
      "time_label": "Вақт тавсифи — айнан PDFдагидек",
      "start_day": 1,
      "end_day": 30
    }
  ],
  "daily_notes": ["Кундалик эслатма 1", "Кундалик эслатма 2"],
  "diet_note": "Парҳез тавсияси"
}

time_slot қийматлари:
- morning: бомдод, эрталаб (05:00-07:00)
- before_breakfast: нонушта олдин 30-60 дақиқа
- breakfast: нонушта вақтида
- afternoon: тушлик вақтида
- before_dinner: кечки овқат олдин
- dinner: кечки овқат вақтида
- evening: кечқурун овқатдан кейин (20:00 атрофида)
- night: ухлаш олдин
- injection: капельница
- im: мушак ичига укол

Қисқартмалар:
- "мах", "мах.", "махал", "маҳал" = марта/вақт (маҳал). Масалан: "1*1 мах" = кунига 1 марта 1 та; "2*3 мах" = 3 маҳал 2 тадан
- "овк", "овқ" = овқат
- "т.и" = томир ичига (капельница)
- "м.о" = мушак орқали укол
- "ч.к", "ч.қ" = чой қошиқ
- "ош қош", "ош.қош" = ош қошиқ
- "кн" = кейин
- "олд" = олдин

end_day ҳисоблаш: "1 ой"=30, "2 ой"=60, "3 ой"=90, "4 ой"=120, "5 ой"=150, "6 ой"=180, "1 йил"=365, "доимо"=9999
Агар аниқ кун кўрсатилган бўлса (масалан "1-2-3-кунлари"), end_day=охирги кун.

Дори номлари, дозалар, изоҳларни PDFдагидек айнан сақла — кириллча бўлса кириллча, русча бўлса русча, лотин бўлса лотин."""


async def parse_pdf_to_medications(pdf_bytes: bytes) -> dict:
    """PDF bytes ni Claude API ga yuborib dorilar ro'yxatini olish."""
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
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
                        "text": "Ушбу рецептдан барча дориларни ажратиб JSON қайтар.",
                    },
                ],
            }
        ],
    )

    raw = message.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    data = json.loads(raw)
    logger.info(f"PDF tahlil qilindi: {len(data.get('medications', []))} ta dori topildi")
    return data
