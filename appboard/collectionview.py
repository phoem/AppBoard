"""Compile a read-only collection view to the ordinary portable native drawing API."""
import json
import re
from pathlib import Path

COLLECTION_FIELDS = ("collection", "labelField", "imageField", "emptyText")
RENDER = (Path(__file__).with_name("assets") / "collection.js").read_text(encoding="utf-8")


def is_collection_request(context):
    if "fromPage" not in context or "currentPage" in context:
        return False
    brief = context["request"].strip().casefold()
    # New navigation controls can declare any collection. Recognize only bare
    # browsing requests from older saved apps; qualified requests may need custom UI.
    return (brief.startswith("browse collection:") or
            re.fullmatch(r"(?:view|browse|open|show) (?:the |my )?(?:gallery|album|directory|catalog|list)[.!]?", brief)
            is not None)


def collection_script(name, view, *, default_key=""):
    if (not isinstance(view, dict) or set(view) != set(COLLECTION_FIELDS) or
            not all(isinstance(v, str) and len(v) <= 256 for v in view.values()) or
            not (view["collection"].strip() or default_key)):
        raise ValueError("A collection view needs a data key, field names and an empty-state message.")
    config = json.dumps({**view, "collection": view["collection"].strip() or default_key,
                         "emptyText": view["emptyText"].strip() or "No items yet.", "title": name},
                        ensure_ascii=True)
    return "const view = " + config + ";\n" + RENDER
