"""Core: inject AppLovin Analytics Bridge vào HTML đã convert AL.

Spec: `AppLovin-HTML-Bridge-Tool.md` (AL_PLAYABLE_ANALYTICS_BRIDGE_V3).

Luồng CTS:
  1. AL convert tạo `<basename>_AL.html` (giữ nguyên như trước).
  2. Nếu user tick "Có Tracking" / "Có Tracking kèm Banner", tạo bản sao
     `<basename>_AL_tracking.html` và inject bridge trước `</body>`.

Module này KHÔNG phụ thuộc GUI; có thể chạy CLI độc lập.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# Marker nhận diện bridge (để remove / replace khi patch chồng).
BRIDGE_MARKER = 'AL_PLAYABLE_ANALYTICS_BRIDGE_V3'
BRIDGE_MARKER_PREFIX = 'AL_PLAYABLE_ANALYTICS_BRIDGE'

# Regex xoá block bridge cũ (mọi version có marker).
EXISTING_BRIDGE_PATTERN = re.compile(
    r'<script\b[^>]*>[\s\S]*?'
    + re.escape(BRIDGE_MARKER_PREFIX)
    + r'[\s\S]*?</script>\s*',
    re.IGNORECASE,
)

BODY_CLOSE_PATTERN = re.compile(r'</body\s*>', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Snippet production (không banner) — lấy NGUYÊN VĂN từ AppLovin-HTML-Bridge-Tool.md
# ---------------------------------------------------------------------------

BRIDGE_SCRIPT_PRODUCTION = r'''<script>
// AL_PLAYABLE_ANALYTICS_BRIDGE_V3
(function () {
  var displayedSent = false;
  var wired = false;
  var debugHooked = false;

  function hasAL() {
    return typeof window.ALPlayableAnalytics !== "undefined" &&
      window.ALPlayableAnalytics &&
      typeof window.ALPlayableAnalytics.trackEvent === "function";
  }

  function track(name) {
    if (name === "DISPLAYED") {
      if (displayedSent) return;
      displayedSent = true;
    }
    if (!hasAL()) return;
    try {
      window.ALPlayableAnalytics.trackEvent(name);
    } catch (err) {}
  }

  var NAME_FROM_LOG = {
    LogChallengeStarted: "CHALLENGE_STARTED",
    LogChallengeFailed: "CHALLENGE_FAILED",
    LogChallengeRetry: "CHALLENGE_RETRY",
    LogChallengePass25: "CHALLENGE_PASS_25",
    LogChallengePass50: "CHALLENGE_PASS_50",
    LogChallengePass75: "CHALLENGE_PASS_75",
    LogChallengeSolved: "CHALLENGE_SOLVED"
  };

  function maybeTrackFromDebugLog(msg) {
    if (typeof msg !== "string") return;
    if (msg.indexOf("[Analytics.Applovin]") === -1) return;
    for (var key in NAME_FROM_LOG) {
      if (msg.indexOf(key) !== -1) {
        track(NAME_FROM_LOG[key]);
        return;
      }
    }
  }

  function hookConsole() {
    if (debugHooked) return;
    debugHooked = true;
    var origLog = console.log;
    console.log = function () {
      try {
        if (arguments && arguments.length) maybeTrackFromDebugLog(arguments[0]);
      } catch (e) {}
      return origLog.apply(console, arguments);
    };
  }

  function wireApplovinMethods() {
    if (!window.Luna || !Luna.Unity || !Luna.Unity.Analytics) return false;
    var A = Luna.Unity.Analytics.Applovin;
    if (!A) {
      try { Luna.Unity.Analytics.Applovin = A = {}; } catch (e) { return false; }
    }
    var map = {
      LogChallengeStarted: "CHALLENGE_STARTED",
      LogChallengeFailed: "CHALLENGE_FAILED",
      LogChallengeRetry: "CHALLENGE_RETRY",
      LogChallengePass25: "CHALLENGE_PASS_25",
      LogChallengePass50: "CHALLENGE_PASS_50",
      LogChallengePass75: "CHALLENGE_PASS_75",
      LogChallengeSolved: "CHALLENGE_SOLVED",
      a$: "CHALLENGE_STARTED",
      b$: "CHALLENGE_FAILED",
      c$: "CHALLENGE_RETRY",
      d$: "CHALLENGE_PASS_25",
      e$: "CHALLENGE_PASS_50",
      f$: "CHALLENGE_PASS_75",
      g$: "CHALLENGE_SOLVED"
    };
    Object.keys(map).forEach(function (key) {
      var eventName = map[key];
      var fn = function () { track(eventName); };
      try { A[key] = fn; } catch (e1) {}
      try {
        Object.defineProperty(A, key, { value: fn, writable: true, configurable: true });
      } catch (e2) {}
    });
    return typeof A.LogChallengePass25 === "function";
  }

  function wireCta() {
    if (!window.Luna || !Luna.Unity || !Luna.Unity.Playable) return false;
    if (Luna.Unity.Playable.__alCtaWired) return true;
    var prev = Luna.Unity.Playable.InstallFullGame;
    Luna.Unity.Playable.InstallFullGame = function (ios, android) {
      track("CTA_CLICKED");
      if (typeof prev === "function") return prev(ios, android);
    };
    Luna.Unity.Playable.__alCtaWired = true;
    return true;
  }

  function wireDisplayed() {
    if (window.__alDisplayedWired) return;
    window.__alDisplayedWired = true;
    function fire() { track("DISPLAYED"); }
    window.addEventListener("luna:started", fire);
    if (typeof mraid !== "undefined") {
      try {
        if (mraid.isViewable && mraid.isViewable()) fire();
        if (mraid.addEventListener) {
          mraid.addEventListener("viewableChange", function (v) { if (v) fire(); });
        }
      } catch (e) {}
    }
    setTimeout(fire, 1500);
  }

  function tryWire() {
    hookConsole();
    var ok = wireApplovinMethods();
    wireCta();
    wireDisplayed();
    if (ok) wired = true;
    return ok;
  }

  hookConsole();
  ["luna:build", "luna:ready", "luna:started", "luna:start"].forEach(function (evt) {
    window.addEventListener(evt, function () {
      function run() { tryWire(); }
      if (typeof Bridge !== "undefined" && Bridge.ready) Bridge.ready(run);
      else run();
    });
  });

  var tries = 0;
  var timer = setInterval(function () {
    tries++;
    if (tryWire() || tries >= 100) clearInterval(timer);
  }, 200);
})();
</script>
'''


# ---------------------------------------------------------------------------
# Snippet debug banner — production + showBanner (spec AppLovin-HTML-Bridge-Tool.md)
# ---------------------------------------------------------------------------

BRIDGE_SCRIPT_WITH_BANNER = r'''<script>
// AL_PLAYABLE_ANALYTICS_BRIDGE_V3
(function () {
  var displayedSent = false;
  var wired = false;
  var debugHooked = false;

  function showBanner(text, color) {
    try {
      var id = "__al_bridge_banner";
      var el = document.getElementById(id);
      if (!el) {
        el = document.createElement("div");
        el.id = id;
        el.style.cssText = "position:fixed;z-index:2147483647;left:8px;top:8px;max-width:90%;padding:8px 10px;border-radius:8px;font:12px/1.4 -apple-system,Menlo,monospace;color:#fff;background:rgba(0,0,0,.75);pointer-events:none;white-space:pre-wrap;";
        (document.body || document.documentElement).appendChild(el);
      }
      el.style.borderLeft = "4px solid " + (color || "#4ade80");
      el.textContent = text;
    } catch (e) {}
  }

  function hasAL() {
    return typeof window.ALPlayableAnalytics !== "undefined" &&
      window.ALPlayableAnalytics &&
      typeof window.ALPlayableAnalytics.trackEvent === "function";
  }

  function track(name) {
    if (name === "DISPLAYED") {
      if (displayedSent) return;
      displayedSent = true;
    }
    if (hasAL()) {
      try {
        window.ALPlayableAnalytics.trackEvent(name);
        showBanner("[AL track OK] " + name, "#4ade80");
      } catch (err) {
        showBanner("[AL track error] " + name, "#f87171");
      }
      return;
    }
    showBanner("[AL missing] " + name + "\n(local/no SDK)", "#60a5fa");
  }

  var NAME_FROM_LOG = {
    LogChallengeStarted: "CHALLENGE_STARTED",
    LogChallengeFailed: "CHALLENGE_FAILED",
    LogChallengeRetry: "CHALLENGE_RETRY",
    LogChallengePass25: "CHALLENGE_PASS_25",
    LogChallengePass50: "CHALLENGE_PASS_50",
    LogChallengePass75: "CHALLENGE_PASS_75",
    LogChallengeSolved: "CHALLENGE_SOLVED"
  };

  function maybeTrackFromDebugLog(msg) {
    if (typeof msg !== "string") return;
    if (msg.indexOf("[Analytics.Applovin]") === -1) return;
    for (var key in NAME_FROM_LOG) {
      if (msg.indexOf(key) !== -1) {
        track(NAME_FROM_LOG[key]);
        return;
      }
    }
  }

  function hookConsole() {
    if (debugHooked) return;
    debugHooked = true;
    var origLog = console.log;
    console.log = function () {
      try {
        if (arguments && arguments.length) maybeTrackFromDebugLog(arguments[0]);
      } catch (e) {}
      return origLog.apply(console, arguments);
    };
  }

  function wireApplovinMethods() {
    if (!window.Luna || !Luna.Unity || !Luna.Unity.Analytics) return false;
    var A = Luna.Unity.Analytics.Applovin;
    if (!A) {
      try { Luna.Unity.Analytics.Applovin = A = {}; } catch (e) { return false; }
    }
    var map = {
      LogChallengeStarted: "CHALLENGE_STARTED",
      LogChallengeFailed: "CHALLENGE_FAILED",
      LogChallengeRetry: "CHALLENGE_RETRY",
      LogChallengePass25: "CHALLENGE_PASS_25",
      LogChallengePass50: "CHALLENGE_PASS_50",
      LogChallengePass75: "CHALLENGE_PASS_75",
      LogChallengeSolved: "CHALLENGE_SOLVED",
      a$: "CHALLENGE_STARTED",
      b$: "CHALLENGE_FAILED",
      c$: "CHALLENGE_RETRY",
      d$: "CHALLENGE_PASS_25",
      e$: "CHALLENGE_PASS_50",
      f$: "CHALLENGE_PASS_75",
      g$: "CHALLENGE_SOLVED"
    };
    Object.keys(map).forEach(function (key) {
      var eventName = map[key];
      var fn = function () { track(eventName); };
      try { A[key] = fn; } catch (e1) {}
      try {
        Object.defineProperty(A, key, { value: fn, writable: true, configurable: true });
      } catch (e2) {}
    });
    return typeof A.LogChallengePass25 === "function";
  }

  function wireCta() {
    if (!window.Luna || !Luna.Unity || !Luna.Unity.Playable) return false;
    if (Luna.Unity.Playable.__alCtaWired) return true;
    var prev = Luna.Unity.Playable.InstallFullGame;
    Luna.Unity.Playable.InstallFullGame = function (ios, android) {
      track("CTA_CLICKED");
      if (typeof prev === "function") return prev(ios, android);
    };
    Luna.Unity.Playable.__alCtaWired = true;
    return true;
  }

  function wireDisplayed() {
    if (window.__alDisplayedWired) return;
    window.__alDisplayedWired = true;
    function fire() { track("DISPLAYED"); }
    window.addEventListener("luna:started", fire);
    if (typeof mraid !== "undefined") {
      try {
        if (mraid.isViewable && mraid.isViewable()) fire();
        if (mraid.addEventListener) {
          mraid.addEventListener("viewableChange", function (v) { if (v) fire(); });
        }
      } catch (e) {}
    }
    setTimeout(fire, 1500);
  }

  function tryWire() {
    hookConsole();
    var ok = wireApplovinMethods();
    wireCta();
    wireDisplayed();
    if (ok) {
      wired = true;
      showBanner("[AL bridge] WIRED\nhasAL=" + hasAL(), hasAL() ? "#4ade80" : "#fbbf24");
    }
    return ok;
  }

  showBanner("[AL bridge] loading…", "#94a3b8");
  hookConsole();
  ["luna:build", "luna:ready", "luna:started", "luna:start"].forEach(function (evt) {
    window.addEventListener(evt, function () {
      function run() { tryWire(); }
      if (typeof Bridge !== "undefined" && Bridge.ready) Bridge.ready(run);
      else run();
    });
  });

  var tries = 0;
  var timer = setInterval(function () {
    tries++;
    var ok = tryWire();
    if (ok || tries >= 100) {
      clearInterval(timer);
      if (!ok) showBanner("[AL bridge] FAILED to wire", "#f87171");
    }
  }, 200);
})();
</script>
'''


# ---------------------------------------------------------------------------
# Kết quả & lỗi
# ---------------------------------------------------------------------------


@dataclass
class ALTrackingBridgeResult:
    """Tóm tắt thao tác inject AppLovin tracking bridge."""

    output_html_path: Path | None = None
    transforms_applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    input_size: int = 0
    output_html_size: int = 0
    debug_banner: bool = False
    removed_old_bridge: bool = False


class ALTrackingBridgeError(RuntimeError):
    """Raised khi HTML không đủ điều kiện để inject bridge."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_bridge_script(debug_banner: bool = False) -> str:
    """Trả về thẻ <script> bridge (production hoặc kèm debug banner)."""
    raw = BRIDGE_SCRIPT_WITH_BANNER if debug_banner else BRIDGE_SCRIPT_PRODUCTION
    # Chuẩn hoá LF để write CRLF thống nhất sau.
    return raw.replace('\r\n', '\n').strip() + '\n'


