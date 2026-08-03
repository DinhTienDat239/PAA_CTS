# AppLovin Analytics Bridge cho Luna (Unity Ads export)

## Bối cảnh

- Luna **Free** thường chỉ export được **Unity Ads / ironSource**, không export AppLovin.
- Trong Unity vẫn gọi bình thường:

```csharp
Luna.Unity.Analytics.Applovin.LogChallengePass25();
```

- Ở export **không phải AppLovin**, các hàm trên chỉ là **stub `Debug.Log`**, không gọi SDK AppLovin.
- AppLovin thật cần:

```javascript
window.ALPlayableAnalytics.trackEvent('CHALLENGE_PASS_25');
```

- `ALPlayableAnalytics` chỉ tồn tại trong môi trường AppLovin (preview/campaign). Mở HTML local sẽ **không** track thật.

Vì vậy tool cần **patch HTML sau khi export Unity Ads** trước khi upload AppLovin.

## Mục tiêu tool

Input: file HTML Luna export (`targetPlatform: "unityads"` hoặc tương tự)  
Output: HTML đã inject bridge AppLovin analytics  
Option: `debugBanner=true|false` (chỉ dùng khi kiểm thử)

Unity code **không cần đổi**.

---

## Thuật toán patch

1. Đọc HTML.
2. (Khuyến nghị) Không patch chồng: nếu đã có marker `AL_PLAYABLE_ANALYTICS_BRIDGE` thì replace block cũ.
3. Inject 1 thẻ `<script>...</script>` **ngay trước** `</body>`.
4. Ghi file output (hoặc overwrite có backup).

### Marker bắt buộc

Dùng comment JS trong script để tool nhận diện:

```js
// AL_PLAYABLE_ANALYTICS_BRIDGE_V3
```

### Vì sao phải retry / nhiều event hook?

Luna giải nén asset async rồi mới `dispatchEvent("luna:build")`.  
Override quá sớm → `Luna.Unity.Analytics.Applovin` chưa sẵn.  
Override một lần quá muộn / race → miss.  
Do đó bridge phải:

- listen `luna:build`, `luna:ready`, `luna:started`, `luna:start`
- gọi trong `Bridge.ready(...)` nếu có
- poll `setInterval` ~200ms, tối đa ~100 lần

### Vì sao override cả long-name và short-name?

Luna/Bridge map:

| Long name | Short |
|---|---|
| LogChallengeStarted | a$ |
| LogChallengeFailed | b$ |
| LogChallengeRetry | c$ |
| LogChallengePass25 | d$ |
| LogChallengePass50 | e$ |
| LogChallengePass75 | f$ |
| LogChallengeSolved | g$ |

Game thường gọi long-name; short-name phòng minify.

### Vì sao hook `console.log`?

Stub mặc định của Luna:

```text
[Analytics.Applovin] LogChallengePass25
```

Nếu không override được method (property non-writable), vẫn bắt được qua log string.

### Event cần forward

| Nguồn Luna / lifecycle | AppLovin event |
|---|---|
| (auto) playable sẵn sàng | `DISPLAYED` *(required)* |
| LogChallengeStarted | `CHALLENGE_STARTED` |
| LogChallengePass25/50/75 | `CHALLENGE_PASS_25/50/75` |
| LogChallengeFailed | `CHALLENGE_FAILED` |
| LogChallengeRetry | `CHALLENGE_RETRY` |
| LogChallengeSolved | `CHALLENGE_SOLVED` |
| InstallFullGame (CTA) | `CTA_CLICKED` |

`DISPLAYED`: fire 1 lần (dedupe).  
Challenge/CTA: không dedupe phía client (AppLovin tự dedupe; cần cho flow retry).

---

## Snippet production (không banner) — dùng mặc định trong tool

Chèn trước `</body>`:

```html
<script>
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
```

---

## Extra: Debug banner (option kiểm thử)

Banner **chỉ để QA**. AppLovin preview thường **không hiện `console.log`**, nên banner hữu ích hơn console.

### Gợi ý API tool

```text
--debug-banner          # bật overlay góc trái
--no-debug-banner       # mặc định production
```

Hoặc config:

```json
{ "debugBanner": true }
```

### Cách gắn vào snippet

1. Thêm helper `showBanner(text, color)`.
2. Gọi trong:
   - lúc script load
   - khi `tryWire()` thành công
   - trong `track()` khi OK / missing / error
3. Production: **không** inject helper này.

### Snippet banner (copy vào tool khi `debugBanner=true`)

```javascript
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

// ví dụ gắn vào track():
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

// ví dụ khi wire OK:
showBanner("[AL bridge] WIRED\nhasAL=" + hasAL(), hasAL() ? "#4ade80" : "#fbbf24");
```

### Ý nghĩa banner khi test

| Banner | Nghĩa |
|---|---|
| `WIRED` + `hasAL=false` | Bridge OK, đang local / chưa có SDK |
| `AL missing ...` | Call game OK, nhưng không có AppLovin SDK |
| `AL track OK ...` | Đã `trackEvent` thành công trên AppLovin |
| `FAILED to wire` | HTML/runtime không còn `Luna.Unity.Analytics.Applovin` như kỳ vọng |

---

## Pseudo-code tool

```text
function patchHtml(inputPath, outputPath, { debugBanner=false, backup=true }):
  html = read(inputPath)
  if backup: write(inputPath + ".pre-al-bridge.bak.html", html)

  html = removeExistingBridge(html, marker="AL_PLAYABLE_ANALYTICS_BRIDGE")
  script = buildBridgeScript(debugBanner)
  if "</body>" not in html: fail
  html = insertBefore(html, "</body>", "<script>\n" + script + "\n</script>\n")
  write(outputPath, html)
```

### Checklist validate sau patch

- Có marker `AL_PLAYABLE_ANALYTICS_BRIDGE_V3`
- Script nằm trước `</body>`
- (optional) nếu `debugBanner`: có `__al_bridge_banner` / `showBanner`
- File size tăng nhẹ (~2–5KB), không phá structure HTML

---

## Quy trình vận hành

1. Unity: giữ `Luna.Unity.Analytics.Applovin.LogChallenge*()` như docs Luna.
2. Export Luna → Unity Ads HTML.
3. Chạy tool patch (`debugBanner=false` khi ship).
4. Upload HTML đã patch lên AppLovin.
5. QA trên AppLovin Preview (không dùng mở local để kết luận track thật).
6. Thứ tự event kỳ vọng: `DISPLAYED` → `CHALLENGE_STARTED` → `PASS_*` → `SOLVED` / `CTA_CLICKED`.

## Lưu ý

- Mỗi lần export lại từ Luna phải patch lại.
- Local không có `ALPlayableAnalytics` là bình thường.
- AppLovin preview có thể không hiện console; dùng `--debug-banner` khi cần.
- Đây là workaround khi không export được network AppLovin từ Luna Free; không thay hoàn toàn bản export AppLovin chính thức.
