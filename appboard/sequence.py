"""Compile a model-described ordered list and its controls to portable native drawing code."""
import json
import re


def sequence_candidate(context):
    if "fromPage" not in context or "currentPage" in context:
        return False
    brief = context["request"]
    return bool(re.search(r"\b(?:append(?:s|ed|ing)?|add(?:s|ed|ing)?|undo|remov(?:e|es|ed|ing)|enqueue|dequeue)\b", brief, re.I) and
                re.search(r"\b(?:sequence|list|queue|order|oldest|newest|last|duplicates)\b", brief, re.I))


EDIT_ACTIONS = ("remove_last", "remove_first", "clear")
CHOICE = {"type": "object", "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
          "required": ["label", "value"], "additionalProperties": False}
SEQUENCE_SCHEMA = {"type": "object", "properties": {
    "key": {"type": "string"}, "separator": {"type": "string"},
    "append": {"type": "array", "maxItems": 12, "items": CHOICE},
    **{action: {"type": "string"} for action in EDIT_ACTIONS}},
    "required": ["key", "separator", "append", *EDIT_ACTIONS], "additionalProperties": False}


def sequence_schema(brief):
    # Ground literal parts of a description in the request. Leave ambiguous
    # wording to the model and the draw-code alternative.
    properties = dict(SEQUENCE_SCHEMA["properties"])
    match = re.search(r"""\b(?:separated|joined)\s+(?:by|with)\s+(?:'([^'\r\n]{0,32})'|"([^"\r\n]{0,32})")""",
                      brief, re.I)
    if match:
        delimiter = next(value for value in match.groups() if value is not None)
        properties["separator"] = {"type": "string", "enum": [delimiter]}
    for clause in re.split(r"[.!?;]\s+|\n", brief):
        # A short subject naming a control, as in “Withdraw removes the last entry.”
        binding = re.match(
            r"""^\s*['"]?([\w-]+(?: [\w-]+){0,3})['"]?\s+"""
            r"(?:removes?\s+(?:only\s+)?(?:the\s+)?(oldest|first|newest|last)\b"
            r"|(empties|clears)\s+(?:the\s+)?(?:queue|list|sequence|entries|log)\b)", clause, re.I)
        if binding:
            label, end, clear = binding.groups()
            if label.split()[0].lower() in {"a", "an", "the", "it", "this", "that"}:
                continue
            if clear:
                op = "clear"
            else:
                op = "remove_first" if end.lower() in {"oldest", "first"} else "remove_last"
            properties[op] = {"type": "string", "enum": [label]}
    return {**SEQUENCE_SCHEMA, "properties": properties}


def sequence_script(name, panel):
    if not isinstance(panel, dict) or set(panel) != set(SEQUENCE_SCHEMA["required"]):
        raise ValueError("An ordered list needs a state key, separator and edit actions.")
    key, separator, choices = panel["key"], panel["separator"], panel["append"]
    if (not isinstance(key, str) or not key.strip() or len(key) > 64 or
            key in {"__proto__", "constructor", "prototype"} or
            not isinstance(separator, str) or len(separator) > 32):
        raise ValueError("Invalid ordered-list key or separator.")
    if not isinstance(choices, list) or len(choices) > 12:
        raise ValueError("An ordered list supports up to 12 append choices.")
    buttons = []
    for choice in choices:
        if (not isinstance(choice, dict) or set(choice) != {"label", "value"} or
                not all(isinstance(v, str) and len(v) <= 64 for v in choice.values()) or not choice["label"].strip()):
            raise ValueError("Invalid ordered-list choice.")
        buttons.append({"op": "append", **choice})
    for op in EDIT_ACTIONS:
        label = panel[op]
        if not isinstance(label, str) or len(label) > 64:
            raise ValueError("Invalid ordered-list action label.")
        if label.strip():
            buttons.append({"op": op, "label": label})
    if not buttons:
        raise ValueError("An editable list needs at least one control.")
    config = {"title": name, "key": key, "separator": separator, "buttons": buttons}
    return "const list = " + json.dumps(config) + ";\n" + DRAW


DRAW = """function draw(g,w,h) {
  g.clear('white');
  g.text(12, 10, list.title, 21);
  const stored = g.data[list.key];
  if (stored !== undefined && !Array.isArray(stored)) {
    g.text(12, 48, 'This data key already contains a different value.');
    return;
  }
  const items = stored || [];
  const columns = Math.max(1, Math.min(list.buttons.length, Math.floor((w - 16) / 116)));
  const width = (w - 24) / columns;
  for (let i = 0; i < list.buttons.length; i++) {
    const button = list.buttons[i];
    const x = 12 + (i % columns) * width;
    const y = 44 + Math.floor(i / columns) * 40;
    if (g.button(x, y, Math.max(1, width - 6), 34, button.label)) {
      switch (button.op) {
        case 'append': items.push(button.value || button.label); break;
        case 'remove_last': items.pop(); break;
        case 'remove_first': items.shift(); break;
        case 'clear': items.length = 0; break;
      }
      g.data[list.key] = items;
    }
  }
  const bottom = 48 + Math.ceil(list.buttons.length / columns) * 40;
  g.text(12, bottom, items.join(list.separator).slice(0, 8192), 16);
}
"""
