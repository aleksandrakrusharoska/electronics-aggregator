"""Ad-specific chat assistant — an LLM grounded only in one ad's real data,
answering questions like "is this a good deal" or "what should I check"."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/api/ads/chat", tags=["chat"])

MAX_MESSAGES = 20       # cap conversation length per request (cost/latency guard)
MAX_MESSAGE_LEN = 500   # cap per-message length


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class AdContext(BaseModel):
    title: str | None = None
    description: str | None = None
    price_eur: float | None = None
    price_mkd: float | None = None
    condition: str | None = None
    brand: str | None = None
    model: str | None = None
    location: str | None = None
    seller_notes: str | None = None
    specs: dict | None = None
    reference_new_price_mkd: float | None = None
    price_vs_new_ratio: float | None = None
    good_price_deal: bool | None = None
    reference_source: str | None = None


class ChatRequest(BaseModel):
    ad: AdContext
    messages: list[ChatMessage]


def _build_system_prompt(ad: AdContext) -> str:
    facts = []
    if ad.title:
        facts.append(f"Наслов: {ad.title}")
    if ad.description:
        facts.append(f"Опис: {ad.description}")
    if ad.price_eur is not None:
        price_line = f"Цена: {ad.price_eur} EUR"
        if ad.price_mkd is not None:
            price_line += f" ({ad.price_mkd} МКД)"
        facts.append(price_line)
    if ad.condition:
        facts.append(f"Состојба: {ad.condition}")
    if ad.brand:
        facts.append(f"Бренд: {ad.brand}")
    if ad.model:
        facts.append(f"Модел: {ad.model}")
    if ad.location:
        facts.append(f"Локација: {ad.location}")
    if ad.seller_notes:
        facts.append(f"Забелешки од продавачот: {ad.seller_notes}")
    if ad.specs:
        facts.append(f"Спецификации: {ad.specs}")
    if ad.reference_new_price_mkd:
        src = "Setec.mk" if ad.reference_source == "setec" else "друг оглас за нов истиот модел"
        line = f"Споредбена цена на нов уред: {ad.reference_new_price_mkd} МКД (споредено со {src})."
        if ad.price_vs_new_ratio is not None:
            line += f" Овој оглас чини {round(ad.price_vs_new_ratio * 100)}% од таа цена."
        facts.append(line)

    facts_block = "\n".join(facts) if facts else "(нема дополнителни податоци)"

    return (
        "Ти си асистент кој им помага на корисниците на македонски маркетплејс за електроника "
        "да одлучат дали еден конкретен оглас е добра купувачка одлука.\n"
        "Одговарај САМО врз основа на податоците дадени подолу за овој оглас — "
        "никогаш не измислувај детали кои не се наведени таму.\n"
        "Ако немаш доволно информации за да одговориш на прашањето, кажи го тоа искрено, "
        "наместо да претпоставуваш.\n"
        "Одговарај кратко, јасно и на македонски јазик.\n\n"
        f"Податоци за огласот:\n{facts_block}"
    )


@router.post("")
def chat_about_ad(req: ChatRequest):
    settings = get_settings()
    if not settings.groq_api_key:
        raise HTTPException(status_code=503, detail="Chat-от не е достапен во моментов.")
    if not req.messages:
        raise HTTPException(status_code=400, detail="Нема порака.")
    if len(req.messages) > MAX_MESSAGES:
        raise HTTPException(status_code=400, detail="Премногу пораки во овој разговор.")
    for m in req.messages:
        if len(m.content) > MAX_MESSAGE_LEN:
            raise HTTPException(status_code=400, detail="Пораката е предолга.")

    from groq import Groq
    client = Groq(api_key=settings.groq_api_key)

    messages = [{"role": "system", "content": _build_system_prompt(req.ad)}]
    messages += [{"role": m.role, "content": m.content} for m in req.messages]

    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=0.3,
            max_tokens=400,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Грешка при повикување на AI асистентот.") from exc

    return {"reply": response.choices[0].message.content}
