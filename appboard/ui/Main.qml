import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: window
    objectName: "workspace"
    width: 1920
    height: 1080
    minimumWidth: 480
    minimumHeight: 320
    visible: true
    title: "AppBoard"
    color: "#151918"
    onClosing: close => { close.accepted = boardApi.mayExit() }
    Shortcut { sequence: "Ctrl+N"; onActivated: boardApi.create() }
    Shortcut { sequence: "Ctrl+O"; onActivated: boardApi.open() }
    header: Rectangle {
        height: 52
        color: "#202624"
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 18
            anchors.rightMargin: 16
            spacing: 9
            Item {
                implicitWidth: 22; implicitHeight: 22
                Rectangle { x: 0; y: 2; width: 9; height: 18; radius: 2; color: "#8ed5ae" }
                Rectangle { x: 11; y: 2; width: 9; height: 8; radius: 2; color: "#d1e6d9" }
                Rectangle { x: 11; y: 12; width: 9; height: 8; radius: 2; color: "#739e87" }
            }
            Label { text: "AppBoard"; color: "#f0f4f1"; font.family: "Segoe UI"; font.weight: Font.DemiBold; font.pixelSize: 17 }
            Item { Layout.fillWidth: true }
            BoardButton { text: "Open"; onClicked: boardApi.open() }
            BoardButton { text: "+  New app"; primary: true; onClicked: boardApi.create() }
        }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#37403b" }
    }
    Item {
        id: canvas
        anchors.fill: parent
        clip: true
        property int nextZ: 0
        property int countOpened: 0
        Component { id: panel; AppPanel {} }
        Connections {
            target: boardApi
            function onOpened(session) {
                const offset = 16 + (canvas.countOpened++ % 7) * 26
                panel.createObject(canvas, {session: session, x: offset, y: offset, z: ++canvas.nextZ})
            }
        }
    }
}
