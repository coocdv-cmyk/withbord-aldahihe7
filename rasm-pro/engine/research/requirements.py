"""Scene and subtitle handling plus research requirement construction."""
from __future__ import annotations

import re
from typing import Any

from .evidence import EvidenceKind, ResearchRequirement


def parse_srt(text: str) -> list[dict[str, Any]]:
    cues = []
    blocks = re.split(r"\n\s*\n", (text or "").strip())
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        # index line is optional
        timing_line = lines[1] if "-->" in lines[1] else lines[0]
        if "-->" not in timing_line:
            continue
        left, right = [x.strip() for x in timing_line.split("-->")]
        cue_text = " ".join(lines[2:] if timing_line == lines[1] else lines[1:]).strip()
        cues.append(
            {
                "index": lines[0].strip() if timing_line == lines[1] else "",
                "start": left,
                "end": right,
                "start_seconds": _to_seconds(left),
                "end_seconds": _to_seconds(right),
                "text": cue_text,
            }
        )
    return cues


def _to_seconds(value: str) -> float:
    value = value.replace(",", ".")
    parts = value.split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
    except ValueError:
        return 0.0
    return 0.0


def group_cues(cues: list[dict[str, Any]], *, max_words: int = 45, max_gap_seconds: float = 1.5) -> list[dict[str, Any]]:
    units = []
    current = []
    for cue in cues:
        if current:
            gap = cue["start_seconds"] - current[-1]["end_seconds"]
            words = sum(len(c["text"].split()) for c in current) + len(cue["text"].split())
            if gap <= max_gap_seconds and words <= max_words:
                current.append(cue)
                continue
            units.append(_make_unit(current, len(units) + 1))
            current = [cue]
        else:
            current = [cue]
    if current:
        units.append(_make_unit(current, len(units) + 1))
    return units


def _make_unit(cues: list[dict[str, Any]], unit_number: int) -> dict[str, Any]:
    return {
        "unit_id": f"u{unit_number}",
        "cue_indices": [c.get("index") for c in cues],
        "start": cues[0]["start"],
        "end": cues[-1]["end"],
        "start_seconds": cues[0]["start_seconds"],
        "end_seconds": cues[-1]["end_seconds"],
        "text": " ".join(c["text"] for c in cues).strip(),
        "word_count": sum(len(c["text"].split()) for c in cues),
    }


def _asset_type_for_need(need: str) -> str:
    mapping = {
        "portrait": "portrait",
        "event": "event_image",
        "map": "map",
        "flag": "flag",
        "document": "document",
        "object": "object",
        "symbol": "contextual_image",
        "chart": "chart",
    }
    return mapping.get(need, "contextual_image")


def _evidence_kind(asset_type: str) -> str:
    if asset_type in {"document", "title_page", "manuscript"}:
        return EvidenceKind.DIRECT.value
    if asset_type in {"portrait", "map", "flag", "object", "event_image"}:
        return EvidenceKind.CONTEXTUAL.value
    if asset_type == "contextual_image":
        return EvidenceKind.ILLUSTRATION.value
    return EvidenceKind.BROLL.value


