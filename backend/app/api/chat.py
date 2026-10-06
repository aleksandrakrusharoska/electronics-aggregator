"""Ad-specific chat assistant — an LLM grounded only in one ad's real data,
answering questions like "is this a good deal" or "what should I check"."""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/api/ads/chat", tags=["chat"])
log = logging.getLogger(__name__)

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


# The parser stores conditions in English; the model otherwise quotes them
# as-is ("Used – Like New") in an otherwise Macedonian answer.
CONDITION_LABELS = {
    "New": "нов",
    "Used - Like New": "користен, како нов",
    "Used - Good": "користен, добра состојба",
    "Used - Fair": "користен, солидна состојба",
    "Used": "користен",
    "For parts": "за делови",
}


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
        facts.append(f"Состојба: {CONDITION_LABELS.get(ad.condition, ad.condition)}")
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
        src = {
            "store": "цена во македонски продавници",
            "marketplace": "медијана на огласи за нов истиот модел",
            "llm_estimate": "AI-проценка на цената на нов уред",
        }.get(ad.reference_source, "споредбена цена")
        line = f"Споредбена цена на нов уред: {ad.reference_new_price_mkd} МКД (извор: {src})."
        if ad.price_vs_new_ratio is not None:
            line += f" Овој оглас чини {round(ad.price_vs_new_ratio * 100)}% од таа цена."
        facts.append(line)
    if ad.good_price_deal:
        facts.append("Оценка на платформата: добра цена.")
    elif ad.price_vs_new_ratio is not None and ad.price_vs_new_ratio > 1:
        facts.append("Оценка на платформата: поскапо од нов уред.")

    facts_block = "\n".join(facts) if facts else "(нема дополнителни податоци)"

    return (
        "Ти си асистент на македонски сајт за огласи за електроника. Му помагаш на корисникот "
        "да одлучи за еден конкретен оглас, чии податоци се дадени подолу.\n\n"
        "Како одговараш:\n"
        "- Прво одговори директно на прашањето, во првата реченица. Потоа најмногу 2–4 кратки "
        "реченици образложение. Вкупно до околу 80 зборови.\n"
        "- Обичен текст, без markdown: без ѕвездички, наслови и табели. Ако набројуваш, "
        "најмногу три кратки ставки со „-“.\n"
        "- Обраќај се учтиво, со „Вие“, на правилен македонски јазик.\n"
        "- Не повторувај што веќе си кажал во разговорот и не ги препишувај сите податоци "
        "од огласот — спомни го само она што е важно за прашањето.\n\n"
        "Што смееш да тврдиш:\n"
        "- За конкретниот уред (состојба, додатоци, гаранција, дефекти) само она што пишува во "
        "огласот. Кога се повикуваш на огласот, кажи го природно („во огласот пишува…“). "
        "Ако нешто не е наведено, кажи дека не е наведено и предложи да се праша продавачот.\n"
        "- Општо знаење за моделот (познати проблеми, што да се провери, за кого е соодветен) "
        "смееш да користиш, но претстави го како општо, не како дел од огласот.\n"
        "- За цената користи ги само бројките подолу (споредбената цена и оценката на "
        "платформата). Не измислувај цени на половниот пазар или распони на цени. "
        "Споредбената цена е приближна (на пр. медијана од неколку продавници) — "
        "кажи го тоа ако одлуката зависи од неа.\n"
        "- Техничките детали од описот пренеси ги неутрално; не ги оценувај како добри или "
        "лоши, освен ако продавачот самиот така ги претставил.\n"
        "- На прашања што не се за огласот (на пр. споредба на марки) одговори кратко и "
        "општо, без да тврдиш дека едната е подобра за секого.\n\n"
        f"Податоци за огласот:\n{facts_block}"
    )


def _trim_to_sentence(text: str) -> str:
    """When the token cap still cuts an answer off, drop the half sentence
    at the end rather than showing it ("…Цената од")."""
    text = text.strip()
    cut = max(text.rfind(c) for c in ".!?")
    return text[:cut + 1] if cut > len(text) // 2 else text + "…"


def _call_groq(settings, messages: list[dict]) -> str:
    from groq import Groq
    # Without an explicit timeout, a slow/unresponsive Groq API leaves the
    # request (and the browser tab awaiting it) hanging indefinitely.
    client = Groq(api_key=settings.chat_groq_api_key, timeout=15.0)
    response = client.chat.completions.create(
        model=settings.chat_groq_model,
        messages=messages,
        temperature=0.3,
        # gpt-oss reasons before answering and those tokens count against
        # max_tokens too; with 400 and default effort, answers were cut off
        # mid-sentence. Low effort keeps the reasoning short.
        reasoning_effort="low",
        max_tokens=1500,
    )
    choice = response.choices[0]
    text = choice.message.content or ""
    if not text.strip():
        raise RuntimeError(f"empty reply (finish_reason={choice.finish_reason})")
    return _trim_to_sentence(text) if choice.finish_reason == "length" else text.strip()


def _call_mistral(settings, messages: list[dict]) -> str:
    from mistralai.client import Mistral
    client = Mistral(api_key=settings.chat_mistral_api_key, timeout_ms=15_000)
    response = client.chat.complete(
        model=settings.mistral_model,
        messages=messages,
        temperature=0.3,
        max_tokens=600,
    )
    choice = response.choices[0]
    text = choice.message.content or ""
    return _trim_to_sentence(text) if choice.finish_reason == "length" else text.strip()


@router.post("")
def chat_about_ad(req: ChatRequest):
    settings = get_settings()
    # Two independent providers, tried in order, so one outage/exhausted
    # quota doesn't take live chat down — see chat_mistral_api_key in config.
    providers = [
        (name, key, fn)
        for name, key, fn in [
            ("Groq", settings.chat_groq_api_key, _call_groq),
            ("Mistral", settings.chat_mistral_api_key, _call_mistral),
        ]
        if key
    ]
    if not providers:
        raise HTTPException(status_code=503, detail="Chat-от не е достапен во моментов.")
    if not req.messages:
        raise HTTPException(status_code=400, detail="Нема порака.")
    if len(req.messages) > MAX_MESSAGES:
        raise HTTPException(status_code=400, detail="Премногу пораки во овој разговор.")
    for m in req.messages:
        if len(m.content) > MAX_MESSAGE_LEN:
            raise HTTPException(status_code=400, detail="Пораката е предолга.")

    messages = [{"role": "system", "content": _build_system_prompt(req.ad)}]
    messages += [{"role": m.role, "content": m.content} for m in req.messages]

    last_exc = None
    for name, _key, call in providers:
        try:
            return {"reply": call(settings, messages)}
        except Exception as exc:
            log.warning("%s chat call failed, trying next provider: %s", name, exc)
            last_exc = exc

    log.exception("All chat providers failed", exc_info=last_exc)
    raise HTTPException(status_code=502, detail="Грешка при повикување на AI асистентот.") from last_exc
