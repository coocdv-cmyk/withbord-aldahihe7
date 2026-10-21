"""Regression: «المستخدم» في الخطة = **المرسوم**، لا «المطابق نصًّا».

كان ``assets_used`` يسرد كل أصل تطابق اسم كيانه مع سرد المشهد، حتى لو لم
يُرسم منه عنصر واحد.  النتيجة: أصل **غير مرسوم** كان يُحتسب «مستخدمًا» في
البوابة و��يظهر في الاعتمادات — أي ادعاء نسبة ترخيص لأصل لم يُستعمل.

Here the rule is pinned: an asset counts as used only when a plan element
actually draws it.
"""
from __future__ import annotations

from engine.stages.plan import build_plan


def _research() -> dict:
    return {
        "entities": [
            {
                "name": "خريطة",
                "assets": [
                    {
                        "asset": {
                            "path": "assets/generated/map.svg",
                            "mime": "image/svg+xml",
                            "title": "A generated map",
                            "license": "CC0",
                        }
                    }
                ],
            }
        ]
    }


def test_an_asset_that_is_not_drawn_is_not_used():
    plan = build_plan(
        {
            "lang": "ar",
            "hook": "خريطة",
            "scenes": [
                # scene 1 is the hook: the recipe has no image slot, so the
                # matching asset is *not* drawn even though it matched.
                {"id": 1, "duration": 8.0, "narration": "خريطة الطريق تشرح الطريق"},
                # scene 2 is evidence: the image slot exists and it is drawn
                {"id": 2, "duration": 8.0, "narration": "خريطة الطريق تشرح الطريق"},
                {"id": 3, "duration": 8.0, "narration": "خريطة الطريق تشرح الطريق"},
            ],
        },
        _research(),
    )
    hook, evidence = plan["scenes"][0], plan["scenes"][1]
    assert hook["assets_used"] == [], hook["assets_used"]
    assert not any(el.get("type") in ("image", "svg") for el in hook["elements"])
    assert evidence["assets_used"] == ["assets/generated/map.svg"]
    assert any(el.get("type") in ("image", "svg") for el in evidence["elements"])
