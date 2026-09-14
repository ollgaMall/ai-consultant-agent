# АРХИТЕКТУРА ОТ ОРКЕСТРАТОРА (Claude) — TASK-001: AI Opportunity and Implementation Consultant

**Версия:** v4 (заменяет v3 — добавлен реестр нод исполнения / Execution Flow)
**Сохранить как:** `deliverables/TASK-001-ARCHITECTURE-v4.md`
**Дата:** 2026-09-08
**Источник:** ТЗ от Perplexity (`deliverables/TASK-000-TZ-v1.2.md`) + серия архитектурных решений владельца продукта
**Статус:** Волны 1–5 полностью специфицированы. Этот документ самодостаточен — Generator (DeepSeek) не имеет доступа к истории чата и должен получать всю необходимую информацию отсюда, без отсылок к внешним источникам.

---

## 1. Обзор

Полная архитектура продукта AI Opportunity and Implementation Consultant: декомпозиция ТЗ v1.2 на 30 задач для DeepSeek, пять архитектурных решений поверх исходного плана, модель данных, диаграммы, статусная модель заявки, спецификация 13 экранов веб-приложения.

## 2. Хронология волн решений

| Волна | Что добавлено/изменено |
|---|---|
| 1 | Базовая декомпозиция ТЗ v1.2 (TASK-002–024) |
| 2 | Точка ручной проверки консультантом (TASK-025/026) |
| 3 | RAG-пайплайн (TASK-027–029), критический пересмотр архитектуры |
| 4 | НФТ по бэкапам (TASK-031), сущность «Заявка» (TASK-030), разделение хранилищ, LLM-провайдер, анти-спам |
| 5 | Единое веб-приложение (Вариант Б), 13 экранов |

---

## 3. Архитектурные решения

### 3.1 Транскрипция (REQ-05.1)
**Решение:** GigaAM-v3 (self-hosted, MIT) — основной; Whisper (self-hosted) — резерв.
**Обоснование:** GigaAM-v3 точнее на русском (WER 9.2% vs 25.1% у Whisper-large-v3). Оба self-hosted, без лимитов.
**Находка:** референс ТЗ v1.2 о free tier Yandex SpeechKit (100 000 сообщений/мес) не подтверждён официальной документацией — реально платно после пробного периода.
**Отклонено:** Yandex SpeechKit, mymeet.ai (180 мин/мес), TurboScribe (лимит файлов/день).

### 3.2 Хранилище эталона (REQ-18)
**Решение:** ChromaDB (self-hosted, Apache 2.0) с локальной embedding-моделью `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (без OpenAI API).
**Отклонено:** JSON-библиотека (изначальная рекомендация архитектора, отменена владельцем продукта), графовая БД.

### 3.3 LLM-провайдер аналитического слоя (REQ-07–12)
**Решение:** Переключаемая комбинация через интерфейс `AnalysisLLMProvider`:

| Провайдер | Лимит free tier |
|---|---|
| Gemini API (прямой) | ~1500 запросов/день, 1M TPM |
| OpenRouter (`:free`) | 20/мин, 50/день — общий лимит на весь аккаунт |
| Groq (опционально) | ~30/мин, до 14 400/день |

**Риск:** free tier Gemini использует данные запросов для обучения — реальные клиентские данные не передаются до перехода на платный tier/self-hosted LLM. MVP — только синтетические данные.
**Отклонено:** GigaChat API (разовый грант 1 млн токенов/год), OpenRouter как единственный источник.

### 3.4 RAG-пайплайн
**Решение:** Голый Python поверх ChromaDB (chunking → embedding → retrieval), не LangChain/LlamaIndex — прозрачность механики важнее готовых абстракций.
**Изоляция:** отдельная ChromaDB-коллекция на client_id (TASK-028), отделена от коллекции эталона (TASK-022).

### 3.5 Точка ручной проверки консультантом
**Решение:** Обязательный гейт (TASK-025/026) между анализом и отчётом, реализуется как экран №6 веб-приложения.
**Обучающий контур:** правки консультанта — второй источник сигнала для TASK-024 наравне с фидбеком клиента, равные веса на MVP.

### 3.6 Разделение хранилищ (Polyglot persistence)
**Решение:** ChromaDB — только `CHUNK` (RAG-индекс, TASK-028) и `BENCHMARK_PATTERN` (эталон, TASK-022). SQLite — все структурные сущности (`CLIENT`, `CLIENT_APPLICATION`, `USER`, `REPORT`, `REVIEW_EDIT`, `LLM_PROVIDER_CONFIG` и др.).
**Обоснование:** разные типы запросов (семантический поиск vs точные фильтры/транзакции) требуют разных БД. MySQL отклонён — избыточен, требует отдельного сервера.

### 3.7 Резервное копирование (НФТ)
**Решение:** Ежедневный автоматический архив (ChromaDB snapshot + SQLite + `history/`), копия на второй носитель, ротация 7 дней (TASK-031). Offsite-копия отложена (не требуется для MVP).
**НФТ (ISO 25010 — Reliability/Recoverability):** «Система должна автоматически создавать резервную копию эталона и данных заявок клиентов не реже раза в сутки, с копией на втором носителе, ротация ≥7 дней».

### 3.8 Заявка и статусная модель
**Решение:** Сущность `CLIENT_APPLICATION` с полем `status` (11 состояний, раздел 7), SQLite, матрица допустимых переходов в конфиге (TASK-030).

### 3.9 Telegram-бот — анти-спам
**Решение:** Приём свободного текста только в состоянии ожидания вопроса 3; ограничение длины ответа (500 символов, конфигурируемо). НЕ добавлены: rate limit на пользователя, глобальный rate limit, CAPTCHA.

### 3.10 Единое веб-приложение (Вариант Б)
**Решение:** Flask + Jinja2 + htmx, серверный рендеринг, WSGI-сервер waitress.
**Аутентификация:** логин/пароль (Flask-Login) — Консультант, Администратор; magic-link (`itsdangerous`) — Клиент, Сотрудник клиента.
**Следствие:** задача TASK-033 (изолированный Flask-сервис для LLM-провайдера) упразднена, поглощена экраном №9.
**Отклонено:** SPA на React, единый логин для всех ролей.

---

## 4. Полная спецификация задач для DeepSeek

> **Общий технологический стек** (зафиксирован Оркестратором, не был задан в ТЗ): Python 3.11+, стандартная библиотека где возможно, pytest для тестов.
>
> **Общее правило Definition of Done для ВСЕХ задач ниже:** код соответствует Acceptance Criteria; покрытие тестами ≥80%; docstring на каждой публичной функции/классе; прошёл ревью ChatGPT без критических замечаний; PR в `main` после зелёных тестов Kimi (GitHub Flow, feature-branch указана в каждой задаче).

---

### TASK-002 — project_structure
**Источник:** ТЗ Perplexity, REQ-02

**Контекст:** Первый компонент MVP — без единообразной структуры папок последующие модули не имеют, куда писать данные.

**Что сделать:** Модуль `src/ingestion/project_structure.py`, функция `create_client_project(client_id: str, base_path: str | Path) -> Path`, создающая структуру:
```
{base_path}/{client_id}/
  01-transcripts/
  02-product/
  03-analysis/
  04-deliverables/
  05-client-materials/
