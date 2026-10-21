"""منسّق البحث: ScriptGraph → حقائق + أصول حقيقية مرخّصة + منشأ.

المسار لكل كيان:
  1) Wikidata: بحث (باسم مُنقّى + سياق + تواريخ السكريبت) → أفضل QID → حقائق
     (صورة P18، علم P41، خريطة P242، تواريخ، إحداثيات، ISO2…)
  2) Wikipedia: ملخّص للسياق + rescue للـQID عبر sitelink
  3) لكل احتياج بصري: استعلامات بأسماء (إنجليزي أولًا) → Commons → بوابة ترخيص → تنزيل
  4) الأعلام: flag-icons (MIT) + علم Wikidata
  5) الرموز (symbol): مكتبة الأيقونات المحلية (318 ألف أصل)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..core.config import load_config
from ..core.log import get_logger
from ..core.util import write_json
from ..memory.lexicon import Lexicon, is_generic_collective, looks_like_work
from ..research.commons import Commons
from ..research.http import HttpClient, RateLimited
from ..research.local_library import search_icons
from ..research.rights import classify_license
from ..research.store import AssetStore
from ..research.wikidata import Wikidata
from ..research.wikipedia import Wikipedia

log = get_logger("research")

FLAG_ICONS = "https://cdn.jsdelivr.net/npm/flag-icons@7.2.3/flags/4x3/{cc}.svg"

# أنواع Wikidata المتوقعة لكل نوع كيان (لترجيح المطابقة الصحيحة)
EXPECTED_TYPES: dict[str, list[str]] = {
    "person": ["Q5"],
    "country": ["Q6256", "Q3624078", "Q7275", "Q3024240"],
    "city": ["Q515", "Q1549591", "Q1637706", "Q3957", "Q486972"],
    "org": ["Q43229", "Q178706", "Q4830453", "Q327333"],
    "event": ["Q1656682", "Q178561", "Q10931", "Q131569", "Q198", "Q350604"],
    "object": ["Q39546", "Q1183543", "Q11424"],
    "document": ["Q131569", "Q49848"],
}

PERSON_TITLE_PREFIXES = (
    "الأرشيدوق", "الملك", "الملكة", "الرئيس", "الزعيم", "القائد", "الإمبراطور", "السلطان",
    "الخليفة", "الأمير", "الجنرال", "الدكتور", "المهندس", "العالم", "الكاتب", "الفيلسوف",
    "البابا", "المستشار", "الوزير", "المارشال", "الشيخ", "العلامة", "المفكر", "المؤرخ",
    "فيلد مارشال", "الباشا",
)

QUERY_TEMPLATES: dict[str, list[str]] = {
    "portrait": ["{name} portrait", "{name}"],
    "event": ["{name}", "{name} photo"],
    "map": ["{name} map", "{name} locator map"],
    "document": ["{name} document", "{name}"],
    "object": ["{name}"],
}

TYPE_PRIORITY = {"person": 0, "event": 1, "country": 2, "city": 3, "org": 4, "object": 5, "concept": 6, "date": 9}


def _strip_title(name: str) -> str:
    for t in PERSON_TITLE_PREFIXES:
        if name.startswith(t + " "):
            return name[len(t) + 1 :].strip()
    return name


def _token_set(s: str) -> set[str]:
    return {w for w in re.split(r"[^\w\u0600-\u06FF]+", (s or "").lower()) if len(w) > 3}


def _similar_token(a: str, b: str) -> bool:
    """تشابه عربي/لاتيني متسامح مع الاختلافات الإملائية (فردناند ↔ فرديناند)."""
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    if a.startswith(b[:4]) or b.startswith(a[:4]):
        import difflib

        return difflib.SequenceMatcher(None, a, b).ratio() >= 0.72
    return False


def _name_overlap(a: str, b: str) -> bool:
    for x in _token_set(a):
        for y in _token_set(b):
            if _similar_token(x, y):
                return True
    return False


def _norm_title(t: str) -> str:
    return (t or "").lower().replace("file:", "").replace("_", " ").strip()


def _title_relevant(title: str, names: list[str]) -> bool:
    tt = _token_set(_norm_title(title))
    return any(_token_set(n) & tt for n in names)


def _era_hit(wd: Wikidata, facts: dict | None, years: list[int]) -> bool:
    if not facts or not years:
        return False
    return wd.era_score(facts, years) > 0


def _script_years(script_dates: list[str]) -> list[int]:
    out = []
    for d in script_dates:
        m = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", str(d))
        if m:
            y = int(m.group(1))
            if y not in out:
                out.append(y)
    return out


def _query_names(entity: dict, facts: dict | None, wiki: dict | None) -> list[str]:
    """أسماء البحث: إنجليزي أولًا (كومنز أفضل بالإنجليزية) ثم العربي."""
    names: list[str] = []
    if facts:
        for key in ("label_en", "label"):
            v = (facts.get(key) or "").strip()
            if v and v not in names:
                names.append(v)
    if wiki and wiki.get("title"):
        t = wiki["title"].strip()
        if t and t not in names:
            names.append(t)
    stripped = _strip_title(entity.get("name", ""))
    for n in (stripped, entity.get("name", "")):
        n = (n or "").strip()
        if n and n not in names and not any(n in x for x in names):
            names.append(n)
    return names[:3]


def resolve_entity(entity: dict, *, wd: Wikidata, wiki: Wikipedia, cfg, script_dates: list[str]) -> dict:
    """كيان → حقائق ويكي بيانات + سياق ويكيبيديا (+ أسماء بحث).

    المنهج: ويكيبيديا أولًا (الأدق في تمييز الأسماء العربية/المتشابهة)،
    ثم تصحيح زمني من ويكي بيانات إذا كان السياق التاريخي يرجّح كيانًا آخر
    (مثال: «ألمانيا» في سكريبت 1914 → الرايخ الألماني).
    """
    lex = Lexicon.load()
    name = entity.get("name", "")
    context = " ".join([entity.get("context", ""), entity.get("why", "")]).strip()
    langs = cfg.get("research", "langs", default=["ar", "en"])
    years = _script_years(script_dates)
    stripped = _strip_title(name)

    # ذاكرة التعلّم: نوع مُصحَّح + اسم مرجعي أدق (بريطانيا → المملكة المتحدة)
    etype = lex.type_fix(name) or entity.get("type")
    if etype == "person" and is_generic_collective(name):
        etype = "concept"  # «الجنود/القوات»: لا بورتريه شخص ولا مطابقة أفلام
    ref = lex.alias(name) or lex.alias(stripped) or stripped

    out: dict[str, Any] = {"entity": entity, "facts": None, "wikipedia": None, "query_names": []}

    # 1) ويكيبيديا أولًا → QID عبر sitelink → حقائق
    avoid = (
        ["اغتيال", "معركة", "حرب", "ثورة", "مذبحة", "انقلاب", "هجوم", "مؤتمر", "معاهدة", "اتفاقية", "قضية", "حادثة", "عملية", "حصار"]
        if etype == "person"
        else None
    )
    wiki_info: dict | None = None
    facts_wiki: dict | None = None
    s = wiki.best_summary(ref, langs=langs, avoid=avoid)
    if s and s.get("title"):
        qid = wd.by_sitelink(s.get("lang", "ar"), s["title"])
        if qid:
            f = wd.facts(qid)
            if (
                f
                and not looks_like_work(f.get("description") or "")
                and (_name_overlap(f.get("label") or "", ref) or _name_overlap(s["title"], ref))
            ):
                facts_wiki = f
                wiki_info = s

    # 2) ويكي بيانات بالسياق والتواريخ
    facts_wd: dict | None = None
    if etype in ("person", "country", "city", "event", "org", "object", "concept"):
        facts_wd = wd.resolve(
            name,
            context=context,
            dates=script_dates,
            expected_types=EXPECTED_TYPES.get(etype, []),
            search_names=list(dict.fromkeys([ref, stripped, name])),
        )
        if facts_wd and (
            not (_name_overlap(facts_wd.get("label") or "", ref) or _name_overlap(facts_wd.get("label_en") or "", ref))
            or looks_like_work(facts_wd.get("description") or "")
        ):
            facts_wd = None

    # 3) الحكم: أيّهما أفضل (السياق الزمني يحسم عند التعارض)
    facts = facts_wiki
    if facts_wd:
        wiki_era = _era_hit(wd, facts_wiki, years)
        wd_era = _era_hit(wd, facts_wd, years)
        if facts is None or (wd_era and not wiki_era) or (
            wd_era == wiki_era and float(facts_wd.get("match_score") or 0) > 6 and (facts_wd.get("qid") != facts.get("qid"))
        ):
            facts = facts_wd

    # ملخص سياق مطابق للكيان المختار
    if facts and (not wiki_info or (facts.get("qid") != (facts_wiki or {}).get("qid"))):
        sitelinks = facts.get("sitelinks") or {}
        for key in ("arwiki", "enwiki"):
            title = sitelinks.get(key)
            if title:
                ss = wiki.summary(title, lang=key[:2])
                if ss and ss.get("extract"):
                    ss["lang"] = key[:2]
                    wiki_info = ss
                    break

    out["facts"] = facts
    out["wikipedia"] = wiki_info
    out["query_names"] = _query_names(entity, facts, wiki_info)
    return out


def _candidates_for_need(entity: dict, need: str, resolved: dict, *, commons: Commons, cfg, era_year: int | None) -> list[dict]:
    """مرشّحات أصول لاحتياج معيّن (قبل بوابة الترخيص)، بلا تكرار."""
    name = entity.get("name", "")
    facts = resolved.get("facts") or {}
    query_names = resolved.get("query_names") or [name]
    cands: list[dict] = []

    def push(c: dict):
        title = (c.get("title") or c.get("url") or "")[:200]
        if title and any((x.get("title") or x.get("url") or "")[:200] == title for x in cands):
            return
        cands.append(c)

    if need == "flag":
        iso2 = (facts.get("iso2") or "").lower()
        if iso2 and len(iso2) == 2 and iso2.isalpha():
            push({"url": FLAG_ICONS.format(cc=iso2), "title": f"علم {name}", "license": "MIT",
                  "license_url": "https://github.com/lipis/flag-icons/blob/master/LICENSE",
                  "source": "flag-icons", "mime": "image/svg+xml", "kind": "flag",
                  "page_url": "https://github.com/lipis/flag-icons", "is_vector": True})
        if facts.get("flag_url"):
            push({"url": facts["flag_url"], "title": f"علم {name} (كومنز)", "source": "Wikimedia Commons",
                  "kind": "flag", "page_url": facts["flag_url"], "license": None, "needs_license_lookup": True,
                  "mime": "image/svg+xml", "is_vector": True})
        return cands

    if need == "symbol":
        kws = [k for k in [facts.get("label_en"), *(resolved.get("query_names") or [])] if k and k.isascii()]
        kws += [k for k in (entity.get("keywords") or []) if k.isascii()]
        if not kws:
            return cands
        icons = search_icons(kws[:3], limit=int(cfg.get("research", "max_assets_per_need", default=3)))
        for ic in icons:
            push({"local_path": ic["file"], "title": ic["name"], "source": f"iconify/{ic['set']}",
                  "license": ic.get("license"), "kind": "icon", "attr": ic.get("attr"),
                  "page_url": None, "mime": "image/svg+xml", "is_vector": True})
        return cands

    # صور Wikidata المباشرة (أولوية)
    if need == "portrait" and facts.get("image_url"):
        push({"url": facts["image_url"], "title": facts.get("image", ""), "source": "Wikimedia Commons",
              "kind": need, "page_url": facts["image_url"], "license": None, "needs_license_lookup": True})
    if need == "map" and facts.get("locator_map_url"):
        push({"url": facts["locator_map_url"], "title": facts.get("locator_map", ""), "source": "Wikimedia Commons",
              "kind": "map", "page_url": facts["locator_map_url"], "license": None, "needs_license_lookup": True,
              "is_vector": str(facts.get("locator_map", "")).lower().endswith(".svg")})
    if need == "event" and facts.get("image_url"):
        push({"url": facts["image_url"], "title": facts.get("image", ""), "source": "Wikimedia Commons",
              "kind": "event", "page_url": facts["image_url"], "license": None, "needs_license_lookup": True})

    templates = list(QUERY_TEMPLATES.get(need, []))
    if era_year and need in ("event", "map") and templates:
        templates.append(templates[-1] + f" {era_year}")
    if not templates:
        return cands

    want = max(2, int(cfg.get("research", "max_assets_per_need", default=3))) + 2
    seen_titles: set[str] = set()
    for tpl in templates[:3]:
        for qname in query_names[:2]:
            q = tpl.format(name=qname)
            try:
                found = commons.find_images(q, limit=min(8, want))
            except Exception as e:
                log.warning("فشل بحث كومنز '%s': %s", q, e)
                continue
            for f in found:
                mime = str(f.get("mime") or "")
                if mime and not mime.startswith("image/"):
                    continue  # لا كتب PDF/فيديو/صوت
                t = f.get("title") or ""
                nkey = _norm_title(t)
                if nkey in seen_titles:
                    continue
                if not _title_relevant(t, query_names):
                    continue
                seen_titles.add(nkey)
                f = dict(f)
                f["kind"] = need
                f["source"] = "Wikimedia Commons"
                f["query"] = q
                push(f)
            if len(cands) >= want * 2:
                return cands
    return cands


def _fetch_license_for_file(commons: Commons, filename: str) -> dict:
    try:
        infos = commons.file_info([f"File:{filename}"], thumb_width=1600)
        return infos[0] if infos else {}
    except Exception:
        return {}


def _era_year(resolved: dict, script_dates: list[str]) -> int | None:
    """أفضل سنة سياق للكيان (من ويكي بيانات ثم من السكريبت)."""
    facts = resolved.get("facts") or {}
    for k in ("start", "inception", "end", "birth", "death"):
        y = Wikidata._year_of(facts.get(k))
        if y:
            return y
    for d in script_dates:
        y = Wikidata._year_of(d)
        if y:
            return y
    return None


def research_script(graph: dict, project_dir, *, cfg=None, max_entities: int = 14, download: bool = True) -> dict:
    """ينفّذ البحث الكامل ويكتب research.json + CREDITS.md + assets.json."""
    cfg = cfg or load_config()
    ua = cfg.get("research", "user_agent", default="rasm-pro/0.1 (whiteboard video engine; contact: local)")
    client = HttpClient(ua, timeout=int(cfg.get("research", "download_timeout", default=45)))
    wd = Wikidata(client)
    wiki = Wikipedia(client)
    commons = Commons(client)
    store = AssetStore(project_dir, client)

    min_w = int(cfg.get("research", "min_image_width", default=500))
    max_per_need = int(cfg.get("research", "max_assets_per_need", default=3))
    max_examined = int(cfg.get("research", "max_candidates_per_need", default=8))
    allow_sa = bool(cfg.get("research", "allow_sharealike", default=True))
    script_dates = [t.get("when", "") for t in graph.get("timeline", []) if t.get("when")]

    entities = sorted(
        graph.get("entities", []),
        key=lambda e: (TYPE_PRIORITY.get(e.get("type", "concept"), 7), e.get("name", "")),
    )[:max_entities]

    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": project_dir.name,
        "entities": [],
        "skipped": [],
        "totals": {"downloaded": 0, "reused": 0, "denied": 0},
    }

    for ent in entities:
        log.info("كيان: %s (%s)", ent.get("name"), ent.get("type"))
        try:
            resolved = resolve_entity(ent, wd=wd, wiki=wiki, cfg=cfg, script_dates=script_dates)
        except RateLimited as exc:
            # The source asked us to slow down.  Saying "no assets found" here
            # would be a lie: we did not look.
            log.warning("توقّف البحث عن %s: المصدر طلب الإبطاء (%s)", ent.get("name"), exc)
            result["skipped"].append(
                {"entity": ent.get("name"), "need": "*", "title": "", "why": "rate-limited"}
            )
            result["totals"]["rate_limited"] = int(result["totals"].get("rate_limited", 0)) + 1
            continue
        ent_out = {
            "name": ent.get("name"),
            "type": ent.get("type"),
            "needs": ent.get("needs", []),
            "facts": resolved.get("facts"),
            "wikipedia": ((resolved.get("wikipedia") or {}).get("extract") or "")[:600],
            "query_names": resolved.get("query_names", []),
            "assets": [],
        }
        era = _era_year(resolved, script_dates)

        for need in ent.get("needs", [])[:4]:
            got = 0
            examined = 0
            for cand in _candidates_for_need(ent, need, resolved, commons=commons, cfg=cfg, era_year=era):
                if got >= max_per_need:
                    break
                # Every candidate that needs a license lookup costs one Commons
                # call.  A broad search can return dozens of candidates, and
                # scanning all of them made a single entity take minutes.
                # The examined candidates are capped and the rest are declared
                # as skipped — never silently dropped.
                if examined >= max_examined:
                    result["skipped"].append(
                        {
                            "entity": ent.get("name"),
                            "need": need,
                            "title": cand.get("title"),
                            "why": f"تجاوز{max_examined} مرشّحًا مفحوصًا",
                        }
                    )
                    result["totals"]["denied"] += 1
                    break
                examined += 1

                if cand.get("needs_license_lookup"):
                    fname = (cand.get("url") or "").split("FilePath/")[-1].split("?")[0]
                    info = _fetch_license_for_file(commons, fname) if fname else {}
                    if info:
                        cand.update(
                            {
                                "license": info.get("license") or cand.get("license"),
                                "license_url": info.get("license_url"),
                                "artist": info.get("artist"),
                                "page_url": info.get("page_url") or cand.get("page_url"),
                                "title": cand.get("title") or info.get("title"),
                                "width": info.get("width"),
                                "height": info.get("height"),
                                "uploader": info.get("uploader"),
                                "mime": info.get("mime") or cand.get("mime"),
                                "is_vector": bool(info.get("is_vector") or cand.get("is_vector")),
                            }
                        )
                        # SVGs الأصلية تُنزّل كمتجهات (جودة لا نهائية + محرك مسارات)
                        if info.get("is_vector") and info.get("url"):
                            cand["url"] = info["url"]
                        elif info.get("thumb_url"):
                            cand["url"] = info["thumb_url"]

                decision = classify_license(cand.get("license"), cand.get("license_url"), allow_sharealike=allow_sa)
                if not decision.allow:
                    result["skipped"].append({"entity": ent.get("name"), "need": need, "title": cand.get("title"), "why": decision.reason})
                    result["totals"]["denied"] += 1
                    continue

                w = cand.get("width")
                is_vector = bool(cand.get("is_vector")) or str(cand.get("mime", "")).endswith("svg")
                if w and int(w) < min_w and not is_vector and need in ("portrait", "event", "map"):
                    result["skipped"].append({"entity": ent.get("name"), "need": need, "title": cand.get("title"), "why": f"دقة منخفضة ({w}px)"})
                    continue

                if not download:
                    ent_out["assets"].append({"candidate": cand, "decision": decision.dict()})
                    got += 1
                    continue

                meta = {
                    "title": cand.get("title"),
                    "author": cand.get("artist") or cand.get("uploader"),
                    "license": cand.get("license"),
                    "license_url": cand.get("license_url"),
                    "page_url": cand.get("page_url"),
                    "source": cand.get("source"),
                    "entity": ent.get("name"),
                    "entity_type": ent.get("type"),
                    "need": need,
                    "query": cand.get("query"),
                    "decision": decision.level,
                    "era": era,
                    "attr": bool(cand.get("attr") or decision.needs_attribution),
                }
                rec = None
                if cand.get("local_path"):
                    rec = store.add_local(cand["local_path"], kind="icon", record_meta=meta)
                elif cand.get("url"):
                    rec = store.download(cand["url"], kind=cand.get("kind", need),
                                         subdir=f"{ent.get('type')}-{ent.get('name', '')[:24]}",
                                         mime=cand.get("mime"), record_meta=meta)
                if rec:
                    ent_out["assets"].append({"asset": rec, "decision": decision.dict()})
                    if rec.get("reused"):
                        result["totals"]["reused"] += 1
                    else:
                        result["totals"]["downloaded"] += 1
                    got += 1

        # تنقية التكرار على مستوى الكيان (نفس الملف من أكثر من استعلام)
        seen_sha: set[str] = set()
        uniq_assets = []
        for a in ent_out["assets"]:
            sha = (a.get("asset") or {}).get("sha256")
            if sha and sha in seen_sha:
                continue
            if sha:
                seen_sha.add(sha)
            uniq_assets.append(a)
        ent_out["assets"] = uniq_assets

        result["entities"].append(ent_out)

    store.write_credits()
    write_json(project_dir / "research" / "research.json", result)
    log.info(
        "اكتمل البحث: %d كيان · %d تنزيل · %d إعادة استخدام · %d مرفوض",
        len(result["entities"]),
        result["totals"]["downloaded"],
        result["totals"]["reused"],
        result["totals"]["denied"],
    )
    return result
