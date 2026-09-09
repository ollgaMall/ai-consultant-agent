# ТЗ ОТ АНАЛИТИКА (Perplexity) — TASK-000: AI Opportunity and Implementation Consultant

**Версия:** v1.2 (Final)
**Дата:** 2026-09-07
**Статус:** ✅ Утверждено владельцем продукта, готово к передаче Claude-Оркестратору

---

## 1. Бизнес-цель

Создать MVP системы бизнес-диагностики, которая на основе входных материалов клиента (файлы, аудио, структурированные данные) автоматически формирует книгу диагностики с рекомендациями по внедрению AI-агентов, сокращая время консультанта на подготовку отчёта и обеспечивая качество анализа на уровне консалтинговых практик (McKinsey: MECE, Pyramid Principle, hypothesis-driven).

---

## 2. Стейкхолдеры (RACI)

| Роль | R (Responsible) | A (Accountable) | C (Consulted) | I (Informed) |
|---|---|---|---|---|
| Владелец продукта / Консультант | ✅ | ✅ | — | — |
| Собственник бизнеса (клиент) | — | — | ✅ | ✅ |
| Разработчики AI-агентов (следующий этап) | — | — | ✅ | ✅ |
| Будущие пользователи системы (консультанты) | — | — | ✅ | ✅ |

---

## 3. Референсы мировых практик (минимум 5)

1. **McKinsey & Company — Problem Solving Framework** (MECE, Pyramid Principle, Hypothesis-Driven Approach). Используется как методологическая рамка анализа: структурирование проблем, приоритизация, синтез выводов. [1]
2. **BCG — AI in Business: From Hype to Value** (2024–2025). Практики выявления AI-возможностей: критерии отбора процессов (повторяемость, объём данных, объяснимость), оценка зрелости, quick wins vs трансформация. [2]
3. **Accenture — AI Maturity Model** (2023–2024). Шкала зрелости AI-экосистемы (0–5), компоненты: оркестрация, память, governance, комплаенс, измеримость. [3]
4. **Deloitte — State of AI in the Enterprise** (2024). Классификация AI-решений: детерминированный код, LLM-агенты, гибрид, человек+AI; критерии выбора типа реализации. [4]
5. **IIBA — BABOK v3** (Business Analysis Body of Knowledge). Техники elicitation (interview, document analysis), структурирование требований, работа с неопределённостью, traceability. [5]
6. **ISO/IEC 25010:2011** — Systems and software engineering — Software product Quality Requirements and Evaluation (SQuaRE). Используется как рамка для нефункциональных требований. [6]
7. **Gartner — Top Strategic Technology Trends for 2025: AI Agents** (2024). Практики внедрения AI-агентов, критерии готовности процессов, риски. [7]
8. **Yandex Cloud — SpeechKit Free Tier** (2026). Бесплатный уровень для транскрипции: 100 000 сообщений/мес, поддержка русского языка, API. [8][11][14][18]
9. **OpenAI Whisper — Open-Source Model** (2026). Локальная транскрипция без ограничений, поддержка русского языка, бесплатное использование (self-hosted). [12][17][22][24][27][28][32]
10. **Sber GigaAM — Open-Source Russian STT** (2026). Российская модель, точность выше Whisper на русском, бесплатное self-hosted использование. [12][16][21]
11. **Draw.io — CSV/XML Import Format** (2026). Поддержка импорта CSV (иерархический формат) и XML (нативный draw.io) для построения flowchart/org chart. [25][26][29][31][33][36][37]
12. **Telegram Bot Lead Qualification Best Practices** (2026). 3–5 вопросов для квалификации: отрасль, размер, боль, бюджет, timeline; сценарий: приветствие → вопросы по одному → предложение ценности → handoff. [30][35][38][39][40][41][42][43][44]

---

## 4. Требования

