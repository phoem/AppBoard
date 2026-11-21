"""Build the trusted wrapper around an opaque-origin guest document."""
import base64
from pathlib import Path

from PySide6.QtCore import QFile, QIODevice, QUrl
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineQuick import QQuickWebEngineProfile

ASSETS = Path(__file__).with_name("assets")


class RequestFilter(QWebEngineUrlRequestInterceptor):
    def __init__(self, browser, parent):
        super().__init__(parent)
        self.schemes = {"https", "http", "wss", "ws", "about", "data", "blob"} if browser else {"about", "data"}

    def interceptRequest(self, request):
        if request.requestUrl().scheme() not in self.schemes:
            request.block(True)


def profile(browser, parent):
    result = QQuickWebEngineProfile(parent)
    result.setOffTheRecord(True)
    result.filter = RequestFilter(browser, result)
    result.setUrlRequestInterceptor(result.filter)
    result.downloadRequested.connect(lambda download: download.cancel())
    return result


def navigation_url(value):
    if not isinstance(value, str) or len(value) > 8192:
        return ""
    url = QUrl.fromUserInput(value)
    if url.scheme() in ("http", "https") and url.isValid() and url.host() and not url.userInfo():
        return url.toString()
    return ""


def document(project):
    # Put the SDK before author scripts while retaining standards-mode rendering.
    source = project.html.lstrip()
    if source.lower().startswith("<!doctype html>"):
        source = source[len("<!doctype html>"):]
    sdk = (ASSETS / "guest.js").read_text(encoding="utf-8") if project.browser else ""
    guest = '<!doctype html><meta charset="utf-8"><script>' + sdk + '</script>' + source
    # Base64 avoids HTML escaping expansion at Qt's loadHtml IPC size boundary.
    encoded = base64.b64encode(guest.encode()).decode("ascii")
    channel = QFile(":/qtwebchannel/qwebchannel.js")
    if not channel.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError("Qt WebChannel resources are unavailable.")
    library = bytes(channel.readAll()).decode()
    wrapper = (ASSETS / "wrapper.html").read_text(encoding="utf-8")
    return wrapper.replace("/* QT_CHANNEL */", library).replace("APPBOARD_GUEST_BASE64", encoded)
