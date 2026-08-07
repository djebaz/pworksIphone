<!-- VERSION$00001$ | Edited: 07/08 | TIME: 18:20 -->
# Img2Video PWA Discovery

## Status

Discovery phase. No PWA runtime code has been added yet.

## Goal

Explore how to evolve the existing single-page Img2Video Safari launcher into a proper installable Progressive Web App while preserving the working implementation as a reference and avoiding risky edits to production code during discovery.

The future PWA runtime will be developed independently under:

```text
pwa/
```

All PWA discovery and planning documents live under:

```text
devdocs/pwa/
```

## Existing application observed

The current Safari-facing application is `shortcuts/img2video/index.html`.

Its relevant characteristics include:

- one HTML entry point with inline CSS and JavaScript;
- responsive iPhone-focused layout using `viewport-fit=cover` and CSS safe-area insets;
- existing `apple-mobile-web-app-capable=yes` metadata;
- local working-state persistence through `localStorage`;
- image selection through `<input type="file" accept="image/*">`;
- local image preview through `URL.createObjectURL()`;
- a built-in preset library loaded from `./presets.txt`;
- clipboard interaction for the generated command;
- current final hand-off through the `shortcuts://run-shortcut` custom URL scheme;
- an external JetBrains Mono Google Fonts dependency.

The current browser UI does not itself submit ArtWorks tasks. It constructs a JSON payload containing a filename and Python command and launches the iOS Shortcut.

## Existing Python responsibilities observed

`app/img2video_iphone.py` currently does substantially more than one API request. Responsibilities include:

- ArtWorks authentication;
- image encoding;
- task submission;
- task-ID persistence;
- polling and terminal-state handling;
- bounded retry/error behavior;
- cancellation tracking;
- download and validation of completed media;
- recovery/resume state;
- parallel execution;
- chained prompt execution;
- extraction of a video's final frame through FFmpeg;
- video assembly through FFmpeg;
- media validation/probing;
- optional local playback.

A browser migration therefore needs a responsibility-by-responsibility compatibility analysis. "Move API calls to the PWA" must not be interpreted as only translating `POST /api/v3/tasks` into `fetch()`.

## User decisions from discovery

### Hosting

Confirmed direction: GitHub Pages.

### Offline behavior

No offline mode is wanted for the first PWA.

This means offline application-shell caching is not a product requirement. A Service Worker should not be introduced solely because older PWA tutorials treated offline support as mandatory.

### Icon

No PWA icon exists yet. Icon design is deferred.

### iOS standalone appearance

The standalone PWA should blend with the existing dark application background and safe-area layout.

### API ownership

The desired end state is for the PWA to handle ArtWorks API calls rather than continuing to launch the Python workflow for generation.

This creates new security, CORS, lifecycle, media-processing, and recovery requirements that must be resolved before implementation.

### File selection

Preserve the current browser file-picker behavior.

### Application updates

Prefer normal deployment/update behavior where a newly deployed version is picked up on a later navigation/reload. No custom in-app update prompt is currently required.

### Installation UI

No custom Safari installation button/banner is requested for the first version. Use the normal platform installation mechanisms.

### Source isolation

Future PWA code will live in a new repository-root `pwa/` directory. Do not modify the working `shortcuts/img2video/` or `app/` implementation merely to bootstrap the PWA.

## GitHub Pages repository constraint

The current `.github/workflows/static.yml` copies `shortcuts/img2video/` into the Pages artifact root. It also publishes open pull-request snapshots under `preview/pr-<number>/`.

Consequently, adding `pwa/` to the repository does not automatically publish it. A future implementation PR must make an explicit Pages deployment decision, for example:

1. publish `pwa/` at the existing Pages root and retain the old launcher elsewhere;
2. publish `pwa/` under a subpath such as `/pwa/`;
3. publish both applications under separate stable paths;
4. change the Pages artifact layout in another deliberate way.

This discovery PR does not change the deployment workflow.

## Current standards findings

Current MDN guidance reviewed through Context7 states:

- a web app manifest is central to installability and should define at least the normal application identity, start URL, display mode, and appropriate icons;
- Chromium installability guidance expects 192x192 and 512x512 icons;
- maskable icons can be declared with manifest `purpose: "maskable"`;
- service workers are commonly used for offline experiences but are not, by themselves, a universal requirement for PWA installability;
- PWA installation on modern iOS is exposed through the Share menu; current MDN guidance notes browser support on iOS 16.4+ across Safari and several other browsers;
- service workers, if later introduced, require a secure context in production and their scope is determined by registration/script location and configuration.

Primary reference reviewed:

- https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable

## Service Worker decision

Open.

Because the product explicitly does not need offline mode, the first implementation should determine whether a Service Worker provides another concrete benefit before adding one.

Possible reasons to add one later include controlled caching, request mediation within its allowed browser security model, or future offline behavior. It must not be treated as a secure secret store; Service Worker code and browser storage remain client-side.

## API/CORS discovery still required

Before implementing browser-side ArtWorks requests, verify with a non-billable or safely rejected request where possible:

- whether `https://api.artworks.ai` permits the GitHub Pages origin through CORS;
- whether the `Authorization` request header is allowed by preflight;
- whether POST/GET/cancel endpoints can all be called from browser JavaScript;
- whether result media URLs permit browser download/display and any canvas/video operations required by chain mode;
- whether credentials have an alternative provider-supported form such as short-lived tokens or scoped API keys.

Do not infer CORS support from the fact that the Python client works. CORS is a browser-origin policy and does not apply to Python's `urllib` client in the same way.

## Major browser-port questions

1. How will ArtWorks credentials be supplied and protected?
2. Does ArtWorks permit direct requests from the GitHub Pages origin?
3. How should interrupted jobs be resumed safely in browser storage?
4. Can chained execution obtain a reliable final frame without shipping a large FFmpeg/WASM runtime?
5. Can multi-video assembly be performed acceptably on iPhone in-browser, or should that feature use another architecture?
6. How should completed videos be saved into the iOS user workflow?
7. Which Python features belong in the first PWA milestone versus a later compatibility milestone?
8. What final GitHub Pages URL/path should host `pwa/`?
9. What icon should represent the installed application?

## Non-goals for the initial PWA

Unless separately requested, do not add:

- offline mode;
- push notifications;
- background sync;
- periodic sync;
- badges;
- a framework;
- npm/build tooling;
- a PWA helper library;
- a custom install prompt;
- unrelated UI redesign.

## Next discovery focus

Credential architecture and direct-browser API feasibility are the next blockers. The browser implementation should not begin submitting real ArtWorks tasks until those are understood and billable-test boundaries are explicit.