| ID | Epic | User Story (As a / I want / So that) | Acceptance Criteria (Given/When/Then) | Приоритет (MoSCoW) |
|---|---|---|---|---|
| REQ-01 | Вход данных | As a консультант, I want to upload client materials (files, audio, text), so that the system can start diagnostics. | Given the consultant uploads 3–4 files (DOC/DOCX, TXT, MD, XLS/XLSX, audio), When the upload is complete, Then the system registers all materials in a manifest and stores originals unchanged in a separate folder. | Must have |
| REQ-02 | Структура папок | As a consultant, I want the system to automatically create a folder structure per client, so that materials are organised consistently. | Given a new client project is created, When the system initialises, Then it creates folders: 01-transcripts/, 02-product/, 03-analysis/, 04-deliverables/, 05-client-materials/ with subfolders as per high-level spec. | Must have |
| REQ-03 | Реестр материалов | As a consultant, I want an auto-generated manifest.md, so that I can track all incoming materials. | Given materials are uploaded, When the system processes them, Then manifest.md lists each file with path, type, batch ID, and brief description. | Must have |
| REQ-04 | Анкеты для сотрудников | As a consultant, I want the system to generate questionnaires per department + one for the executive, so that I can collect employee input. | Given the system receives the list of departments, When it generates questionnaires, Then it produces one text questionnaire per department + one for the executive, editable by the consultant (comments only, no structure change). | Must have |
| REQ-05 | Обработка аудио | As a consultant, I want the system to transcribe audio and create a digest per employee, so that I don't have to do it manually. | Given audio files are uploaded, When the system processes them, Then it produces: (1) raw transcript stored separately, (2) edited semantic version, (3) digest with fields: role, processes, tools, pains, metrics/volumes, ASR uncertainties. | Must have |
| REQ-05.1 | Транскрипция (инструмент) | As a system architect, I want to use a free speech-to-text API with good Russian support, so that transcription costs are zero in MVP. | Given the system needs to transcribe Russian audio, When it selects a tool, Then it uses one of: Yandex SpeechKit free tier (100k msgs/mo), Whisper local (self-hosted), GigaAM (self-hosted), mymeet.ai (180 min/mo free), TurboScribe (3 files/day free) — all with open API or self-hosted, no paid subscription. | Must have |
| REQ-06 | Контроль полноты | As a consultant, I want the system to identify missing information, so that I can decide whether to proceed. | Given all materials are uploaded, When the system analyses completeness, Then it displays a list of gaps and asks "Proceed to analysis?" with Yes/No + option to add more info. | Must have |
| REQ-07 | Анализ процессов | As a consultant, I want the system to identify and list all business processes, so that I can see automation candidates. | Given transcripts, digests, and documents are available, When the system runs process analysis, Then it produces a list of processes with: department, frequency, time volume, inputs, outputs, pain points. | Must have |
| REQ-08 | Критерии автоматизации | As a consultant, I want the system to score processes for automation potential, so that I can prioritise. | Given the process list, When the system evaluates each process, Then it applies criteria: repeatability, data availability, explainability, time volume, error cost (from research) and outputs a score/priority. | Must have |
| REQ-09 | Классификация реализации | As a consultant, I want the system to classify each automation candidate as: code / agent / hybrid / human+AI, so that developers know the approach. | Given the automation candidates, When the system classifies them, Then each candidate is tagged with one of four types based on process characteristics. | Must have |
| REQ-10 | Маркировка утверждений | As a consultant, I want every statement in the report to be marked as FACT / CONCLUSION / HYPOTHESIS / ASSUMPTION, so that uncertainty is explicit. | Given the analysis is complete, When the system generates the report, Then each claim is prefixed with [ФАКТ], [ВЫВОД], [ГИПОТЕЗА], or [ПРЕДПОЛОЖЕНИЕ]. | Must have |
| REQ-11 | Чек-лист зрелости | As a consultant, I want the system to assess AI maturity using a 0–5 scale, so that the client sees their current state. | Given the process and automation analysis, When the system evaluates maturity, Then it outputs an overall maturity score (0–5) per ecosystem (not per department) with justification. | Must have |
| REQ-12 | AS-IS / TO-BE | As a client, I want to see the difference between current state (AS-IS) and target state (TO-BE), so that I understand the transformation. | Given the analysis is complete, When the system generates the report, Then it includes side-by-side AS-IS and TO-BE descriptions with clear delta. | Must have |
| REQ-13 | Карта процессов | As a consultant, I want a process map table, so that I can see all processes with priorities. | Given the process list, When the system generates the map, Then it produces a table with columns: process \| department \| frequency \| time volume \| automation potential \| implementation type \| priority. | Must have |
| REQ-13.1 | Экспорт для Draw.io | As a developer, I want to export processes in CSV format compatible with draw.io, so that I can create BPMN-like diagrams without re-entering data. | Given the process map is generated, When the consultant exports, Then the system outputs CSV with columns: id, parent, label (process name), department, inputs, outputs, executor, frequency, tools — compatible with draw.io Arrange → Insert → Advanced → CSV import. | Must have |
| REQ-14 | Дорожная карта | As a client, I want a high-level implementation roadmap, so that I understand the steps and timeline. | Given the automation candidates, When the system generates the roadmap, Then it outputs 3–5 high-level phases with estimated timeline and resources. | Must have |
| REQ-15 | ROI-раздел | As a client, I want to see estimated ROI (time savings, FTE, revenue impact), so that I can evaluate the investment. | Given the process analysis, When the system calculates ROI, Then it outputs estimates with explicit uncertainty ranges (e.g., "~65–175 hours/month, ~2–6M RUB/year"). | Must have |
| REQ-16 | Форматы отчёта | As a consultant, I want the final report in multiple formats (web, PDF, DOC, MD), so that I can share with client and developers. | Given the report is generated, When the consultant exports, Then the system provides: (1) static HTML (open in browser + download), (2) PDF for client, (3) DOC for developers/consultant, (4) MD for internal use. | Must have |
| REQ-17 | Две версии отчёта | As a consultant, I want two report versions (executive for client, detailed for developers), so that each audience gets relevant content. | Given the report is generated, When the consultant exports, Then the executive version (HTML/PDF) is ~20 pages, and the detailed version (DOC) includes technical details for developers. | Must have |
| REQ-18 | Накопление эталона | As a consultant, I want the system to accumulate learnings from each client, so that the maturity model and process library improve over time. | Given multiple client projects are completed, When the system stores confirmed hypotheses and process patterns, Then it builds a reusable library of industry processes and maturity benchmarks (architecture decision by Claude: free tool, e.g., JSON library, vector DB, or knowledge base). | Must have |
| REQ-19 | Telegram-бот (MVP) | As a potential client, I want to interact with a Telegram bot for pre-qualification, so that I can quickly understand if the system fits my needs. | Given a user messages the bot, When the bot asks 3 questions (industry/niche, company size/employees, main pain/automation goal), Then it outputs a brief value proposition and next steps, and integrates with the main system to create a preliminary client project. | Should have |
| REQ-20 | Валидация гипотез | As a consultant, I want to track which hypotheses the client confirmed/rejected, so that I can refine the maturity model. | Given the client reviews the report, When they provide feedback, Then the system records confirmed/rejected hypotheses and updates the internal knowledge base. | Should have |

