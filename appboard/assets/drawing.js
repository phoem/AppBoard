// This function is captured by the host before evaluating the app's script.
(function () {
  const stringify = JSON.stringify;
  const parse = JSON.parse;
  let focusedField = null;
  let selectAll = false;
  return function render(width, height, eventJSON, browserJSON, dataJSON) {
    const nodes = [];
    const commands = [];
    let animate = false;
    let feature = null;
    const data = parse(dataJSON);
    const event = eventJSON ? parse(eventJSON) : null;
    const editedFields = new Set();
    if (event && event.type === "down") {
      focusedField = null;
      selectAll = false;
    }
    function pressed(x, y, w, h) {
      return Boolean(event && event.type === "down" &&
        event.x >= x && event.x < x + w && event.y >= y && event.y < y + h);
    }
    function node(kind, attributes) {
      if (nodes.length >= 512) throw Error("A frame supports up to 512 drawing operations.");
      nodes.push({kind, ...attributes});
    }
    const g = Object.freeze({
      data,
      openFeature(id, brief) { feature = [id, brief]; },
      button(x, y, w, h, label, color = "#245b45") {
        this.rect(x, y, w, h, color, 6);
        this.text(x + 12, y + Math.max(0, (h - 20) / 2), label, 16, "white");
        return pressed(x, y, w, h);
      },
      featureButton(x, y, w, h, label, id, brief, color = "#245b45") {
        if (this.button(x, y, w, h, label, color)) feature = [id, brief];
      },
      textField(x, y, w, h, key, placeholder = "") {
        if (typeof key !== "string" || !key || key === "__proto__") throw Error("textField needs a data key.");
        if (pressed(x, y, w, h)) focusedField = key;
        let value = typeof data[key] === "string" ? data[key] : "";
        let submitted = false;
        if (focusedField === key && event && event.type === "key" && !editedFields.has(key)) {
          editedFields.add(key);
          const control = event.modifiers & 0x04000000;
          if (event.key === 16777220 || event.key === 16777221) submitted = true;
          else if (control && event.key === 65) selectAll = true;
          else if (event.key === 16777219) {
            value = selectAll ? "" : Array.from(value).slice(0, -1).join("");
            selectAll = false;
          } else if (!control && event.text && !/[\x00-\x1f\x7f]/.test(event.text)) {
            value = ((selectAll ? "" : value) + event.text).slice(0, 8192);
            selectAll = false;
          }
          data[key] = value;
        }
        this.rect(x, y, w, h, focusedField === key ? "#daeaff" : "#f0f2f4", 5);
        const room = Math.max(1, Math.floor((w - 16) / 9));
        this.text(x + 8, y + Math.max(0, (h - 20) / 2), value.slice(-room) || placeholder, 16, "#172430");
        return {value, submitted};
      },
      clear(color) { nodes.length = 0; this.rect(0, 0, width, height, color); },
      rect(x, y, w, h, color, radius = 0) { node("rect", {x, y, w, h, color, radius}); },
      circle(cx, cy, radius, color) { this.rect(cx-radius, cy-radius, 2*radius, 2*radius, color, radius); },
      text(x, y, value, size = 16, color = "#151918") { node("text", {x, y, value: String(value), size, color}); },
      line(x1, y1, x2, y2, color, thickness = 1) {
        this.path("M"+x1+" "+y1+" L"+x2+" "+y2, "transparent", color, thickness);
      },
      path(d, fill, stroke = "transparent", thickness = 1) { node("path", {d, color: fill, stroke, thickness}); },
      image(x, y, w, h, png) { node("image", {x, y, w, h, png}); },
      animate() { animate = true; },
      browser: Object.freeze({
        url: "", title: "", loading: false, canGoBack: false, canGoForward: false,
        ...parse(browserJSON),
        navigate(url) { commands.push(["navigate", String(url)]); },
        back() { commands.push(["back", ""]); },
        forward() { commands.push(["forward", ""]); },
        reload() { commands.push(["reload", ""]); }
      })
    });
    if (typeof draw !== "function") throw Error("Define function draw(g, w, h).");
    if (event && typeof input === "function") input(event, g, width, height);
    draw(g, width, height);
    return stringify({nodes, commands, animate, data, feature});
  };
})()
