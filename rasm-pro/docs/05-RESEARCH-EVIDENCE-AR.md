# بحث الأدلة واقتناء الأصول (Research Evidence)

## 1. الهدف

نظام بحث مسنّد داخل `rasm-pro` (وليس في Studio القديم) يدعم إنتاج الفيديو العربي/الإنجليزي من سكريبت ومصادر اختيارية. يحدد متطلبات كل مشهد، يبحث في المصادر، يكتشف مرشحات، يتحقق من هوية السياق، يحفظ الأدلة، ويبلّغ عن غير المحسوم honstly.

Qwen3-4B هو مساعد لغوي مقيّد، وليس سلطة نهائية على الحقائق أو الهوية أو الترخيص.

## 2. الأوامر

```powershell
# فحص Qwen 4B
python rasm.py llm-status

# بحث مسنّد (بدون تنزيل)
python rasm.py evidence <project> --max-seconds 300 --max-requests 60 --max-pages 60 --max-llm-calls 24

# مع تنزيل المرشحات المسموح بها
python rasm.py evidence <project> --download

# من SRT
python rasm.py evidence <project> --srt script.srt --language ar

# من روابط مصادر
python rasm.py evidence <project> --source-url "https://example.com/source" --source-url "https://example.com/other"

# من مستندات محلية
python rasm.py evidence <project> --doc "D:\\path\\source.pdf"
```

الرندر remains منفصلًا: after research, run `rasm plan` and `rasm render`.

## 3. المخرجات

- `projects/<name>/research/evidence.json`: حالة كاملة (متطلبات، مصادر، مرشحات، أدلة، استعلامات، قرارات، ميزانية).
- `projects/<name>/research/evidence_summary.json`: ملخص قابل للقراءة.
- `projects/<name>/research/evidence_state.json`: حالة قابلة للاستئناف.
- `projects/<name>/research/assets.json` and `CREDITS.md` عند التزيل.
- `projects/<name>/assets/...`: أصول منزّلة (منفصلة عن derivatives).

## 4. تشغيل بدون نموذج

إذا كان Qwen غير متاح، البحث الحتمي (Wikipedia/Wikidata/Commons/مكتبة محلية) يستمر، وتُسجّل حالة `assistant_status=connection_error` (أو `auth_401`/`auth_403`). لا يُبلّغ عن ذلك كإنجاز مكافئ.

## 5. إعداد Qwen 4B

```powershell
$env:RASM_RESEARCH_LLM_BASE_URL="http://127.0.0.1:11435/v1"
$env:RASM_RESEARCH_LLM_API_KEY="<key>"
$env:RASM_RESEARCH_LLM_MODEL="studio\\models\\Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
$env:RASM_RESEARCH_LLM_MODEL_PATH="D:\\withbord inmation\\studio\\models\\Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
python rasm.py llm-status
```

`llm-status` distinguishes connection failure, HTTP 401, HTTP 403, server error, and successful access. It records model path and size; hashing is skipped for large files unless small.

## 6. أمان المصادر

- روابط ناقصة (`...`) تُرفض، لا يُخمّن الباقي.
- hosts محلية/خاصة تُرفض (SSRF protection).
- قيود على bytes/timeout/retries/concurrency.
- صفحات الويب treated as untrusted data, not instructions.
- لا bypass لـ paywalls/auth.
- access level recorded: full text, abstract, summary, preview, metadata only, unavailable, restricted.

## 7. قراءة المستندات

- HTML: text extraction + links.
- PDF: pypdf or pymupdf if installed (optional).
- EPUB: zipfile + HTML.
- IIIF: manifest parser (version varies by institution).
- OCR is not implemented as a hard dependency; scanned PDFs report reader unavailable rather than inventing text.

File-page index is distinguished from printed page number where the reader provides it.

## 8. بوابات التحقق

Each candidate is evaluated separately for:
- identity
- time
- location
- relevance
- quality
- provenance
- usage
- evidence

A high-resolution image does not compensate for wrong identity. Missing metadata remains missing.

## 9. النماذج/الوحدات

- `engine/research/evidence.py`: contracts.
- `engine/research/identity.py`: chronology (BCE, centuries, ranges), names.
- `engine/research/requirements.py`: SRT grouping and requirement construction.
- `engine/research/urls.py`: URL safety and bounded fetching.
- `engine/research/readers.py`: document readers.
- `engine/research/discovery.py`: replaceable providers.
- `engine/research/verification.py`: mandatory gates.
- `engine/research/assistant.py`: bounded Qwen tasks.
- `engine/research/workflow.py`: iterative, resumable research.

## 10. tested sources/formats

Live-tested in this environment:
- Wikipedia (ar/en)
- Wikidata
- Wikimedia Commons
- local icon library (after optimized index build)
- user-provided URLs (complete only)
- HTML pages

Not live-tested here:
- PDF text extraction (optional dependency not in rasm-pro venv)
- EPUB
- IIIF manifests
- scanned PDF OCR
- authenticated sources

## 11. limitations

- No claim of complete internet coverage.
- No universal website support.
- No 100% correctness.
- Qwen availability and auth affect query drafting only; deterministic research continues without it.
- Image content is not verified by the text model; human review remains required.
- Candidate approval is not automatic; review state starts as `review_required`.
- Network quality and provider limits affect results.

## 12. tests

```powershell
python -m pytest tests/test_research_evidence.py -q
```

Covers SRT grouping, URL validation, SSRF, chronology, verification, no-network workflow, resume, and explicit assistant unavailability.
