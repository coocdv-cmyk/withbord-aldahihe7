import sys,json
import audit
from engine.research.local_library import search_icons
print(json.dumps(search_icons(sys.argv[1].split(),limit=5),ensure_ascii=False))
