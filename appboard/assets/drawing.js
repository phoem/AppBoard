// This function is captured by the host before evaluating the app's script.
(function () {
  const stringify = JSON.stringify;
  const parse = JSON.parse;
  return function render(width, height, eventJSON, browserJSON) {
    const nodes = [];
    const commands = [];
    let animate = false;
    function node(kind, attributes) {
      if (nodes.length >= 512) throw Error("A frame supports up to 512 drawing operations.");
      nodes.push({kind, ...attributes});
    }
    const g = Object.freeze({
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
    if (eventJSON && typeof input === "function") input(parse(eventJSON), g, width, height);
    draw(g, width, height);
    return stringify({nodes, commands, animate});
  };
})()
