"""Prompt templates for AI synthesis."""

from __future__ import annotations

import json
from datetime import date

from my_diary.models import CollectorResult

_SYSTEM_PROMPT_TEMPLATE = """\
Jesteś osobistym skrybą{name_genitive} — tworzysz dzienną notatkę z {possessive} aktywności.

Zasady:
- Pisz po polsku
- NIGDY nie wymyślaj danych — bazuj wyłącznie na dostarczonych informacjach
- Łącz konteksty z różnych źródeł w spójną narrację
- Bądź zwięzły, ale konkretny
- Używaj czasu przeszłego
- Jeśli dane z jakiegoś źródła są puste, pomiń tę sekcję
- Action items powinny być konkretnymi zadaniami do zrobienia jutro

Zwróć odpowiedź jako JSON z następującymi polami:
- tldr: 2-3 zdania podsumowania dnia
- key_decisions: lista kluczowych decyzji i ustaleń (strings)
- development_narrative: narracja o pracy deweloperskiej (commity, MR-y, CI/CD)
- tasks_narrative: narracja o zadaniach (Linear — ukończone, w toku, nowe)
- communication_narrative: narracja o komunikacji (Slack — kluczowe dyskusje, ustalenia)
- meetings_narrative: narracja o spotkaniach (Calendar — lista, kontekst)
- documents_narrative: narracja o dokumentach (Notion, Google Drive)
- local_activity_narrative: narracja o lokalnej aktywności (git we wszystkich repo, pliki, terminal)
- action_items: lista konkretnych action items i follow-upów (strings)

Zwróć TYLKO valid JSON, bez markdown code blocks ani dodatkowego tekstu.\
"""


def build_prompt(
    collector_results: list[CollectorResult],
    target_date: date,
    user_name: str = "",
) -> str:
    """Build the full prompt for Claude CLI."""
    # Personalize prompt with user name
    if user_name:
        name_genitive = f" {user_name}"
        possessive = "jego"
        name_for = user_name
    else:
        name_genitive = ""
        possessive = "Twojej"
        name_for = "użytkownika"

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        name_genitive=name_genitive,
        possessive=possessive,
    )

    # Serialize collector data
    raw_data = {}
    for result in collector_results:
        if result.has_data:
            raw_data[result.source] = result.data

    weekday_names_pl = [
        "poniedziałek", "wtorek", "środa", "czwartek",
        "piątek", "sobota", "niedziela",
    ]
    weekday = weekday_names_pl[target_date.weekday()]

    user_prompt = f"""\
Data: {target_date.isoformat()} ({weekday})

Dane z collectorów:

{json.dumps(raw_data, ensure_ascii=False, indent=2, default=str)}

Na podstawie powyższych danych stwórz dzienną notatkę dla {name_for}.\
"""

    return f"{system_prompt}\n\n---\n\n{user_prompt}"