```
`base_path` — обязательный параметр, не хардкодить путь.

**Acceptance Criteria:**
- Given новый client_id и валидный base_path, When вызывается `create_client_project`, Then создаются все 5 папок верхнего уровня.
- Given структура для этого client_id уже существует, When функция вызывается повторно, Then существующие данные не перезаписываются и выбрасывается `ProjectAlreadyExistsError`.

**Архитектурные ограничения:** Только стандартная библиотека. Single Responsibility — модуль не занимается загрузкой файлов (это TASK-003). `base_path` — параметр, не константа.

**Feature-branch:** `task/TASK-002-project-structure`

---

### TASK-003 — material_upload
**Источник:** ТЗ Perplexity, REQ-01 | **Зависит от:** TASK-002

**Контекст:** Отвечает за приём материалов клиента и их неизменное сохранение.

**Что сделать:** Модуль `src/ingestion/material_upload.py`, функция `register_material(client_project_path: Path, source_file: Path, material_type: str) -> MaterialRecord`. Копирует (не перемещает) файл в `05-client-materials/` без изменения содержимого. `MaterialRecord` — dataclass (path, type, batch_id, uploaded_at). Поддерживаемые типы MVP: DOC/DOCX, TXT, MD, XLS/XLSX, аудио (принимать как есть, без валидации кодека).

**Acceptance Criteria:**
- Given структура проекта существует (TASK-002), When загружается файл поддерживаемого типа, Then оригинал копируется в `05-client-materials/` без изменений (проверка хэша до/после), and возвращается заполненный `MaterialRecord`.
- Given файл неподдерживаемого типа, When вызывается `register_material`, Then выбрасывается `UnsupportedMaterialTypeError`, файл не копируется.

**Архитектурные ограничения:** try/except обязателен вокруг файловых операций. Модуль не знает про формат manifest.md (это TASK-004). Стратегия генерации `batch_id` (UUID4 или timestamp) — в конфиге.

**Feature-branch:** `task/TASK-003-material-upload`

---

### TASK-004 — manifest
**Источник:** ТЗ Perplexity, REQ-03 | **Зависит от:** TASK-003

**Контекст:** Формирует человекочитаемый реестр материалов из `MaterialRecord`.

**Что сделать:** Модуль `src/ingestion/manifest.py`, функция `append_to_manifest(client_project_path: Path, record: MaterialRecord) -> None`, дописывающая строку в `manifest.md` (создаёт файл с заголовком таблицы, если не существует) со столбцами: путь, тип, batch ID, краткое описание, дата загрузки.

**Acceptance Criteria:**
- Given один или несколько `MaterialRecord` зарегистрированы, When вызывается `append_to_manifest`, Then `manifest.md` содержит по одной строке на материал, без дублирования при повторном вызове с тем же record (идемпотентность по batch_id).
- Given `manifest.md` не существует, When функция вызывается впервые, Then файл создаётся с корректным заголовком таблицы Markdown.

**Архитектурные ограничения:** Идемпотентность по batch_id обязательна. Формат — валидная Markdown-таблица.

**Feature-branch:** `task/TASK-004-manifest-registry`

---

### TASK-005 — questionnaire_generator
**Источник:** ТЗ Perplexity, REQ-04

**Контекст:** Второй логический блок MVP — сбор данных от сотрудников.

**Что сделать:** Модуль `src/collection/questionnaire_generator.py`, функция `generate_questionnaires(departments: list[str], config_path: Path) -> dict[str, Path]`, генерирующая по одному текстовому файлу-анкете на департамент + один для executive из шаблона в конфиге, сохраняет в `02-product/questionnaires/`.

**Acceptance Criteria:**
- Given список департаментов и путь к шаблону в конфиге, When вызывается `generate_questionnaires`, Then создаётся N+1 файлов (N департаментов + executive) с подстановкой названия департамента.
- Given пустой список департаментов, When вызывается функция, Then выбрасывается `EmptyDepartmentListError` без создания файлов.

**Архитектурные ограничения:** Шаблон анкеты — в конфиге (`config/questionnaire_template.md`), не в коде. Модуль не должен перезаписывать уже отредактированные консультантом файлы при повторном запуске (проверка по существованию файла).

**Feature-branch:** `task/TASK-005-questionnaire-generator`

---

### TASK-006 — audio_digest
**Источник:** ТЗ Perplexity, REQ-05, REQ-05.1 | **Зависит от:** TASK-003

**Контекст:** Реализует решение 3.1 — GigaAM-v3 основной, Whisper резервный.

**Что сделать:** Модуль `src/collection/audio_digest.py`:
1. `TranscriptionProvider` — абстрактный интерфейс с методом `transcribe(audio_path: Path) -> str`.
2. `GigaAMProvider` и `WhisperProvider` — реализации интерфейса.
3. `build_employee_digest(raw_transcript: str) -> EmployeeDigest` — dataclass: role, processes, tools, pains, metrics, asr_uncertainties.
4. Сохранение: raw transcript отдельно, edited semantic version отдельно, digest — в `01-transcripts/`.

**Acceptance Criteria:**
- Given зарегистрированный аудиофайл, When вызывается transcribe через `GigaAMProvider`, Then возвращается непустая строка транскрипта.
- Given провайдер недоступен (нет GPU/модель не загружена), When происходит ошибка инициализации, Then система автоматически переключается на `WhisperProvider` и логирует факт fallback.
- Given готовый транскрипт, When вызывается `build_employee_digest`, Then возвращается `EmployeeDigest` со всеми полями, при этом поля с низкой уверенностью ASR явно помечены в `asr_uncertainties`.

**Архитектурные ограничения:** Выбор провайдера и fallback-логика — через конфиг. Single Responsibility: транскрипция и построение digest — разные функции/классы. try/except вокруг вызова моделей.

**Feature-branch:** `task/TASK-006-audio-transcription-digest`

---

### TASK-007 — completeness_check
**Источник:** ТЗ Perplexity, REQ-06 | **Зависит от:** TASK-004

**Контекст:** Закрывает входной блок — перед анализом система показывает консультанту, чего не хватает.

**Что сделать:** Модуль `src/ingestion/completeness_check.py`, функция `check_completeness(client_project_path: Path, required_materials: list[str]) -> CompletenessReport` (список отсутствующих материалов, список полученных, флаг `ready_to_proceed: bool`).

**Acceptance Criteria:**
- Given manifest.md и список обязательных типов из конфига, When вызывается `check_completeness`, Then отчёт корректно перечисляет недостающие позиции.
- Given все обязательные материалы присутствуют, When вызывается функция, Then `ready_to_proceed = True`.

**Архитектурные ограничения:** `required_materials` — конфигурируемый список. Модуль только формирует отчёт — решение «продолжать?» принимает консультант через экран 4.

**Feature-branch:** `task/TASK-007-completeness-gate`

---

### TASK-008 — Claim / маркировка
**Источник:** ТЗ Perplexity, REQ-10

**Контекст:** Фундаментальный, сквозной компонент — используется всеми последующими аналитическими модулями.

**Что сделать:** Модуль `src/analysis/claims.py`: dataclass `Claim(text: str, claim_type: ClaimType, source_ref: str | None)`, `ClaimType` — enum `{FACT, CONCLUSION, HYPOTHESIS, ASSUMPTION}`; функция `render_claim(claim: Claim) -> str`, форматирующая как `[ФАКТ] ...` / `[ВЫВОД] ...` / `[ГИПОТЕЗА] ...` / `[ПРЕДПОЛОЖЕНИЕ] ...`.

**Acceptance Criteria:**
- Given `Claim` с любым `claim_type`, When вызывается `render_claim`, Then строка начинается с соответствующего маркера.
- Given `claim_type` вне enum, When создаётся `Claim`, Then Python не позволяет создать объект (типизация через enum).

**Архитектурные ограничения:** Без внешних зависимостей — модель данных, а не аналитика.

**Feature-branch:** `task/TASK-008-claim-marking`

---

### TASK-009 — process_discovery (финальная версия, интегрирует RAG)
**Источник:** ТЗ Perplexity, REQ-07 | **Зависит от:** TASK-006, TASK-008, TASK-029

**Контекст:** Обнаружение бизнес-процессов компании. Изначально проектировался на прямой передаче всех digest'ов в LLM; после введения RAG-пайплайна (волна 3) переработан на точечный retrieval по департаментам.

**Что сделать:** Модуль `src/analysis/process_discovery.py`: `AnalysisLLMProvider` — абстрактный интерфейс с методом `analyze(prompt: str) -> str` (реализации — см. TASK-032); функция `discover_processes(client_id: str, department_queries: list[str], retriever: Retriever, provider: AnalysisLLMProvider) -> list[ProcessRecord]`, где `ProcessRecord`: department, frequency, time_volume, inputs, outputs, pain_points, claims (список `Claim`). На каждый департамент формируется точечный запрос (например, «процессы и проблемы отдела продаж»), `retriever.retrieve()` возвращает top-K релевантных чанков именно по этому департаменту, только они идут в промпт.

**Acceptance Criteria:**
- Given непустой список department_queries, When вызывается `discover_processes`, Then возвращается ≥1 `ProcessRecord` на департамент с достаточными данными.
- Given `retriever` возвращает `low_confidence = True` для департамента (нет релевантных данных), When обрабатывается этот департамент, Then возвращается `ProcessRecord` с полем `data_coverage: "insufficient"`, а не выдуманный процесс.
- Given найдены релевантные чанки, When формируется `Claim` для каждого поля `ProcessRecord`, Then `Claim.source_ref` указывает на `chunk_id` конкретного retrieved-чанка.
- Given провайдер недоступен/ошибка API, When вызов происходит, Then выбрасывается явное `AnalysisProviderError`, не пустой/тихий результат.

**Архитектурные ограничения:** Provider abstraction (Dependency Inversion — первый приоритет по SOLID для проекта). Промпт-шаблоны — в конфиге, не хардкод.

**Feature-branch:** `task/TASK-009-rag-integration`

---

### TASK-010 — automation_scoring
**Источник:** ТЗ Perplexity, REQ-08 | **Зависит от:** TASK-009

**Что сделать:** Модуль `src/analysis/automation_scoring.py`, функция `score_process(process: ProcessRecord, weights_config: Path) -> ScoredProcess`, скоринг по 5 критериям (repeatability, data availability, explainability, time volume, error cost), веса — из конфига.

**Acceptance Criteria:**
- Given `ProcessRecord` и конфиг весов, When вызывается `score_process`, Then возвращается `ScoredProcess` с итоговым числовым скором и разбивкой по каждому критерию.
- Given конфиг весов не в валидном диапазоне (сумма ≠ 1.0), When загружается конфиг, Then выбрасывается `InvalidWeightsConfigError`.

**Архитектурные ограничения:** Веса и критерии — только в конфиге. Чистая функция, без вызовов LLM (детерминированный расчёт, не требует reasoning).

**Feature-branch:** `task/TASK-010-automation-scoring`

---

### TASK-011 — implementation_classifier (финальная версия, интегрирует RAG)
**Источник:** ТЗ Perplexity, REQ-09 | **Зависит от:** TASK-010, TASK-029

**Что сделать:** Модуль `src/analysis/implementation_classifier.py`, функция `classify_implementation(scored_process: ScoredProcess, retriever: Retriever, provider: AnalysisLLMProvider) -> ClassifiedProcess`, присваивающая одну из 4 меток: `CODE / AGENT / HYBRID / HUMAN_AI`. Перед классификацией модуль запрашивает `retriever.retrieve(query=f"детали процесса {scored_process.name}")` для обоснования цитатой.

**Acceptance Criteria:**
- Given `ScoredProcess`, When вызывается `classify_implementation`, Then возвращается ровно одна метка из 4 допустимых плюс обоснование (`Claim` типа `CONCLUSION`), ссылающееся на `chunk_id` retrieved-чанка.
- Given процесс с explainability-критерием ниже порога (конфиг), When классифицируется, Then метка не может быть `AGENT` без явного `HUMAN_AI`-компонента.

**Архитектурные ограничения:** Порог explainability — в конфиге, не хардкод числом в коде.

**Feature-branch:** `task/TASK-011-rag-integration`

---

### TASK-012 — maturity_assessment (финальная версия, интегрирует RAG)
**Источник:** ТЗ Perplexity, REQ-11 | **Зависит от:** TASK-009–011, TASK-029

**Что сделать:** Модуль `src/analysis/maturity_assessment.py`, функция `assess_maturity(classified_processes: list[ClassifiedProcess], retriever: Retriever, provider: AnalysisLLMProvider) -> MaturityScore` (score 0–5, justification — список `Claim`). Опциональный retrieval по общему запросу «уровень автоматизации и governance в компании» для дополнительного обоснования.

**Acceptance Criteria:**
- Given список `ClassifiedProcess` по всей компании, When вызывается `assess_maturity`, Then возвращается ровно одно значение 0–5 (на уровне экосистемы, не per-department) с обоснованием, ссылающимся на конкретные `ProcessRecord`.
- Given пустой список процессов, When вызывается функция, Then выбрасывается `InsufficientDataError`.
- Given отсутствуют релевантные чанки для governance-запроса, When формируется justification, Then оно строится только на `ClassifiedProcess`, без выдуманных деталей.

**Feature-branch:** `task/TASK-012-rag-integration`

---

### TASK-013 — as_is_to_be (финальная версия, интегрирует RAG)
**Источник:** ТЗ Perplexity, REQ-12 | **Зависит от:** TASK-011, TASK-029

**Что сделать:** Модуль `src/analysis/as_is_to_be.py`, функция `build_as_is_to_be(classified_processes: list[ClassifiedProcess], retriever: Retriever, provider: AnalysisLLMProvider) -> list[AsIsToBe]` (process_name, as_is_description, to_be_description, delta_claims). AS-IS строится через точечный `retriever.retrieve(query=f"текущее состояние процесса {process.name}")` (grounded в цитатах), TO-BE — генеративно (LLM предлагает целевое состояние, по природе `HYPOTHESIS`).

**Acceptance Criteria:**
- Given классифицированные процессы, When вызывается `build_as_is_to_be`, Then для каждого процесса с меткой отличной от «оставить как есть» формируется пара AS-IS/TO-BE с явным delta.
- Given процесс без изменений в TO-BE, When обрабатывается, Then помечается явно как «без изменений», не пропускается молча.
- Given AS-IS содержит детали, не подтверждённые ни одним retrieved-чанком, When формируется описание, Then эти детали помечаются `Claim(ASSUMPTION)`, не `Claim(FACT)`.

**Feature-branch:** `task/TASK-013-rag-integration`

---

### TASK-014 — process_map
**Источник:** ТЗ Perplexity, REQ-13 | **Зависит от:** TASK-010, TASK-011

**Что сделать:** Модуль `src/analysis/process_map.py`, функция `build_process_map(scored: list[ScoredProcess], classified: list[ClassifiedProcess]) -> ProcessMapTable` со столбцами: process, department, frequency, time_volume, automation_potential, implementation_type, priority (сортировка по скору).

**Acceptance Criteria:**
- Given согласованные по process_id списки scored и classified, When вызывается `build_process_map`, Then таблица отсортирована по priority по убыванию, все 7 столбцов заполнены.
- Given несовпадение process_id между scored и classified, When вызывается функция, Then выбрасывается `DataMismatchError`, не тихое игнорирование строки.

**Feature-branch:** `task/TASK-014-process-map`

---

### TASK-015 — drawio_csv_export
**Источник:** ТЗ Perplexity, REQ-13.1 | **Зависит от:** TASK-014

**Что сделать:** Модуль `src/export/drawio_csv_export.py`, функция `export_to_drawio_csv(process_map: ProcessMapTable, output_path: Path) -> Path`, генерирующая CSV со столбцами `id, parent, label, department, inputs, outputs, executor, frequency, tools` (совместимо с draw.io: Arrange → Insert → Advanced → CSV).

**Acceptance Criteria:**
- Given `ProcessMapTable`, When вызывается экспорт, Then создаётся валидный CSV с header, каждая строка содержит уникальный `id`.
- Given процессы с иерархией (родитель/подпроцесс), When экспортируется, Then поле `parent` корректно ссылается на `id` родителя, иначе остаётся пустым.

**Definition of Done (дополнение к общему правилу):** ручная проверка — сгенерированный CSV успешно импортируется в draw.io (приложить скриншот в PR).

**Feature-branch:** `task/TASK-015-drawio-export`

---

### TASK-016 — roadmap
**Источник:** ТЗ Perplexity, REQ-14 | **Зависит от:** TASK-013, TASK-014

**Что сделать:** Модуль `src/analysis/roadmap.py`, функция `build_roadmap(as_is_to_be, process_map, provider: AnalysisLLMProvider) -> Roadmap` (3–5 `Phase(name, timeline, resources, processes_covered, claims)`).

**Acceptance Criteria:**
- Given заполненные AS-IS/TO-BE и process map, When вызывается `build_roadmap`, Then возвращается от 3 до 5 фаз, каждая ссылается на ≥1 процесс из карты.
- Given process_map пустой, When вызывается функция, Then `InsufficientDataError`.

**Архитектурная заметка:** эта задача НЕ обновлялась под RAG — синтез верхнего уровня работает с уже агрегированными данными, точечный retrieval здесь избыточен.

**Feature-branch:** `task/TASK-016-roadmap`

---

### TASK-017 — roi_estimator
**Источник:** ТЗ Perplexity, REQ-15 | **Зависит от:** TASK-010

**Что сделать:** Модуль `src/analysis/roi_estimator.py`, функция `estimate_roi(scored_processes, rate_config: Path) -> ROIEstimate` — детерминированный расчёт (без LLM): `time_savings_hours: (low, high)`, `revenue_impact: (low, high)`, диапазон через конфигурируемый множитель неопределённости, каждая оценка — `Claim(HYPOTHESIS)`.

**Acceptance Criteria:**
- Given процессы со скором и time_volume, When вызывается `estimate_roi`, Then `low < high` во всех диапазонах.
- Given процесс без данных time_volume, When вызывается функция, Then используется дефолтное значение из конфига, явно маркируется `Claim(ASSUMPTION)`.

**Архитектурные ограничения:** Чистая функция, детерминирована — не требует `AnalysisLLMProvider`.

**Feature-branch:** `task/TASK-017-roi-estimator`

---

### TASK-018 — report_model (финальная версия, потребляет только одобренные данные)
**Источник:** ТЗ Perplexity, REQ-16/17 (основа) | **Зависит от:** TASK-026 (не напрямую от TASK-012–017!)

**Контекст:** После введения точки ручной проверки (волна 2) TASK-018 больше не принимает сырые данные аналитических модулей напрямую — только одобренную консультантом версию.

**Что сделать:** Модуль `src/report/report_model.py`, функция `build_report_model(reviewed_bundle: ReviewedAnalysisBundle) -> ReportModel` — единая модель-агрегатор, единый источник для рендереров (TASK-019–021). `ReviewedAnalysisBundle` — тип, возвращаемый TASK-026.

**Acceptance Criteria:**
- Given `ReviewedAnalysisBundle` со всеми секциями, When вызывается `build_report_model`, Then возвращается `ReportModel` со всеми секциями заполненными.
- Given одна из секций отсутствует в bundle, When собирается модель, Then секция явно помечается как `missing`, не падает с ошибкой атрибута.

**Feature-branch:** `task/TASK-018-report-model`

---

### TASK-019 — render_html_pdf
**Источник:** ТЗ Perplexity, REQ-16, REQ-17 (executive-версия) | **Зависит от:** TASK-018

**Что сделать:** Модуль `src/report/render_html_pdf.py`, функция `render_executive_report(model: ReportModel, template_path: Path) -> tuple[Path, Path]` — статичный HTML + PDF (~20 стр.), рендеринг через Jinja2 + WeasyPrint (open-source, self-hosted).

**Acceptance Criteria:**
- Given `ReportModel`, When вызывается рендер, Then создаются оба файла, HTML открывается без внешних сетевых зависимостей.
- Given секция помечена `missing`, When рендерится, Then отображается явная плашка «раздел не завершён».

**Архитектурные ограничения:** Новые зависимости (jinja2, weasyprint) — проверить лицензии как open-source перед добавлением в requirements.

**Feature-branch:** `task/TASK-019-html-pdf-renderer`

---

### TASK-020 — render_doc
**Источник:** ТЗ Perplexity, REQ-16, REQ-17 (detailed-версия) | **Зависит от:** TASK-018

**Что сделать:** Модуль `src/report/render_doc.py`, функция `render_developer_report(model: ReportModel, template_path: Path) -> Path` — .docx с техническими деталями (python-docx), включая приложения (полные claims с источниками, raw scores), отсутствующие в executive-версии.

**Acceptance Criteria:**
- Given `ReportModel`, When вызывается рендер, Then .docx содержит все секции executive-версии плюс технический раздел.
- Given модель без изменений с прошлой генерации, When рендерится повторно, Then файл перезаписывается полностью, не апендится.

**Feature-branch:** `task/TASK-020-doc-renderer`

---

### TASK-021 — render_md
**Источник:** ТЗ Perplexity, REQ-16 (внутренний формат) | **Зависит от:** TASK-018, TASK-008

**Что сделать:** Модуль `src/report/render_md.py`, функция `render_markdown_report(model: ReportModel) -> Path` — единый MD-файл, все claims отрендерены через `render_claim` (TASK-008).

**Acceptance Criteria:**
- Given `ReportModel`, When вызывается рендер, Then MD-файл содержит все секции, каждый claim с маркером `[ФАКТ]/[ВЫВОД]/[ГИПОТЕЗА]/[ПРЕДПОЛОЖЕНИЕ]`.

**Feature-branch:** `task/TASK-021-md-renderer`

---

### TASK-022 — benchmark_repository (финальная версия, с формализованным EmbeddingProvider)
**Источник:** ТЗ Perplexity, REQ-18 | **Реализует решение 3.2**

**Что сделать:** Модуль `src/knowledge/benchmark_repository.py`: интерфейс `EmbeddingProvider` (метод `embed(texts: list[str]) -> list[Vector]`, формализован отдельно, переиспользуется и здесь, и в TASK-028); интерфейс `BenchmarkRepository` (Provider abstraction) + `ChromaBenchmarkRepository` — реализация с локальной embedding-функцией через `EmbeddingProvider` (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, CPU-инференс, без обращения к OpenAI API). Методы: `store_pattern(pattern: ProcessPattern) -> None`, `find_similar(query: str, top_k: int = 5) -> list[ProcessPattern]`.

**Acceptance Criteria:**
- Given новый `ProcessPattern`, When вызывается `store_pattern`, Then паттерн сохраняется и не дублируется при повторном вызове с идентичным содержимым (проверка по хэшу).
- Given запрос `find_similar`, When в репозитории есть семантически близкие паттерны, Then они возвращаются, отсортированные по релевантности.
- Given любой вызов embedding, When выполняется тест, Then сетевой вызов к OpenAI API отсутствует (тест обязан падать при попытке внешнего HTTP-вызова, проверяется мокированием сети).

**Feature-branch:** `task/TASK-022-benchmark-repository`

---

### TASK-023 — telegram_bot (финальная версия, с анти-спам правилами)
**Источник:** ТЗ Perplexity, REQ-19 | **Реализует:** сценарий диалога из решения 3.9

**Что сделать:** Модуль `src/leadgen/telegram_bot.py` (библиотека `python-telegram-bot`, open-source) — 5-шаговый линейный сценарий:
1. `/start` → приветствие.
2. Вопрос 1 (ниша) — inline-кнопки: Retail | Услуги | Производство | Финансы/Страхование | Другое.
3. Вопрос 2 (размер) — inline-кнопки: 1–10 | 11–50 | 51–200 | 200+.
4. Вопрос 3 (боль, свободный текст) — единственная точка приёма произвольного текста.
5. Ценностное предложение (шаблон с подстановкой ответов) → CTA «Да, хочу» / «Нет, спасибо».
6. При «Да» — вызов `create_client_project` (TASK-002).

**Acceptance Criteria:**
- Given пользователь проходит все 3 вопроса и выбирает «Да, хочу», When завершается диалог, Then создаётся preliminary client project с ответами, записанными как первичная запись в manifest.
- Given бот НЕ находится в состоянии ожидания ответа на вопрос 3, When получено произвольное текстовое сообщение, Then оно игнорируется, бот повторяет текущий ожидаемый шаг (кнопки).
- Given ответ на вопрос 3 превышает 500 символов (порог — в конфиге), When получено такое сообщение, Then бот просит сократить ответ, не сохраняя урезанную/полную версию как есть.
- Given команда `/restart` в любой момент, When получена, Then состояние диалога сбрасывается.

**Явно НЕ реализуется (по решению владельца продукта):** rate limit на пользователя, глобальный rate limit сообщений/сек, CAPTCHA.

**Feature-branch:** `task/TASK-023-telegram-bot`

---

### TASK-024 — hypothesis_validation (финальная версия, два источника входа)
**Источник:** ТЗ Perplexity, REQ-20 | **Зависит от:** TASK-022, TASK-026

**Что сделать:** Модуль `src/knowledge/hypothesis_validation.py`, функция `record_feedback(claims: list[Claim], decisions: dict[str, bool], source: FeedbackSource) -> None`, где `FeedbackSource` — enum `{CONSULTANT_REVIEW, CLIENT_VALIDATION}`. Вызывается из двух мест: из TASK-026 (`import_reviewed_edits`, при правке значения относительно исходного экспорта — трактуется как подтверждение с `source=CONSULTANT_REVIEW`) и из экрана 8 веб-приложения (клиентская валидация, `source=CLIENT_VALIDATION`).

**Acceptance Criteria:**
- Given список claims типа `HYPOTHESIS` и решения по каждому, When вызывается `record_feedback`, Then соответствующие паттерны в `BenchmarkRepository` (TASK-022) обновлены.
- Given `record_feedback` вызван с любым из двух источников, When обновляется confidence паттерна, Then шаг изменения одинаков для обоих источников на MVP (равные веса — явное решение владельца продукта).
- Given паттерн обновлён, When запрашивается история паттерна, Then видно, сколько раз и от какого источника пришло подтверждение (не влияет на вес сейчас, нужно для будущего пересмотра).
- Given `decisions` содержит ключ, отсутствующий среди переданных claims, When вызывается функция, Then выбрасывается `UnknownClaimReferenceError`.

**Feature-branch:** `task/TASK-024-dual-feedback-source`

---

### TASK-025 — export_for_review (финальная версия, с реальным текстом источника)
**Источник:** AC сформулирован Оркестратором (пробел в ТЗ v1.2) | **Зависит от:** TASK-012, 013, 014, 016, 017, TASK-029

**Контекст:** Изначально экспортировал только `chunk_id` как ссылку на источник — после введения RAG (волна 3) это оказалось бессмысленным для консультанта без реального текста. Исправлено.

**Что сделать:** Модуль `src/review/export_for_review.py`, функция `export_for_review(maturity, as_is_to_be, process_map, roadmap, roi, retriever: Retriever, output_path: Path) -> Path` — сериализует все аналитические результаты в единый YAML-файл. Для каждого `Claim.source_ref` (chunk_id) модуль подтягивает **реальный текст чанка** через retriever и вставляет его как `источник_цитаты` рядом с полем, вместе с исходным `claim_type` в комментарии.

**Acceptance Criteria:**
- Given результаты всех модулей блока анализа, When вызывается `export_for_review`, Then создаётся YAML со всеми процессами/скорами/классификациями/AS-IS-TO-BE/roadmap/ROI, каждое поле снабжено inline-комментарием с исходным `claim_type` и, где применимо, реальным текстом source-чанка (не голым chunk_id).
- Given YAML сгенерирован, When консультант открывает файл, Then структура (ключи, вложенность) защищена от случайной порчи — редактируются только значения.

**Feature-branch:** `task/TASK-025-export-for-review`

---

### TASK-026 — import_reviewed_edits
**Источник:** AC сформулирован Оркестратором | **Зависит от:** TASK-025

**Что сделать:** Модуль `src/review/import_reviewed_edits.py`, функция `import_reviewed_edits(reviewed_yaml_path: Path) -> ReviewedAnalysisBundle` — парсит отредактированный YAML, валидирует схему, помечает каждое изменённое поле как `claim_type = FACT` (если значение отличалось от исходного экспорта и не помечено консультантом как отклонённое).

**Acceptance Criteria:**
- Given отредактированный YAML, When вызывается `import_reviewed_edits`, Then возвращается `ReviewedAnalysisBundle`, готовый для TASK-018.
- Given консультант изменил значение поля, When импортируется, Then соответствующий `Claim` автоматически повышается до `FACT`.
- Given нарушена структура YAML (удалён обязательный ключ), When вызывается импорт, Then выбрасывается `InvalidReviewFileError` с указанием, какого ключа не хватает — TASK-018 не должна получить возможность собрать отчёт из повреждённого файла.

**Feature-branch:** `task/TASK-026-import-reviewed-edits`

---

### TASK-027 — chunker
**Источник:** AC сформулирован Оркестратором (RAG-пайплайн, решение 3.4)

**Что сделать:** Модуль `src/rag/chunker.py`, функция `chunk_document(text: str, source_id: str, chunk_size: int = 500, overlap: int = 50) -> list[Chunk]`, где `Chunk`: text, source_id, chunk_index, metadata (тип документа, дата). Разбиение — по предложениям/абзацам с overlap.

**Acceptance Criteria:**
- Given текст документа и параметры chunk_size/overlap из конфига, When вызывается `chunk_document`, Then возвращается список `Chunk` без потери текста (конкатенация чанков минус overlap восстанавливает исходный текст).
- Given overlap ≥ chunk_size, When вызывается функция, Then выбрасывается `InvalidChunkConfigError`.

**Feature-branch:** `task/TASK-027-rag-chunker`

---

### TASK-028 — client_document_store
**Источник:** AC сформулирован Оркестратором | **Зависит от:** TASK-027

**Что сделать:** Модуль `src/rag/client_document_store.py`: `ClientDocumentStore` — обёртка над ChromaDB с изолированной коллекцией на client_id, использует `EmbeddingProvider` (тот же интерфейс, что и TASK-022). Методы: `index_chunks(client_id: str, chunks: list[Chunk]) -> None`, `delete_client_data(client_id: str) -> None`.

**Acceptance Criteria:**
- Given чанки одного клиента, When вызывается `index_chunks`, Then они попадают в коллекцию, изолированную от других client_id и от коллекции эталона (TASK-022).
- Given вызван `delete_client_data`, When операция завершена, Then ни один чанк этого клиента не находится через `find_similar` ни в этой, ни в общей коллекции.

**Известный, осознанно принятый пробел:** удаляет только векторный индекс, не файлы (TASK-003) и не SQLite-записи (TASK-030) — каскадное удаление отложено до первого реального запроса клиента на полное удаление данных.

**Feature-branch:** `task/TASK-028-client-document-store`

---

### TASK-029 — retriever
**Источник:** AC сформулирован Оркестратором | **Зависит от:** TASK-028

**Что сделать:** Модуль `src/rag/retriever.py`, функция `retrieve(client_id: str, query: str, top_k: int = 5) -> list[RetrievedChunk]`, где `RetrievedChunk`: текст, source_id, relevance_score.

**Acceptance Criteria:**
- Given запрос и client_id, When вызывается `retrieve`, Then возвращается ≤ top_k чанков, отсортированных по убыванию relevance_score.
- Given relevance_score всех найденных чанков ниже порога из конфига, When вызывается функция, Then возвращается пустой список с явным флагом `low_confidence = True`, не «мусорные» чанки для видимости.

**Feature-branch:** `task/TASK-029-retriever`

---

### TASK-030 — application_status
**Источник:** AC сформулирован Оркестратором (новая сущность, подтверждена владельцем)

**Что сделать:**
- `src/db/schema.py` — SQLite-схема: таблицы `client`, `client_application` (с полем `status`), `status_history`.
- `src/db/application_status.py` — enum `ApplicationStatus` (11 значений, см. раздел 7) + матрица допустимых переходов (в конфиге, не хардкод) + `transition_status(application_id, new_status, actor) -> None`, `get_status_history(application_id) -> list[StatusChangeRecord]`.

**Acceptance Criteria:**
- Given текущий статус и запрошенный переход есть в матрице допустимых, When вызывается `transition_status`, Then статус обновляется, в `status_history` добавляется запись (timestamp, actor, старый/новый статус).
- Given переход не разрешён матрицей (например, из `CLOSED_COMPLETED` обратно в `ANALYSIS`), When вызывается функция, Then выбрасывается `InvalidStatusTransitionError`, статус не меняется.
- Given заявка перешла в `ERROR` из состояния X, When ошибка устранена вручную, Then возможен переход либо обратно в X (из истории), либо в `CANCELLED`.

**Архитектурные ограничения:** Матрица переходов — в конфиге. SQLite через стандартную библиотеку `sqlite3`, без ORM на MVP.

**Feature-branch:** `task/TASK-030-application-status`

---

### TASK-031 — backup_scheduler
**Источник:** AC сформулирован Оркестратором (новое НФТ) | **Зависит от:** TASK-022, TASK-028, TASK-030

**Что сделать:** Модуль `src/ops/backup_scheduler.py`, функция `create_backup(primary_dir: Path, secondary_dir: Path) -> BackupResult` — создаёт единый timestamped-архив (`backup_ГГГГ-ММ-ДД_ЧЧММ.tar.gz`), включающий: директорию персистентности ChromaDB (эталон + все клиентские коллекции), файл SQLite, папку `history/`. Копирует архив в `primary_dir` и `secondary_dir`.

**Acceptance Criteria:**
- Given ChromaDB и SQLite существуют, When вызывается `create_backup`, Then создаётся один архив, содержащий все три источника без потерь.
- Given в `primary_dir` уже 7 ежедневных архивов, When создаётся новый, Then самый старый удаляется (ротация).
- Given `secondary_dir` физически недоступен, When бэкап запускается, Then бэкап в `primary_dir` всё равно выполняется, недоступность второго носителя логируется как явное предупреждение — не тихий отказ всего бэкапа.
- Given ChromaDB активно пишет данные во время бэкапа, When создаётся архив, Then используется собственный snapshot-механизм ChromaDB, не сырое копирование файлов «на лету».

**Definition of Done (дополнение):** README дополнен инструкцией по настройке cron: `0 2 * * * python backup_scheduler.py`.

**Feature-branch:** `task/TASK-031-backup-scheduler`

---

### TASK-032 — llm_provider_registry
**Источник:** AC сформулирован Оркестратором (решение владельца, 3.3) | **Зависит от:** TASK-030

**Что сделать:** Каталог `src/analysis/providers/`: три реализации `AnalysisLLMProvider` — `GeminiProvider`, `OpenRouterProvider(model_id)`, `GroqProvider(model_id)`. `ProviderRegistry.get_active_provider() -> AnalysisLLMProvider` — читает конфиг из таблицы `llm_provider_config` (SQLite) при **каждом** вызове, не кэширует на старте процесса.

**Acceptance Criteria:**
- Given в `llm_provider_config` активен `OPENROUTER` с моделью `meta-llama/llama-3.2-3b-instruct:free`, When любой модуль анализа запрашивает провайдера, Then получает именно эту конфигурацию.
- Given конфиг изменён администратором (экран 9) между двумя вызовами анализа, When выполняется следующий вызов, Then используется уже новый провайдер, без перезапуска процесса.
- Given OpenRouter/Groq возвращает ошибку превышения лимита (HTTP 429), When это происходит, Then ошибка передаётся наверх явно, с сообщением, рекомендующим переключить провайдера — не бесконечный тихий retry.

**Feature-branch:** `task/TASK-032-llm-provider-registry`

---

### TASK-033 — УПРАЗДНЕНА

Изначально: изолированный Flask-сервис только для переключения LLM-провайдера. **Заменена решением 3.10** (единое веб-приложение) — функциональность полностью реализуется экраном №9 (раздел 8) внутри общего приложения. Отдельная задача TASK-033 не создаётся — экран 9 декомпозируется в рамках задач веб-приложения (см. раздел 12, открытый вопрос 1).

---

## 5. Модель данных — полная (сущности с атрибутами)

| Сущность | Ключевые атрибуты | Хранилище |
|---|---|---|
| `LEAD_INQUIRY` | id, niche, company_size, pain_text, created_at | SQLite |
| `CLIENT` | id, name, industry, created_at | SQLite |
| `CLIENT_APPLICATION` | id, client_id, status, created_at, updated_at | SQLite |
| `MATERIAL` | id, application_id, file_path, file_type, batch_id, uploaded_at | SQLite (метаданные), файловая система |
| `EMPLOYEE` | id, application_id, department, role | SQLite |
| `DIGEST` | id, employee_id, raw_transcript_path, role, pains, metrics, asr_uncertainties | SQLite (метаданные), файл |
| `CHUNK` | id, source_id, text, chunk_index, metadata_json | ChromaDB |
| `PROCESS` | id, application_id, name, department, automation_score, implementation_type, priority | SQLite |
| `CLAIM` | id, parent_entity_id, claim_type, text, source_chunk_id | SQLite (метаданные), ссылка на ChromaDB chunk |
| `MATURITY_SCORE` | id, application_id, score_0_5, justification | SQLite |
| `AS_IS_TO_BE` | id, process_id, as_is_description, to_be_description | SQLite |
| `ROADMAP_PHASE` | id, application_id, name, timeline, phase_order | SQLite |
| `ROI_ESTIMATE` | id, process_id, hours_low, hours_high, revenue_low, revenue_high | SQLite |
| `REVIEW_EDIT` | id, application_id, user_id, field_changed, old_value, new_value, edited_at | SQLite |
| `REPORT` | id, application_id, format, file_path, generated_at | SQLite (метаданные), файловая система |
| `BENCHMARK_PATTERN` | id, pattern_text, confidence, confirmations_count, rejections_count | ChromaDB |
| `USER` | id, role, name | SQLite |
| `LLM_PROVIDER_CONFIG` | id, active_provider, active_model_id, switched_at, switched_by_user_id | SQLite |

## 6. Диаграммы

**⚠️ Важно:** диаграммы физически хранятся в папке `diagrams/` репозитория. Они не создаются автоматически — при первичной настройке проекта их нужно один раз скачать из соответствующих сессий Claude и закоммитить.

| Диаграмма | Путь в репозитории | Назначение |
|---|---|---|
| Модули и потоки данных | `diagrams/architecture-diagram.html` | Технический поток обработки (зависимости TASK-XXX) |
| Модель данных (ER) | `diagrams/entity-diagram.html` | Сущности и связи |
| Статусы заявки | `diagrams/status-diagram.html` | Переходы состояний `CLIENT_APPLICATION` |
| Service Blueprint | `diagrams/service-blueprint.html` | Точки взаимодействия человека с системой |
| Execution Flow (ноды) | `diagrams/execution-flow-diagram.html` | Семантика выполнения: триггер/ожидание/готовность на каждом шаге (см. раздел 11) |

## 7. Статусная модель заявки (TASK-030)

**11 состояний:** `NEW_LEAD`, `AWAITING_DOCUMENTS`, `AWAITING_DOCUMENTS_PAUSED`, `ANKETA_CREATION`, `ANALYSIS`, `CONSULTANT_REVIEW`, `REPORT_GENERATION`, `AWAITING_CLIENT_FEEDBACK`, `CLOSED_COMPLETED`, `CANCELLED`, `ERROR`.

**Переходы:**
```
NEW_LEAD -> AWAITING_DOCUMENTS
AWAITING_DOCUMENTS <-> AWAITING_DOCUMENTS_PAUSED
AWAITING_DOCUMENTS -> ANKETA_CREATION
ANKETA_CREATION -> AWAITING_DOCUMENTS_PAUSED (обнаружена нехватка данных)
ANKETA_CREATION -> ANALYSIS
ANALYSIS <-> CONSULTANT_REVIEW
CONSULTANT_REVIEW -> REPORT_GENERATION
REPORT_GENERATION -> AWAITING_CLIENT_FEEDBACK
AWAITING_CLIENT_FEEDBACK -> CLOSED_COMPLETED
[AWAITING_DOCUMENTS | ANKETA_CREATION | ANALYSIS] -> ERROR -> (исходное состояние | CANCELLED)
[AWAITING_DOCUMENTS | ANKETA_CREATION | ANALYSIS | CONSULTANT_REVIEW] -> CANCELLED
```
Визуально — `diagrams/status-diagram.html`.

## 8. Веб-приложение — полная спецификация 13 экранов

Flask + Jinja2 + htmx. Аутентификация: логин (Консультант/Администратор), magic-link (Клиент/Сотрудник).

### Экран 0 — Вход
Роль: Консультант, Администратор. Доступ: логин/пароль.
Элементы: поля логин+пароль, чекбокс «запомнить меня», ссылка «забыли пароль» (опционально).
Действие: «Войти» → экран 1. Данные: `USER`.

### Экран 1 — Дашборд / Список заявок
Роль: Консультант.
Элементы: таблица (Клиент | Статус — цветной бейдж | Дата создания | Дата изменения), фильтр по статусу, поиск по клиенту, кнопка «+ Новая заявка», счётчики.
Действия: клик по строке → экран 2. Данные: `CLIENT_APPLICATION`, `CLIENT`.

### Экран 2 — Карточка заявки
Роль: Консультант (полная), Клиент (упрощённая, magic-link).
Консультант: шапка, прогресс-бар, история статусов, вкладки (Материалы→3, Сотрудники, Анализ→6, Отчёт→7), кнопка «Отменить заявку».
Клиент: прогресс-бар + статус человеческим языком.
Данные: `CLIENT_APPLICATION`, `status_history`, связанные `MATERIAL`/`EMPLOYEE`/`REPORT`.

### Экран 3 — Загрузка материалов
Роль: Консультант.
Элементы: drag-and-drop зона, список загруженных (имя, тип, дата, статус обработки), индикатор допустимых форматов.
Действие: «Загрузить» → TASK-003, фоновый вызов TASK-007. Данные: `MATERIAL`.

### Экран 4 — Проверка полноты
Роль: Консультант.
Элементы: чекмарки требуемых типов, пояснение по пробелам, кнопка «Продолжить, даже если не всё готово», кнопка «Приостановить заявку».
Действие: «Продолжить» → статус `ANKETA_CREATION`. Данные: результат TASK-007.

### Экран 5 — Анкета сотрудника
Роль: Сотрудник клиента. Доступ: magic-link (ссылка отправляется консультантом вручную вне системы на MVP).
Элементы: приветствие, список вопросов, опционально прикрепление аудио, прогресс.
Действие: «Отправить ответы» → TASK-006 при аудио. Данные: `EMPLOYEE`, `DIGEST`.

### Экран 6 — Проверка анализа консультантом
Роль: Консультант. (Веб-версия TASK-025/026 вместо YAML-файла.)
Элементы: карточки процессов с инлайн-редактированием, маркер типа Claim + раскрывающаяся реальная цитата-источник, секции Зрелость/AS-IS-TO-BE/Roadmap/ROI, кнопки «Одобрить и сформировать отчёт» / «Отправить на повторный анализ».
Данные: `PROCESS`, `CLAIM`, `MATURITY_SCORE`, `AS_IS_TO_BE`, `ROADMAP_PHASE`, `ROI_ESTIMATE`. Каждая правка → `REVIEW_EDIT` → TASK-024.

### Экран 7 — Просмотр отчёта
Роль: Клиент (magic-link), Консультант.
Элементы: встроенный просмотрщик HTML-отчёта, кнопки скачивания PDF/DOCX/MD. Данные: `REPORT`.

### Экран 8 — Валидация гипотез
Роль: Клиент.
Элементы: список гипотез (`Claim` типа `HYPOTHESIS`), переключатель Подтверждаю/Отклоняю + комментарий, кнопка «Отправить фидбек».
Действие: → TASK-024 (`CLIENT_VALIDATION`), статус → `CLOSED_COMPLETED`. Данные: `CLAIM`, обновление `BENCHMARK_PATTERN`.

### Экран 9 — Переключатель LLM-провайдера
Роль: Администратор.
Элементы: выпадающий список Провайдер→Модель, текущий активный выделен, индикатор последних ошибок (429), кнопка «Применить».
Данные: `LLM_PROVIDER_CONFIG`. Эффект — на следующий вызов анализа, без перезапуска (TASK-032).

### Экран 10 — Настройка весов скоринга
Роль: Администратор.
Элементы: слайдеры для 5 критериев скоринга (сумма = 100%), порог explainability, порог confidence retrieval.
Особое: влияет только на новые заявки (явное предупреждение).

### Экран 11 — Управление пользователями
Роль: Администратор.
Элементы: таблица пользователей, кнопка «+ Пригласить», деактивация. Данные: `USER`.

### Экран 12 — Статус системы и бэкапов (опционально для MVP)
Роль: Администратор.
Элементы: дата/статус последнего бэкапа, кнопка «Запустить бэкап сейчас», размер эталона.

### Сводная таблица доступа

| № | Экран | Роль | Доступ |
|---|---|---|---|
| 0 | Вход | Консультант, Админ | Логин |
| 1 | Дашборд заявок | Консультант | Логин |
| 2 | Карточка заявки | Консультант/Клиент | Логин/magic-link |
| 3 | Загрузка материалов | Консультант | Логин |
| 4 | Проверка полноты | Консультант | Логин |
| 5 | Анкета сотрудника | Сотрудник | magic-link |
| 6 | Проверка анализа | Консультант | Логин |
| 7 | Просмотр отчёта | Клиент/Консультант | magic-link/Логин |
| 8 | Валидация гипотез | Клиент | magic-link |
| 9 | LLM-провайдер | Админ | Логин |
| 10 | Веса скоринга | Админ | Логин |
| 11 | Пользователи | Админ | Логин |
| 12 | Статус/бэкапы | Админ (опц.) | Логин |

## 9. Карта точек взаимодействия с человеком

| № | Точка | Кто | Действие | Экран/канал |
|---|---|---|---|---|
| 1 | Telegram-бот | Лид | Отвечает на 3 вопроса | Telegram, TASK-023 |
| 2 | Загрузка + подтверждение полноты | Консультант | Загружает файлы, решает «продолжать?» | Экраны 3-4 |
| 3 | Заполнение анкеты/интервью | Сотрудник клиента | Отвечает / даёт интервью | Экран 5 |
| 4 | Точка ручной проверки | Консультант | Правит результаты анализа | Экран 6 |
| 5 | Валидация гипотез | Клиент | Подтверждает/отклоняет | Экран 8 |
| 6 | Переключатель LLM-провайдера | Консультант/Админ | Выбирает модель | Экран 9 |
| 7 | Просмотр статуса заявки | Клиент, Консультант | Пассивный просмотр | Экран 2 |
| + | Админ-панель | Админ | Конфигурация | Экраны 9-12 |

Визуально — `diagrams/service-blueprint.html`.

## 11. Реестр нод исполнения (Execution Flow) — Уровень 2

### 11.1 Методика картирования

Картирование выполнено на Уровне 2 (внутренняя работа продукта, не мета-процесс разработки 5 ролей), по методике, объединяющей три источника:

- **Общая методика картирования AI-агентных систем** — задаёт обязательные поля карточки: роль/задача узла, границы ответственности, используемый инструмент, путь передачи данных.
- **Принципы n8n** — узел (нода) явно фиксирует триггер, вход, выход и критерий готовности; типы узлов: 🟢 Trigger, ⚙️ Action, 🔀 IF/Switch, ⏸ Wait, 🔗 Merge.
- **Anthropic, «Building Effective Agents» (19.12.2024)** — доминирующий паттерн исполнения на Уровне 2 продукта — **Prompt chaining** (жёсткая последовательность шагов), с точечными вкраплениями **Routing** (ветвление: GigaAM→Whisper fallback, бизнес-правило explainability) и явными точками **Wait** (человек в контуре: гейт полноты данных, точка ручной проверки). Паттерн НЕ проставляется отдельным полем на каждую ноду (см. правило ниже) — фиксируется здесь, один раз.

**Правило объединения задач в одну ноду:** несколько TASK-XXX объединяются в одну ноду только если у них нет самостоятельного триггера и самостоятельного критерия готовности — то есть они выполняются строго последовательно без паузы, и промежуточный результат не используется никем, кроме следующего шага внутри этой же цепочки. Применено к TASK-027+028 (chunker + client_document_store → «RAG-индексация документа»). Явно НЕ применено к TASK-019/020/021 (параллельные ветки от одного источника — объединение скрыло бы параллелизм) и к TASK-002/003/004 (разные триггеры: один раз на клиента vs многократно на файл).

**Правило по сквозным сервисам:** узлы, вызываемые множеством других узлов без единственного «предыдущего шага» (TASK-008, 022, 030, 032) показаны полноценными нодами с несколькими входящими связями (пунктиром, для визуального отличия от основного потока данных), а не вынесены в отдельный список — это сохраняет видимость фактической связности системы.

**Правило по избыточной классификации** (закреплено также в `role-claude.md`, 1.6, пункт 9): паттерн Anthropic не проставлен как поле в реестре — при ~29 нодах, где подавляющее большинство относится к одному паттерну (Prompt chaining), это добавило бы шум, а не понимание.

### 11.2 Реестр нод (29 штук)

**Легенда:** 🟢 Trigger · ⚙️ Action · 🔀 IF/Switch · ⏸ Wait · 🔗 Merge

| № | Нода | Тип | Триггер | Ждёт (вход) | Куда идёт результат | Готово (DoD ноды) | Инструмент |
|---|---|---|---|---|---|---|---|
| 1 | Создание проекта клиента (TASK-002) | 🟢 Trigger | Консультант создаёт заявку / лид конвертирован (нода 23) | client_id | Загрузка материала (нода 2) | 5 папок созданы на диске | Python, файловая система |
| 2 | Загрузка материала (TASK-003) | ⚙️ Action | Консультант загружает файл (экран 3) | Структура проекта (нода 1) | Manifest (нода 3) | Оригинал скопирован, хэш совпадает | Python |
| 3 | Manifest (TASK-004) | ⚙️ Action | Материал зарегистрирован (нода 2) | MaterialRecord | Проверка полноты (нода 4) | Строка добавлена в manifest.md | Python, Markdown |
| 4 | Проверка полноты (TASK-007) | ⏸ Wait | Manifest обновлён (нода 3) | manifest.md, список обязательных типов | Решение консультанта (экран 4) → Анкеты (нода 5) / Аудио (нода 6) / статус ПРИОСТАНОВЛЕНО | Консультант нажал «Продолжить» | Python |
| 5 | Генерация анкет (TASK-005) | ⚙️ Action | Консультант подтвердил полноту (нода 4) | Список департаментов, шаблон | Заполнение сотрудником (экран 5, вне схемы) | N+1 файлов-анкет созданы | Python, Markdown |
| 6 | Транскрипция + Digest (TASK-006) | 🔀 IF | Подтверждена полнота (нода 4) ИЛИ аудио прикреплено (экран 5) | Аудиофайл | RAG-индексация (нода 7) | Digest сформирован; при недоступности GigaAM → ветка на Whisper | GigaAM-v3 / Whisper (self-hosted) |
| 7 | RAG-индексация документа (TASK-027+028, объединено) | ⚙️ Action | Материал загружен (нода 2) ИЛИ Digest готов (нода 6) | Текст документа/digest | Retriever (нода 8) | Чанки проиндексированы в изолированной коллекции client_id | ChromaDB, sentence-transformers |
| 8 | Retriever (TASK-029) | ⚙️ Action | Запрос от нод 10, 12, 13, 14 | client_id, текст запроса | Обратно вызывающему модулю | Top-K чанков возвращены или `low_confidence=True` | ChromaDB |
| 9 | Claim / маркировка (TASK-008) | ⚙️ Action *(сквозной сервис)* | Вызывается нодами 10, 12, 13, 14, 17, 24 | Текст утверждения + тип | Обратно вызывающему модулю | Маркер `[ФАКТ]/[ВЫВОД]/...` возвращён | Python |
| 10 | Обнаружение процессов (TASK-009) | ⚙️ Action | RAG-индексация завершена (нода 7) | department_queries, retriever, provider | Скоринг (нода 11) | `ProcessRecord` на департамент сформирован | Gemini/OpenRouter/Groq (нода 29) |
| 11 | Скоринг автоматизации (TASK-010) | ⚙️ Action | Процессы обнаружены (нода 10) | ProcessRecord, веса из конфига | Классификация (12), Карта процессов (15), ROI (18) | ScoredProcess с итоговым баллом | Python |
| 12 | Классификация реализации (TASK-011) | 🔀 IF | Скоринг готов (нода 11) | ScoredProcess, retriever | Зрелость (13), AS-IS/TO-BE (14) | Метка присвоена; блокировка AGENT при низкой explainability | Gemini/OpenRouter/Groq |
| 13 | Оценка зрелости (TASK-012) | ⚙️ Action | Классификация готова для всех процессов (12) | ClassifiedProcess[], retriever | Экспорт на проверку (19) | Итоговый балл 0–5 с обоснованием | Gemini/OpenRouter/Groq |
| 14 | AS-IS / TO-BE (TASK-013) | ⚙️ Action | Классификация готова (12) | ClassifiedProcess, retriever | Экспорт (19), Roadmap (17) | Пара AS-IS/TO-BE сформирована | Gemini/OpenRouter/Groq |
| 15 | Карта процессов (TASK-014) | 🔗 Merge | Скоринг (11) + Классификация (12) готовы | ScoredProcess[], ClassifiedProcess[] | Экспорт (19), Draw.io export (16), Roadmap (17) | Таблица собрана и отсортирована | Python |
| 16 | Экспорт в Draw.io (TASK-015) | ⚙️ Action | Карта процессов готова (15) | ProcessMapTable | Файл для консультанта | Валидный CSV создан | Python |
| 17 | Дорожная карта (TASK-016) | 🔗 Merge | AS-IS/TO-BE (14) + Карта процессов (15) готовы | as_is_to_be, process_map | Экспорт (19) | 3–5 фаз сформированы | Gemini/OpenRouter/Groq |
| 18 | ROI-калькулятор (TASK-017) | ⚙️ Action | Скоринг готов (11) | ScoredProcess[], тарифы из конфига | Экспорт (19) | Диапазон low/high рассчитан | Python |
| 19 | Экспорт на проверку (TASK-025) | ⚙️ Action | Готовы: 13, 14, 15, 17, 18 | Все аналитические результаты + retriever | Точка ожидания консультанта (экран 6) | YAML с реальными цитатами создан | Python, PyYAML |
| 20 | Импорт правок консультанта (TASK-026) | ⏸ Wait | Консультант нажал «Одобрить» (экран 6) | Отредактированные данные экрана 6 | Сборка отчёта (21), Обучение (25) | `ReviewedAnalysisBundle` валиден | Python, PyYAML |
| 21 | Сборка модели отчёта (TASK-018) | 🔗 Merge | Правки импортированы (20) | ReviewedAnalysisBundle | Параллельно: HTML/PDF (22), DOCX (23), MD (24) | ReportModel собран | Python |
| 22 | Рендер HTML/PDF (TASK-019) | ⚙️ Action | ReportModel готов (21) | ReportModel | Просмотр клиентом (экран 7) | HTML+PDF созданы | Jinja2, WeasyPrint |
| 23 | Рендер DOCX (TASK-020) | ⚙️ Action | ReportModel готов (21) | ReportModel | Просмотр консультантом (экран 7) | .docx создан | python-docx |
| 24 | Рендер Markdown (TASK-021) | ⚙️ Action | ReportModel готов (21) | ReportModel | Внутреннее использование | .md создан | Python |
| 25 | Валидация гипотез (TASK-024) | ⚙️ Action *(2 источника)* | Клиент отправил фидбек (экран 8) ИЛИ правки импортированы (20) | Claims + решения, FeedbackSource | Обновление эталона (26) | Confidence обновлён, источник зафиксирован | Python |
| 26 | Хранилище эталона (TASK-022) | ⚙️ Action *(сквозной сервис)* | Обнаружение процессов (10, чтение) ИЛИ Валидация (25, запись) | ProcessPattern / запрос | Обратно ноде 10 | Паттерн сохранён/найден, без сетевых вызовов к OpenAI | ChromaDB, sentence-transformers |
| 27 | Статус заявки (TASK-030) | ⚙️ Action *(сквозной сервис)* | Практически любая нода при завершении шага | application_id, новый статус | Обновление экрана 2 | Переход валиден по матрице, запись в истории | SQLite |
| 28 | Резервное копирование (TASK-031) | 🟢 Trigger | Собственное расписание (cron) | Директории ChromaDB, SQLite, history/ | Второй носитель + ротация | Архив создан на обоих носителях | Python, cron |
| 29 | LLM-провайдер (TASK-032) | ⚙️ Action *(сквозной сервис)* | Запрос от нод 10, 12, 13, 14, 17 ИЛИ администратор (экран 9) | Текущий конфиг из SQLite | Обратно вызывающей ноде | Провайдер возвращён, конфиг читается заново на каждый вызов | Gemini/OpenRouter/Groq, SQLite |

Визуально — `diagrams/execution-flow-diagram.html` (та же информация в форме n8n-подобной схемы с формами узлов по типу).

## 12. Открытые вопросы

1. Декомпозиция экранов веб-приложения (раздел 8) в конкретные код-задачи для DeepSeek (backend-роут + шаблон на экран) — специфицировано, но не декомпозировано. Требует отдельного подтверждения.
2. Сокращение MVP-скоупа экранов — решение не принято.
3. Каскадное удаление данных клиента (файлы + SQLite + векторный индекс) — известный, осознанно принятый пробел.
4. Автоматизация переноса кода DeepSeek в GitHub — решение: Уровень 0 (без автоматизации), GitHub Desktop.
5. Сохранение сырых JSON-ответов DeepSeek как аудиторский след — решение не принято.

## ДЕЛЬТА ИЗМЕНЕНИЙ (относительно v3)

- **ADDED:** раздел 11 — Реестр нод исполнения (Execution Flow), 29 нод, методика картирования (n8n-семантика + паттерны Anthropic), диаграмма `execution-flow-diagram.html`.
- **ADDED:** правила методики картирования — объединение задач в ноду, обработка сквозных сервисов, запрет избыточной классификации (перенесено также в `role-claude.md`, 1.6, пункт 9).
- **MODIFIED:** нумерация разделов (открытые вопросы теперь раздел 12, было 10); таблица диаграмм (раздел 6) дополнена пятой диаграммой.

## ДЕЛЬТА v3 (относительно v2, историческая запись)

- **REMOVED:** все формулировки «см. историю сессии» — заменены полным текстом.
- **ADDED:** полные Given/When/Then, архитектурные ограничения и feature-branch для каждой из 30 задач (раздел 4).
- **MODIFIED:** пути к диаграммам исправлены на конкретное расположение в репозитории (`diagrams/...`) вместо абстрактных имён файлов, добавлено явное предупреждение о необходимости ручного скачивания.

---

**Документ самодостаточен: следующий агент (DeepSeek) может работать по нему без доступа к истории чата.**
