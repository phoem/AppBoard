import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebChannel
import QtWebEngine

Rectangle {
    id: panel
    required property var session
    objectName: "appPanel"
    width: Math.min(720, parent.width)
    height: Math.min(480, parent.height)
    radius: 7
    color: "#28302d"
    border.color: "#57665e"
    property string runtimeError: ""
    function fit() {
        width = Math.min(width, parent.width)
        height = Math.min(height, parent.height)
        x = Math.max(0, Math.min(x, parent.width - width))
        y = Math.max(0, Math.min(y, parent.height - height))
    }
    Component.onCompleted: fit()
    Connections {
        target: panel.parent
        function onWidthChanged() { panel.fit() }
        function onHeightChanged() { panel.fit() }
    }
    function raisePanel() { panel.z = ++parent.nextZ }
    Connections {
        target: panel.session
        function onActivated() { panel.raisePanel(); panel.forceActiveFocus() }
    }
    TapHandler { onPressedChanged: if (pressed) panel.raisePanel() }
    Rectangle {
        id: bar
        x: 1; y: 1; width: parent.width - 2; height: 40
        color: "transparent"
        MouseArea {
            anchors.fill: parent
            onPressed: panel.raisePanel()
            drag.target: panel
            drag.minimumX: 0; drag.minimumY: 0
            drag.maximumX: panel.parent.width - panel.width
            drag.maximumY: panel.parent.height - panel.height
        }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12; anchors.rightMargin: 5; spacing: 5
            Label {
                Layout.fillWidth: true
                text: panel.session.storageStatus || panel.session.pageStatus || panel.session.title
                ToolTip.visible: labelHover.hovered && truncated
                ToolTip.text: text
                HoverHandler { id: labelHover }
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: "#edf3ee"; font.pixelSize: 13; font.bold: true
            }
            BoardButton { text: "Back"; visible: panel.session.canBack && !panel.session.building; onClicked: panel.session.back() }
            BoardButton { text: "Stop"; visible: panel.session.building; onClicked: panel.session.cancelPage() }
            BoardButton { text: "Retry"; visible: panel.session.canRetry; onClicked: panel.session.retryPage() }
            BoardButton { text: "Edit"; visible: !panel.session.building; onClicked: panel.session.edit() }
            BoardButton { text: "Retry save"; visible: panel.session.dirty; onClicked: panel.session.save() }
            BoardButton { text: "Export"; visible: panel.session.canSave && !panel.session.building; onClicked: panel.session.exportApp() }
            BoardButton { text: "Close"; onClicked: panel.session.close() }
        }
    }
    WebChannel {
        id: bridge
        registeredObjects: [proxy]
    }
    QtObject {
        id: proxy
        WebChannel.id: "browserPort"
        signal stateChanged(var state)
        function request(action: string, value: string) { panel.session.browserPort.request(action, value) }
    }
    Connections {
        target: panel.session.browserPort
        function onStateChanged(state) { proxy.stateChanged(state) }
    }
    Item {
        id: content
        x: 1; y: bar.height + 1
        width: parent.width - 2
        height: parent.height - y - 10
        clip: true
        Loader {
            id: appSurface
            width: parent.width
            height: panel.session.hasBrowser ? Math.min(panel.session.toolbarHeight, parent.height - 16) : parent.height
            sourceComponent: panel.session.native ? drawingView : documentView
        }
        Component {
            id: drawingView
            NativeSurface { drawing: panel.session.drawing }
        }
        Component {
          id: documentView
          WebEngineView {
            id: guest
            objectName: "guestView"
            profile: panel.session.guestProfile
            webChannel: bridge
            settings.localContentCanAccessFileUrls: false
            settings.localContentCanAccessRemoteUrls: false
            settings.javascriptCanOpenWindows: false
            settings.javascriptCanAccessClipboard: false
            settings.javascriptCanPaste: false
            settings.unknownUrlSchemePolicy: WebEngineSettings.DisallowUnknownUrlSchemes
            onFileDialogRequested: r => { r.accepted = true; r.dialogReject() }
            onContextMenuRequested: r => { r.accepted = true }
            onPermissionRequested: p => p.deny()
            onJavaScriptConsoleMessage: (level, message) => {
                if (level === WebEngineView.ErrorMessageLevel) panel.runtimeError = message.slice(0, 220)
            }
            onRenderProcessTerminated: panel.runtimeError = "The app renderer stopped. Use Edit to revise or reload its source."
            Component.onCompleted: loadHtml(panel.session.source)
            Connections {
                target: panel.session
                function onReloadSource() { panel.runtimeError = ""; guest.loadHtml(panel.session.source) }
            }
          }
        }
        Loader {
            id: browserLoader
            active: panel.session.hasBrowser
            x: 0; y: appSurface.height
            width: parent.width; height: parent.height - y
            sourceComponent: Component {
                WebEngineView {
                    id: browser
                    objectName: "browserView"
                    profile: panel.session.webProfile
                    settings.localContentCanAccessFileUrls: false
                    settings.javascriptCanOpenWindows: false
                    settings.unknownUrlSchemePolicy: WebEngineSettings.DisallowUnknownUrlSchemes
                    onPermissionRequested: p => p.deny()
                    onFileDialogRequested: r => { r.accepted = true; r.dialogReject() }
                    onNavigationRequested: r => {
                        if (r.isMainFrame && !/^(https?:\/\/|about:blank$)/i.test(r.url.toString())) r.reject()
                    }
                    function publish() {
                        panel.session.updateBrowser({url: url.toString(), title: title,
                            loading: loading, canGoBack: canGoBack, canGoForward: canGoForward})
                    }
                    onUrlChanged: publish()
                    onTitleChanged: publish()
                    onCanGoBackChanged: publish()
                    onCanGoForwardChanged: publish()
                    onLoadingChanged: publish()
                    Component.onCompleted: publish()
                    Connections {
                        target: panel.session
                        function onBrowserCommand(action, value) {
                            if (action === "navigate") browser.url = value
                            else if (action === "back") browser.goBack()
                            else if (action === "forward") browser.goForward()
                            else if (action === "reload") browser.reload()
                        }
                    }
                }
            }
        }
        Rectangle {
            visible: errorText.text !== ""
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: errorText.implicitHeight + 12
            color: "#532e2b"
            Label {
                id: errorText
                anchors.centerIn: parent; width: parent.width - 14; wrapMode: Text.Wrap
                color: "#ffe7dd"; textFormat: Text.PlainText
                text: panel.session.native ? panel.session.drawing.problem : panel.runtimeError
            }
        }
    }
    MouseArea {
        anchors.bottom: parent.bottom; anchors.right: parent.right; width: 22; height: 10
        cursorShape: Qt.SizeFDiagCursor
        property point start
        property size initial
        onPressed: mouse => {
            panel.raisePanel()
            start = mapToItem(panel.parent, mouse.x, mouse.y)
            initial = Qt.size(panel.width, panel.height)
        }
        onPositionChanged: mouse => {
            if (!pressed) return
            const p = mapToItem(panel.parent, mouse.x, mouse.y)
            panel.width = Math.min(panel.parent.width - panel.x, Math.max(340, initial.width + p.x - start.x))
            panel.height = Math.min(panel.parent.height - panel.y, Math.max(180, initial.height + p.y - start.y))
        }
        Text { anchors.centerIn: parent; text: "◢"; font.pixelSize: 9; color: "#91a599" }
    }
    Connections {
        target: panel.session
        function onRemoved() {
            const s = panel.session
            panel.destroy()
            Qt.callLater(boardApi.release, s)
        }
    }
}