---

## 5. Нефункциональные требования

| Категория (ISO 25010) | Требование | Метрика |
|---|---|---|
| Функциональная пригодность (Functional Suitability) | Система должна покрывать все этапы: загрузка → регистрация → анкеты → транскрипция → анализ → отчёт. | 100% coverage of REQ-01 to REQ-20 in MVP. |
| Производительность (Performance Efficiency) | Транскрипция аудио должна завершаться в разумное время. | < 5 минут на 15 минут аудио (при использовании бесплатных инструментов: Yandex SpeechKit, Whisper, GigaAM). |
| Совместимость (Compatibility) | Система должна принимать файлы форматов: DOC/DOCX, TXT, MD, XLS/XLSX, аудио (без ограничений по форматам в MVP). | Successful upload and processing of all listed formats. |
| Надёжность (Reliability) | Система должна сохранять оригиналы файлов неизменными. | 100% of original files preserved without modification. |
| Безопасность (Security) | Система должна позволять масштабирование на обработку ПДн (маскирование), но в MVP обработка ПДн не требуется. | Architecture supports future PII masking; no PII processing in MVP. |
| Сопровождаемость (Maintainability) | Код и архитектура должны позволять добавлять новые форматы, модули анализа, интеграции. | Modular architecture with clear separation of concerns. |
| Переносимость (Portability) | Система должна работать на бесплатных инструментах (без платных API). | 100% of components use free-tier tools/APIs or self-hosted open-source. |
| Удобство использования (Usability) | Консультант должен понимать, какие данные не хватает, и принимать решение о продолжении. | System displays gaps and asks "Proceed?" before analysis. |
| Интероперабельность (Interoperability) | Система должна экспортировать процессы в формате для Draw.io (CSV). | CSV export with required fields compatible with draw.io import (Arrange → Insert → Advanced → CSV). |

