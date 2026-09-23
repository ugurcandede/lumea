"""One anonymous ping per day to Google Analytics (Measurement Protocol): a
random install id and the app version, nothing else. Off when "send anonymous
usage stats" is unchecked in Settings. The Measurement Protocol does not derive
geography from the IP, and no other identifier leaves the machine.

Same scheme as the author's other apps (TapLock, Sotto); the GA property is
shared and APP_NAME is the discriminator. Networking goes through Qt so it stays
on the single event loop — no threads, nothing blocks the UI."""

import json
import logging
import uuid
from datetime import datetime, timedelta

from PySide6.QtCore import QCoreApplication, QSettings, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

log = logging.getLogger(__name__)

# GA4 → Admin → Data streams → Measurement Protocol API secrets. The property is
# shared across apps; APP_NAME is the discriminator.
MEASUREMENT_ID = "G-DCYDCWCN8V"
API_SECRET = "RzYiYu4ISFCAwL6K4ZuiUA"
APP_NAME = "lumea"

_nam = None
_timer = None


def enabled() -> bool:
    return QSettings().value("analytics_enabled", True, type=bool)


def set_enabled(value: bool) -> None:
    QSettings().setValue("analytics_enabled", bool(value))


def start() -> None:
    global _nam, _timer
    _nam = QNetworkAccessManager()
    _ping_if_due()
    # The app can run for weeks between launches; a timer keeps daily actives
    # honest. _ping_if_due itself sends at most once per day.
    _timer = QTimer()
    _timer.setInterval(6 * 3600 * 1000)
    _timer.timeout.connect(_ping_if_due)
    _timer.start()


def _ping_if_due() -> None:
    if not MEASUREMENT_ID or not API_SECRET or not enabled():
        return
    now = datetime.now()
    if _last_ping() == _day(now):
        return
    for date in _unsent_dates(now):
        _send(date, backdated=date != now)


def _unsent_dates(now):
    """Days missed offline are backfilled with a backdated timestamp, which GA
    accepts up to 72 hours into the past — so at most the two previous days are
    recoverable; older gaps stay lost."""
    last_sent = _last_ping()
    if last_sent is None:
        return [now]
    dates = [now - timedelta(days=offset) for offset in (2, 1)]
    return [d for d in dates if _day(d) > last_sent] + [now]


def _send(date, backdated: bool) -> None:
    url = QUrl(f"https://www.google-analytics.com/mp/collect"
               f"?measurement_id={MEASUREMENT_ID}&api_secret={API_SECRET}")
    request = QNetworkRequest(url)
    request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
    # session_id and engagement_time_msec are required for the ping to count as
    # an active user in GA4 reports, not just an event.
    body = {
        "client_id": _client_id(),
        "events": [{
            "name": "daily_ping",
            "params": {
                "app_name": APP_NAME,
                # "backfill" means the day was spent offline and the ping was
                # recovered later; "live" went out same-day.
                "ping_type": "backfill" if backdated else "live",
                "app_version": QCoreApplication.applicationVersion() or "dev",
                "session_id": str(int(date.timestamp())),
                "engagement_time_msec": 100,
            },
        }],
    }
    if backdated:
        body["timestamp_micros"] = int(date.timestamp() * 1_000_000)

    # The day is marked sent only once Google answers — an unreachable network
    # leaves the last ping untouched, so the next timer tick retries and
    # backfills what it can.
    sent_day = _day(date)
    reply = _nam.post(request, json.dumps(body).encode())

    def done():
        reply.deleteLater()
        if reply.error() != QNetworkReply.NetworkError.NoError:
            log.debug("analytics ping failed: %s", reply.errorString())
            return
        if sent_day > (_last_ping() or ""):
            QSettings().setValue("analytics_last_ping", sent_day)

    reply.finished.connect(done)


def _last_ping():
    """yyyy-MM-dd of the newest acknowledged ping."""
    return QSettings().value("analytics_last_ping", None)


def _client_id() -> str:
    """Random id minted on first use — the only identifier analytics sends."""
    settings = QSettings()
    cid = settings.value("analytics_client_id", None)
    if not cid:
        cid = str(uuid.uuid4())
        settings.setValue("analytics_client_id", cid)
    return cid


def _day(date) -> str:
    return date.strftime("%Y-%m-%d")
