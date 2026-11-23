let firstRow = 0;
function collectionLayout(g, w, h) {
  const items = Array.isArray(g.data[view.collection]) ? g.data[view.collection] : [];
  const columns = view.imageField ? Math.min(6, Math.max(1, Math.floor(w / 150))) : 1;
  const rowHeight = view.imageField ? 108 : 32;
  const visible = Math.max(1, Math.min(40, Math.ceil((h - 52) / rowHeight)));
  const maxRow = Math.max(0, Math.ceil(items.length / columns) - Math.max(1, Math.floor((h - 52) / rowHeight)));
  return {items, columns, rowHeight, visible, maxRow};
}
function draw(g, w, h) {
  const {items, columns, rowHeight, visible, maxRow} = collectionLayout(g, w, h);
  firstRow = Math.min(maxRow, firstRow);
  g.clear("white");
  g.text(16, 12, view.title, 22, "#18251e");
  if (!items.length) {
    g.text(16, 52, view.emptyText, 16, "#526358");
    return;
  }
  const width = Math.max(1, (w - 32) / columns);
  const start = firstRow * columns;
  for (let i = start; i < Math.min(items.length, start + visible * columns); i++) {
    const item = items[i];
    const x = 16 + ((i - start) % columns) * width;
    const y = 52 + Math.floor((i - start) / columns) * rowHeight;
    const record = item !== null && typeof item === "object";
    const image = view.imageField && (record ? item[view.imageField] : item);
    const png = typeof image === "string" && image.length <= 400000 && image.startsWith("data:image/png;base64,iVBORw0KGgo");
    if (png) g.image(x, y, Math.max(1, width - 8), 76, image);
    const label = record ? item[view.labelField] : png ? null : item;
    g.text(x, y + (png ? 78 : 0), String(label ?? ("Item " + (i + 1))).slice(0, 180), 15, "#26372e");
  }
}
function input(e, g, w, h) {
  const step = e.type === "wheel" ? -Math.sign(e.delta) :
    e.type === "key" && e.key === 16777237 ? 1 : e.type === "key" && e.key === 16777235 ? -1 : 0;
  if (step) firstRow = Math.max(0, Math.min(collectionLayout(g,w,h).maxRow, firstRow + step));
}
