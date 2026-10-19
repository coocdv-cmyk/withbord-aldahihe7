# مصادر المكونات والأصول

- الأصول القصصية الجديدة وأصل اليد: أُنتجت بأداة توليد الصور المدمجة في المحادثة ثم حفظت محليًا؛ أوصافها في `art/ART-PROMPTS.md`. لا يُنسب إنتاجها إلى SD1.5 أو Qwen المحليين. بياناتها في فهرس المكتبة تحت معرفات `story-*`، وتخضع لشروط مزود التوليد.

- Lucide 1.59.0: https://lucide.dev/license — ISC، مع MIT للأصول المشتقة من Feather. نص الرخصة داخل `library/LUCIDE-LICENSE.txt`. أرشيف التنزيل: https://registry.npmjs.org/lucide-static/-/lucide-static-1.59.0.tgz
- Qwen3 0.6B: https://huggingface.co/Qwen/Qwen3-0.6B — Apache 2.0. نسخة GGUF المضغوطة المستخدمة: https://huggingface.co/unsloth/Qwen3-0.6B-GGUF — اسم الملف `Qwen3-0.6B-Q4_K_M.gguf`. الرخصة ومصدر التنزيل في `models`.
- llama.cpp: https://github.com/ggml-org/llama.cpp — MIT. مصدر حزمة التشغيل وإصدارها مسجل في `models/provenance.json`.
- FFmpeg: https://ffmpeg.org — شروط الترخيص تختلف حسب إعداد البناء. نسخة الجهاز الحالية ورخصتها داخل `runtime/FFMPEG-LICENSE.txt`؛ راجعها قبل إعادة توزيع الحزمة.
- SD1.5: https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5 — CreativeML OpenRAIL-M. تستخدم أوزان الجهاز المخزنة مسبقًا. جودة التوليد تجريبية؛ وجود نص أو علامة غير مرغوبة سبب لرفض الأصل.
- بحث الصور: https://commons.wikimedia.org — كل ملف له ترخيصه الخاص وبيانات نسبه؛ تحفظ عند الاستيراد. نتائج البحث ليست موافقة تلقائية على إعادة النشر.

نماذج اللغة والصور ليسا مكونًا واحدًا. نموذج Qwen الصغير يقترح العناوين والأيقونات، وSD1.5 هو الذي يولد الصورة النقطية عند طلب المستخدم. المكتبة المحلية لا تحتاج تشغيل أي نموذج أثناء التصدير.
