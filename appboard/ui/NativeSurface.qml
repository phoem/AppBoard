import QtQuick
import QtQuick.Shapes

Item {
    id: surface
    required property var drawing
    objectName: "nativeSurface"
    clip: true
    focus: true
    function resize() { if (drawing) drawing.resize(Math.round(width), Math.round(height)) }
    onWidthChanged: resize()
    onHeightChanged: resize()
    Component.onCompleted: resize()
    Repeater {
        model: surface.drawing.items.length
        delegate: Loader {
            id: itemLoader
            required property int index
            property var op: surface.drawing.items[index] || ({kind:"", x:0, y:0})
            x: op.x || 0; y: op.y || 0
            sourceComponent: {
                switch (op.kind) {
                case "rect": return rectangle
                case "text": return label
                case "path": return vector
                case "image": return picture
                default: return null
                }
            }
            Component {
                id: rectangle
                Rectangle {
                    width: itemLoader.op.w || 0; height: itemLoader.op.h || 0
                    color: itemLoader.op.color || "transparent"; radius: itemLoader.op.radius || 0
                    antialiasing: radius > 0
                }
            }
            Component {
                id: label
                Text {
                    text: itemLoader.op.value || ""; textFormat: Text.PlainText
                    font.pixelSize: Math.max(1, itemLoader.op.size || 1)
                    color: itemLoader.op.color || "black"
                }
            }
            Component {
                id: vector
                Shape {
                    width: surface.width; height: surface.height
                    ShapePath {
                        fillColor: itemLoader.op.color || "transparent"
                        strokeColor: itemLoader.op.stroke || "transparent"
                        strokeWidth: itemLoader.op.thickness || 0
                        PathSvg { path: itemLoader.op.d || "" }
                    }
                }
            }
            Component {
                id: picture
                Image {
                    width: itemLoader.op.w || 0; height: itemLoader.op.h || 0
                    source: itemLoader.op.png || ""; fillMode: Image.Stretch
                }
            }
        }
    }
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        function send(kind, e) { surface.drawing.interact({type:kind, x:e.x, y:e.y, buttons:e.buttons}) }
        onPressed: e => { surface.forceActiveFocus(); send("down", e) }
        onReleased: e => send("up", e)
        onPositionChanged: e => send("move", e)
        onWheel: e => surface.drawing.interact({type:"wheel", x:e.x, y:e.y, delta:e.angleDelta.y})
    }
    Keys.onPressed: e => {
        surface.drawing.interact({type:"key", key:e.key, text:e.text, modifiers:e.modifiers})
        e.accepted = true
    }
}
