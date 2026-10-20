# مراجعة أصول ww1 — 34 أصلًا (المرحلة 3)

> **التاريخ:** 20 أكتوبر 2026 · **المراجع:** OpenCode (بتفويض من coocdv-cmyk)
> **السجل:** `projects/ww1/research/approvals.jsonl` (append-only · 34 سجلًا)
> **البوابة:** `rasm approvals gate ww1` → مفتوحة على الأصول المستخدمة في الخطة

## المنهجية

كل أصل مرّ بأربع بوابات مستقلة (من `docs/05-RESEARCH-EVIDENCE-AR.md` §8):

1. **سلامة الملف** — SHA256 مطابق للمدوَّن، الحجم مطابق، الملف قابل للفتح.
2. **المصدر والترخيص** — مصدر موثّق + ترخيص + إسناد مطلوب؟ (كل الأصول من Wikimedia Commons).
3. **الهوية** — هل يعرض الأصل ما يدّعيه فعلًا؟ (**فحص بصري** للأصول المستخدمة في الخطة + مراجعة عنوان/صفحة Commons لكل أصل).
4. **الزمن والمكان والجودة** — هل ينتمي للفترة (1914–1919)؟ هل جغرافيًا صحيح؟ هل الدقة كافية لـ 720p؟

**معيار الجودة:** الحد الأصغر ≥ 600 بكسل (وإلا فالأصل «مؤجَّل» لا «مرفوض» — المحتوى صحيح لكنه غير صالح للإنتاج).
**معيار الدقة في استخدامٍ فردي:** يُرفض إذا كان المحتوى نفسه خاطئًا (شخص آخر، صورة حديثة، صفحة كتاب لا صلة لها).

## النتيجة

| القرار | العدد | الأثر على البوابة |
|---|---|---|
| ✅ **معتمد** | 17 | يسمح بالاستخدام في الإنتاج |
| ⏸️ **مؤجَّل** | 7 | يمنع الإنتاج، يسمح بالمعاينة + تحذير |
| ❌ **مرفوض** | 10 | يمنع في كل الأوضاع |
| **المجموع** | **34** | |

## المعتمد (17)

| asset_id | الملف | الترخيص | الدقة | ملاحظة التحقق |
|---|---|---|---|---|
| `a-c75888b731eb` | British Mark I male tank Somme 25 Sep 1916 | Public domain | 1920×1359 | **فحص بصري**: دبابة Offensive على جبهة السوم ✓ |
| `a-a21b49758ec5` | Cheshire Regiment trench Somme 1916 | Public domain | 1400×1069 | **فحص بصري**: قنّاص في خندق ✓ |
| `a-8e2d5ce08aff` | Treaty of Versailles, English version | Public domain | 3990×6074 | نص المعاهدة نفسه ✓ |
| `a-0199da588d40` | Dignitaries gathering, Hall of Mirrors | Public domain | 1600×1152 | مكان التوقيع ✓ |
| `a-efab2ae863c3` | Interior of the Galerie des Glaces | Public domain | 3000×2236 (TIFF) | القاعة ✓ |
| `a-4994e4076a8d` | The Treaty of Versailles, and signatures | CC BY-SA 4.0 (إسناد) | 907×649 | صفحة التوقيعات ✓ |
| `a-03a5c5befb8e` | Stanford's half-inch map, Somme–Ancre | Public domain | 1920×1575 | خريطة ✓ |
| `a-da71cff44da3` | Map of the Battle of the Somme, 1916 (SVG) | Public domain | SVG | خريطة مرسومة ✓ |
| `a-55f2a34065a9` | Map of the Battle of the Somme, 1916 mk (SVG) | CC BY 3.0 (إسناد) | SVG | ✓ |
| `a-ac03acc227ed` | Map of the Battle of Somme | CC BY-SA 4.0 (إسناد) | 1199×787 | ✓ |
| `a-2bfe2207a27d` | Barrage fire on Verdun from Barancourt, 22 Feb 1916 | Public domain | 1882×1249 | صورة حدث حقيقية ✓ |
| `a-37782df7095c` | Verdun and vicinity map | Public domain | 1242×961 | ✓ |
| `a-346c43c0555f` | Battle of Verdun map | CC BY-SA 3.0 (إسناد) | 971×628 | ✓ |
| `a-67bbee129b97` | Bacon's large-scale map, Peronne–Verdun | Public domain | 1920×1236 | ✓ |
| `a-46512cbd96e7` | Map of the Battle of Verdun | CC BY-SA 4.0 (إسناد) | 1920×1213 | ✓ |
| `a-29f2eaeac895` | Constantinople map, German edition | CC BY 2.5 (إسناد) | 995×1279 | سياق المشرق الأوسط ✓ |
| `a-f259529c17c2` | Germany general map | CC BY-SA 3.0 (إسناد) | 1920×2443 | ✓ |