def default_tracking_filename(al_html_path: Path) -> str:
    """Từ `Foo_AL.html` → `Foo_AL_tracking.html`."""
    stem = al_html_path.stem  # vd. Input_AL
    suffix = al_html_path.suffix or '.html'
    if stem.endswith('_tracking'):
        return f'{stem}{suffix}'
    return f'{stem}_tracking{suffix}'


# ---------------------------------------------------------------------------
# Hàm chính
# ---------------------------------------------------------------------------


def bridge_html(
    input_path: str | os.PathLike,
    output_dir: str | os.PathLike,
    log: Callable[[str], None] | None = None,
    debug_banner: bool = False,
    output_filename: str | None = None,
) -> ALTrackingBridgeResult:
    """Inject AppLovin Analytics Bridge vào file HTML (thường là output AL).

    Args:
        input_path: file HTML nguồn (vd. Output/AL/Input_AL.html).
        output_dir: thư mục đầu ra (thường cùng Output/AL/).
        log: callback log (tuỳ chọn).
        debug_banner: True → inject bản có overlay QA banner.
        output_filename: mặc định `<stem>_tracking.html`.

    Returns:
        ALTrackingBridgeResult.

    Raises:
        ALTrackingBridgeError: thiếu </body> hoặc không inject được.
        FileNotFoundError: input không tồn tại.
    """

    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        raise FileNotFoundError(f'Không tìm thấy file input: {input_path}')

    _log(f'Đọc file AL để bridge tracking: {input_path}')
    with input_path.open('r', encoding='utf-8') as f:
        content = f.read()
    result = ALTrackingBridgeResult(
        input_size=len(content),
        debug_banner=debug_banner,
    )
    _log(f'  Kích thước input: {len(content):,} ký tự')
    _log(
        f'  Chế độ: {"Tracking + Banner (QA)" if debug_banner else "Tracking (production)"}'
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # BƯỚC 1 – Xoá bridge cũ nếu đã patch chồng
    # ------------------------------------------------------------------ #
    content, n_removed = EXISTING_BRIDGE_PATTERN.subn('', content)
    result.removed_old_bridge = n_removed > 0
    if n_removed > 0:
        result.transforms_applied.append(
            f'1. Xoá {n_removed} block bridge cũ ({BRIDGE_MARKER_PREFIX})'
        )
        _log(f'  + Xoá {n_removed} block bridge cũ')
    else:
        result.transforms_applied.append('1. Không có bridge cũ cần xoá')

    # ------------------------------------------------------------------ #
    # BƯỚC 2 – Inject script ngay trước </body>
    # ------------------------------------------------------------------ #
    body_match = BODY_CLOSE_PATTERN.search(content)
    if body_match is None:
        raise ALTrackingBridgeError(
            'Không tìm thấy thẻ </body> để inject AppLovin tracking bridge.'
        )

    script = build_bridge_script(debug_banner=debug_banner)
    insert_at = body_match.start()
    content = content[:insert_at] + script + content[insert_at:]

    mode_label = 'kèm Banner' if debug_banner else 'production'
    result.transforms_applied.append(
        f'2. Inject {BRIDGE_MARKER} ({mode_label}) trước </body>'
    )
    _log(f'  + Inject {BRIDGE_MARKER} ({mode_label}) trước </body>')

    # ------------------------------------------------------------------ #
    # BƯỚC 3 – Validate tối thiểu
    # ------------------------------------------------------------------ #
    if BRIDGE_MARKER not in content:
        raise ALTrackingBridgeError(
            f'Inject thất bại: thiếu marker {BRIDGE_MARKER} trong output.'
        )
    if debug_banner and 'showBanner' not in content:
        raise ALTrackingBridgeError(
            'Inject thất bại: chế độ banner nhưng thiếu showBanner.'
        )
    if not debug_banner and 'showBanner' in content:
        result.warnings.append(
            'Cảnh báo nội bộ: production script không nên chứa showBanner'
        )

    # ------------------------------------------------------------------ #
    # BƯỚC 4 – Ghi file (UTF-8 no BOM, CRLF – đồng bộ AL)
    # ------------------------------------------------------------------ #
    if output_filename is None:
        output_filename = default_tracking_filename(input_path)
    output_html = output_dir / output_filename

    content_out = content.replace('\r\n', '\n').replace('\n', '\r\n')
    with output_html.open('wb') as f:
        f.write(content_out.encode('utf-8'))

    result.output_html_path = output_html
    result.output_html_size = len(content)
    result.transforms_applied.append(f'3. Ghi output: {output_html.name}')
    _log(f'Ghi output tracking: {output_html} ({len(content):,} ký tự)')

    return result


if __name__ == '__main__':
    # CLI: python al_tracking_bridge.py <al.html> [output_dir] [--banner]
    import sys

    try:
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    args = [a for a in sys.argv[1:] if a != '--banner']
    use_banner = '--banner' in sys.argv[1:]
    if len(args) < 1:
        print(
            'Usage: python al_tracking_bridge.py <al.html> [output_dir] [--banner]'
        )
        sys.exit(1)
    in_path = Path(args[0])
    out_dir = Path(args[1]) if len(args) >= 2 else in_path.parent
    try:
        r = bridge_html(
            in_path, out_dir, log=print, debug_banner=use_banner
        )
    except ALTrackingBridgeError as exc:
        print('!! Lỗi:', exc)
        sys.exit(2)
    print('--- DONE ---')
    print('HTML output :', r.output_html_path)
    print('Debug banner:', r.debug_banner)
    print('Transforms  :', r.transforms_applied)
    if r.warnings:
        print('Warnings    :', r.warnings)
