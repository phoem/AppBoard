import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool primary: false
    implicitHeight: 32
    leftPadding: 12
    rightPadding: 12
    hoverEnabled: true
    font.family: "Segoe UI"
    font.pixelSize: 13
    contentItem: Text {
        text: control.text
        font: control.font
        color: control.primary ? "#10261e" : "#dce4e1"
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 5
        color: control.primary ? (control.hovered ? "#a9e6c5" : "#8ed5ae")
                               : (control.hovered ? "#36403c" : "#252c29")
        border.color: control.visualFocus ? "#ddffe9" : (control.primary ? "#8ed5ae" : "#404944")
    }
}