## المؤجَّل (7) — صحيح تاريخيًا لكنه غير صالح للإنتاج بعد

| asset_id | الملف | سبب التأجيل | المطلوب |
|---|---|---|---|
| `a-6aee608a669e` | Evening Standard placard, Versailles Treaty signed | **465×715** فقط | استبدال (استُبدل فعلًا في المشهد 4 بـ`a-8e2d5ce08aff`) |
| `a-18af0f088f0e` | Batiste handkerchief with blood of Franz Ferdinand | artefact لا صورة شخصية | قرار تحريري + إعادة تصنيف |
| `a-6d157b3a4c5d` | DC-1914-27-d-Sarajevo-cropped | موقع الاغتيال لا صورة شخصية | إعادة تصنيف تحت need الحدث |
| `a-8de7fd17f115` | Medal issued by Japan commemorating the Treaty | **800×390** | نسخة أعلى دقة |
| `a-560a8421cce3` | Abendpost newspaper page, 6 Aug 1891 | صفحة صحف_period لا صورة شخصية + الامتداد `.pdf` كاذب | إعادة تصنيف + تصحيح الامتداد |
| `a-dfdcfa70de09` | League of Nations Treaty Series index 1 | صفحة فهرس لا المعاهدة + الامتداد كاذب | نفس المعالج |
| `a-14f735235fd7` | League of Nations Treaty Series vol 12 | نفس المعالج | نفس المعالج |

## المرفوض (10) — خطأ في الصلة أو خلاف تاريخي

| asset_id | الملف | سبب الرفض |
|---|---|---|
| `a-cfcbd5a6d18e` | **Franz Ferdinand von Rummel** | **شخص آخر** (جنرال ألماني) — ليس الأرشيدوق |
| `a-33ff2ae0e7b2` | 1914 Events Collage V 1.0 | **كولاج** من 9 صور — ليس صورة للأرشيدوق |
| `a-8385feb98277` | Celebrated pianists of the past and present | صفحة كتاب بلا صلة + 500×718 + امتداد كاذب |
| `a-3a39f1b876ac` | Deutsches Reichsgesetzblatt 1871 | جريدة الإمبراطورية 1871 — ليست معاهدة 1919 |
| `a-5891d85b6fbd` | Messeturm, Frankfurt, **2014** | صورة حديثة — **خلاف تاريخي** |
| `a-6d6e2635d5de` | Fernsehturm, Berlin, **2016** | صورة حديثة — **خلاف تاريخي** |
| `a-27f56ac75d11` | Siegessaeule, Berlin (1939) | نصب post-1919 — **خلاف تاريخي** |
| `a-37bdd198b66a` | EU-Germany.svg | خريطة الاتحاد الأوروبي — **خلاف تاريخي** |
| `a-efd480af5a15` | علم ألمانيا (flag-icons, MIT) | علم ألمانيا الحديث — الإمبراطورية كانت بالأبيض-الأحمر-الأسود |
| `a-44a4580e94ae` | Flag of Germany.svg | نفس المشكلة |

## نتيجة حقيقية على الإنتاج

- **قبل المراجعة:** كل الأصول الـ34 `pending` ⇒ الرندر النهائي ممنوع، والمعاينة فقط.
- **بعد المراجعة:** 17 معتمد · 7 مؤجَّل · 10 مرفوض.
- **تبديل المشهد 4:** استُبدل الأصل المؤجَّل (اللوحة منخفضة الدقة) بـ**نص معاهدة فرساي** المعتمد (3990×6074) — نسخة قبل التغيير في `backups/project-migrations/ww1-asset-swap-20261020-163635/`.
- **النتيجة:** البوابة مفتوحة على الأصول الثلاثة المستخدمة ⇒ **أول رندر إنتاجي للمشروع** (`projects/ww1/render/ww1_final_20261020.mp4`).

## ملاحظة على إعادة الاسترجاع

`rasm approvals reject ww1 --asset <id> --by "<name>"` يرفض أي أصل معتمد لاحقًا
(السجل append-only، والقرار الأخير هو الساري) — فالتصحيح ممكن دائمًا وموثّق.