---

## 6. Риски и допущения

| Риск/Допущение | Вероятность | Влияние | Митигация |
|---|---|---|---|
| Недостаточное качество AI-анализа (ключевой риск) | Высокая | Высокое | Глубокая проработка аналитической логики; явная маркировка гипотез; валидация через клиента; накопление эталона |
| Ограничения бесплатного тарифа Yandex SpeechKit | Средняя | Среднее | Использовать альтернативы: Whisper локально, GigaAM, mymeet.ai (180 мин/мес), TurboScribe (3 файла/день) |
| Сложность интеграции Telegram-бота с основной системой | Средняя | Среднее | Архитектура с единым API, бот вызывает те же endpoints, что и веб-интерфейс |
| Отсутствие реальных данных для тестирования на старте | Средняя | Среднее | Использовать анонимизированные примеры из прошлых проектов; создать синтетические тестовые данные |
| Сопротивление консультантов новому инструменту | Средняя | Среднее | Вовлечь консультантов в дизайн; обеспечить возможность ручных правок; показать выгоду (меньше правок, быстрее отчёт) |
| Несоответствие отчёта лучшим практикам | Средняя | Высокое | Research мировых практик на этапе проектирования; явные референсы в ТЗ; валидация через клиента |

---

## 7. Открытые вопросы к пользователю

**Нет открытых вопросов.** Все уточнения получены и зафиксированы в ТЗ.

---

## ДЕЛЬТА ИЗМЕНЕНИЙ (относительно предыдущего снапшота v1.1)

- **ADDED:** REQ-13.1 (Экспорт для Draw.io — CSV формат с полями: id, parent, label, department, inputs, outputs, executor, frequency, tools).
- **ADDED:** Детализация REQ-05.1 (транскрипция: конкретные бесплатные инструменты — Yandex SpeechKit, Whisper, GigaAM, mymeet.ai, TurboScribe).
- **ADDED:** Детализация REQ-19 (Telegram-бот: 3 вопроса — ниша, размер, боль; сценарий: приветствие → вопросы по одному → предложение ценности → интеграция с системой).
- **ADDED:** Детализация REQ-16 (веб-интерфейс: статичный HTML с возможностью открытия по ссылке + скачивания файла).
- **ADDED:** Референсы 11–12 (Draw.io CSV/XML import, Telegram bot lead qualification best practices).
- **MODIFIED:** Нефункциональные требования (Interoperability уточнён: CSV export для draw.io).
- **MODIFIED:** Риски (добавлен риск ограничений Yandex SpeechKit + митигация альтернативами).
- **REMOVED:** Все открытые вопросы сняты (решения зафиксированы).

---

**ТЗ готово к передаче Claude-Оркестратору.**