def requirements_from_script(graph: dict[str, Any], *, units: list[dict[str, Any]] | None = None) -> list[ResearchRequirement]:
    """Build scene-level requirements from a ScriptGraph.

    The function is deterministic and intentionally conservative.  Qwen may later
    propose refinements, but every requirement must already have mandatory
    conditions and rejection rules before model assistance is considered.
    """
    requirements: list[ResearchRequirement] = []
    scenes = graph.get("scenes", []) or []
    if units:
        # Preserve unit linkage while still using scene-level needs when available.
        scene_by_text = {str(s.get("narration", "")).strip(): s for s in scenes}
    else:
        units = [{"unit_id": f"s{s.get('id')}", "text": s.get("narration", ""), "scene_id": s.get("id")} for s in scenes]

    for unit in units:
        unit_id = str(unit.get("unit_id") or unit.get("id") or "")
        scene_id = str(unit.get("scene_id") or unit.get("scene") or unit_id)
        scene = None
        for s in scenes:
            if str(s.get("id")) == scene_id:
                scene = s
                break
        if scene is None:
            # Best-effort match by narration text.
            for s in scenes:
                if str(s.get("narration", "")).strip() == str(unit.get("text", "")).strip():
                    scene = s
                    break

        needs = list(scene.get("needs", []) if scene else [])
        if not needs:
            needs = ["symbol"]
        entities = [e for e in (graph.get("entities", []) or []) if scene is None or scene.get("id") in (e.get("scenes") or [scene.get("id")])]
        if not entities:
            entities = graph.get("entities", []) or []

        for need_index, need in enumerate(needs[:6], 1):
            asset_type = _asset_type_for_need(need)
            entity_name = ""
            alternative_names = []
            if entities:
                # Prefer an entity whose needs include this need.
                chosen = None
                for e in entities:
                    if need in (e.get("needs") or []):
                        chosen = e
                        break
                chosen = chosen or entities[min(need_index - 1, len(entities) - 1)]
                entity_name = str(chosen.get("name", "")).strip()
                alternative_names = [str(x).strip() for x in (chosen.get("alternative_names") or []) if str(x).strip()]
            req_id = f"req-{scene_id or 'scene'}-{need}-{need_index}"
            req = ResearchRequirement(
                id=req_id,
                scene_id=scene_id or "unknown",
                unit_id=unit_id or scene_id or "unknown",
                excerpt=str(unit.get("text") or (scene.get("narration") if scene else "") or "").strip()[:500],
                purpose=f"Visual support for scene {scene_id}: {need}",
                asset_type=asset_type,
                entity=entity_name,
                alternative_names=alternative_names,
                time_context=_time_context(graph, scene),
                location=_location_context(graph, scene),
                mandatory=_mandatory_for(asset_type),
                optional=_optional_for(asset_type),
                rejection=_rejection_for(asset_type),
                minimum_evidence=_minimum_evidence_for(asset_type),
                quality={"min_width": 640, "readable_at_final_size": True},
                importance=_importance_for(need, scene),
                priority=_priority_for(need),
                evidence_kind=_evidence_kind(asset_type),
                chronology=__import__("engine.research.identity", fromlist=["parse_chronology"]).parse_chronology(_time_context(graph, scene)),
            )
            requirements.append(req)
    return requirements


def _time_context(graph: dict[str, Any], scene: dict[str, Any] | None) -> str:
    if scene and scene.get("when"):
        return str(scene["when"])
    timeline = graph.get("timeline") or []
    if timeline:
        return str(timeline[0].get("when", ""))
    dates = graph.get("numbers") or []
    return str(dates[0]) if dates else ""


def _location_context(graph: dict[str, Any], scene: dict[str, Any] | None) -> str:
    entities = graph.get("entities") or []
    for e in entities:
        if e.get("type") in {"city", "country"}:
            return str(e.get("name", ""))
    return ""


def _mandatory_for(asset_type: str) -> list[str]:
    base = ["identity of the depicted subject or work"]
    if asset_type in {"document", "title_page", "manuscript"}:
        base += ["edition or translation identity", "source page or catalog record", "access level"]
    if asset_type in {"portrait", "event_image"}:
        base += ["date of creation distinguished from event date", "depiction vs. subject distinction"]
    if asset_type == "map":
        base += ["geographic scope", "date of map"]
    return base


def _optional_for(asset_type: str) -> list[str]:
    return ["higher resolution", "better crop", "contemporary depiction", "additional context"]


def _rejection_for(asset_type: str) -> list[str]:
    rules = ["wrong identity", "wrong period", "wrong location"]
    if asset_type in {"portrait", "event_image"}:
        rules += ["modern depiction presented as contemporary", "artwork of a different subject"]
    if asset_type in {"document", "title_page", "manuscript"}:
        rules += ["different edition", "different translation", "cover not title page"]
    return rules


def _minimum_evidence_for(asset_type: str) -> list[str]:
    if asset_type in {"document", "title_page", "manuscript"}:
        return ["source URL", "catalog or page evidence", "content hash"]
    return ["source URL", "source metadata", "content hash"]


def _importance_for(need: str, scene: dict[str, Any] | None) -> str:
    if need in {"document", "portrait"}:
        return "high"
    if need in {"map", "event"}:
        return "medium"
    return "low"


def _priority_for(need: str) -> int:
    return {"document": 10, "portrait": 20, "map": 30, "event": 40, "object": 50,
            "flag": 60, "chart": 70, "symbol": 80, "contextual_image": 90}.get(need, 99)
