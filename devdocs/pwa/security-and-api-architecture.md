<!-- VERSION$00004$ | Edited: 07/08 | TIME: 20:12 -->
# PWA Security and API Architecture

## Purpose

Define the security boundary for moving ArtWorks task handling from the current iPhone Python client into a GitHub Pages-hosted PWA.

## Selected direction

**Decision:** use user-supplied ArtWorks credentials rather than a shared application credential.

Reusable ArtWorks credentials must never be committed to the repository or injected into the public GitHub Pages build.

The PWA should call ArtWorks directly from the browser if the provider's CORS policy permits the required authenticated requests.

The user's preference is for credential persistence on their own device. The implementation should prefer the platform/browser password manager over inventing an application-owned password database. Exact iOS Home Screen PWA behavior still needs physical-device validation.

## Current authentication behavior

The current Python client constructs an HTTP Basic `Authorization` header from the locally stored ArtWorks username and password and sends requests directly to `https://api.artworks.ai`.

That works because the credentials live in a local file beside the Python runtime and are not published with the repository or static site.

The browser implementation should preserve the ownership property — the user owns the credential — without pretending browser application storage is equivalent to a native secret vault.

## Fundamental GitHub Pages constraint

GitHub Pages serves static public assets. There is no private server-side runtime attached to a Pages request.

Therefore:

- repository secrets must never be written into HTML, JavaScript, a manifest, JSON, or another Pages artifact;
- GitHub Actions secrets are secret while a workflow runs, but a value injected into a deployed browser asset becomes public to anyone who can fetch that asset;
- JavaScript environment variables produced at build time are not secret once bundled or emitted into the site;
- a Service Worker is client-side code and is not a secret store;
- Cache Storage, IndexedDB, OPFS, and `localStorage` are client-side origin storage, not server-side environment variables;
- obfuscation, Base64, minification, or splitting a credential across files does not make it secret.

A static PWA cannot contain a reusable private ArtWorks password and keep that password hidden from its own browser runtime.

## Selected architecture — user-supplied credentials, direct browser-to-ArtWorks

### Model

The PWA asks the user for their ArtWorks username/password locally and calls ArtWorks directly with `fetch()`.

### Advantages

- GitHub Pages remains sufficient for application hosting if CORS permits direct access.
- No general ArtWorks proxy needs to be operated.
- Credentials are not committed to the repository or embedded in public deployment artifacts.
- Each user consumes their own ArtWorks account rather than a shared project credential.
- The API request path remains simple if ArtWorks CORS permits it.

### Critical prerequisite: CORS

ArtWorks must allow the deployed PWA origin to make authenticated cross-origin requests, including the `Authorization` header and required methods/endpoints.

The fact that the Python client works is not evidence of browser CORS support.

Current status: **Unknown / unverified at runtime.**

A non-billable browser/preflight probe should be performed before generation implementation. Do not create a live generation merely to discover a CORS header.

The preflight gate must include at least the production async creation shape:

```text
POST /api/v3/tasks
Authorization
Content-Type
```

Then verify the known-ID GET/cancel/priority operations required by the selected UI.

## Preferred credential persistence hierarchy

### 1. System/browser password manager and AutoFill — preferred

The first implementation should attempt to keep reusable ArtWorks credentials out of application-owned persistent storage entirely.

Use a semantic credentials form with standard markup such as:

```html
<form id="credentialsForm">
  <input
    name="username"
    type="text"
    autocomplete="username"
    autocapitalize="none"
    spellcheck="false"
  >
  <input
    name="password"
    type="password"
    autocomplete="current-password"
  >
</form>
```

**Documented:** Safari AutoFill uses semantic form/input markup and the standard `autocomplete` tokens to identify credentials. Modern password managers are designed to save credentials for an origin and fill them when the user returns.

Benefits:

- the PWA does not create its own persistent plaintext password record;
- credential protection/unlock is delegated to the user's password manager and operating-system security model;
- Safari/iCloud Passwords can provide familiar biometric/device-authentication UX according to the user's own platform settings;
- no custom KDF/encryption format needs to be maintained by the PWA.

Important qualification: a system password manager may synchronize credentials across the user's devices/cloud account according to the user's settings. If the requirement is literally **one physical device only with no password-manager sync**, the user must disable such sync or choose another persistence mode. The PWA itself cannot promise the password manager's sync policy.

Also, Password AutoFill behavior for this exact installed Home Screen PWA flow must be tested on the target iPhone. The form may submit through JavaScript to ArtWorks rather than to the PWA origin, so save/update prompting and re-fill behavior should be validated rather than assumed.

### 2. Memory-only credential — safest application-owned fallback

Keep the credential only in page memory after the user enters or AutoFills it.

Benefits:

- the application does not persist the reusable secret itself;
- a cold restart naturally locks the PWA again;
- task IDs/history remain recoverable without retaining an unlocked ArtWorks password.

Disadvantage: after a cold restart the user must use Password AutoFill or enter the credential again before the PWA can resume authenticated polling/download work.

This is a good security property, not a correctness problem: the PWA can show persisted tasks as `authentication required to resume` until the user unlocks credentials.

### 3. Encrypted IndexedDB credential — optional fallback to study

If real-device testing shows that system Password AutoFill cannot provide acceptable persistence/re-entry UX, study an application-owned encrypted record as a fallback rather than defaulting to plaintext storage.

A defensible browser-only pattern is:

1. user enters ArtWorks credentials and a separate application unlock secret/passphrase;
2. derive an encryption key with Web Crypto, for example PBKDF2 with a random salt and deliberately selected iteration count;
3. encrypt the credential with authenticated encryption such as AES-GCM and a fresh IV;
4. persist only ciphertext, salt, IV, version/KDF metadata, and non-secret UX metadata in IndexedDB;
5. do not persist the derived key;
6. require unlock after a cold restart.

This provides encryption at rest, but it does **not** eliminate XSS risk after unlock. Authorized application JavaScript must eventually obtain usable secret material to issue the request.

### Zero-friction auto-unlock

A design that stores both ciphertext and its reusable decryption key under the same web origin should not be described as secure encrypted storage. It may deter casual inspection but does not create a meaningful boundary against origin compromise.

## Storage options explicitly rejected for reusable credentials

### Raw `localStorage`

**Rejected.** OWASP guidance advises against storing sensitive authentication data in browser local storage because same-origin script/XSS can read it.

`localStorage` may remain acceptable for low-risk UI preferences, but not the ArtWorks username/password.

### Raw `sessionStorage`

Not useful as a secure persistence mechanism. It is still readable by same-origin JavaScript and disappears with the session.

### Raw IndexedDB

IndexedDB is excellent for structured application data but is not intrinsically a secret vault. A credential stored there unencrypted is still available to same-origin JavaScript.

## Credential threat model

The primary browser threat is cross-site scripting or malicious same-origin JavaScript: code executing with the PWA's origin privileges can potentially read application storage and access a credential while the application has unlocked it for use.

Therefore:

- no browser storage mechanism makes an unlocked reusable credential immune to same-origin script compromise;
- encryption at rest primarily reduces exposure from raw storage inspection or accidental leakage;
- the strongest client-only control is to minimize the amount of code allowed to execute at the PWA origin;
- task/history persistence and credential persistence must be separated;
- deployment topology must prevent untrusted code from sharing the credential-bearing origin.

## Same-origin preview/fork security gate

This is now a first-class deployment prerequisite.

The previously proposed GitHub Pages layout uses pathname separation:

```text
production: /pwa/
preview:    /preview/pr-<number>/pwa/
```

That pathname separation is useful for navigation and Service Worker scoping, but it is **not an origin-level security boundary**. Pages under the same scheme/host/port share the same web origin.

Consequences:

- IndexedDB and OPFS are origin-scoped rather than path-scoped;
- same-origin JavaScript must be treated as capable of interacting with same-origin state/resources even if it is served from another pathname;
- Password AutoFill/browser credential behavior must not be assumed to isolate `/pwa/` from `/preview/...`;
- Service Worker scope can restrict which pages one worker controls but does not turn one pathname into a separate origin.

**Decision:** do not let untrusted PR/fork JavaScript execute under the same origin that will receive real ArtWorks credentials.

Before production credentials are used, choose one of these trust models:

1. only trusted code/branches are ever deployed beneath the credential-bearing Pages origin;
2. production PWA moves to a separate trusted hostname/origin and previews stay elsewhere;
3. untrusted preview deployment is disabled or moved to an origin that never receives real credentials.

This is a Stage 0 go/no-go decision, not later deployment polish.

## Frontend security requirements

Because the future PWA will handle credentials directly, copying the legacy single-file HTML structure byte-for-byte is not the correct security goal. Preserve UI and behavior, but the new `pwa/` may legitimately separate local CSS and JavaScript files to support a stricter policy.

### No third-party runtime JavaScript

Do not load analytics, tag managers, UI frameworks, CDN libraries, or other third-party runtime scripts without a concrete need and security review.

The dependency-light/plain-JavaScript project direction is an advantage here.

If Mediabunny is selected for Chain, pin and vendor a reviewed build under the repository-controlled `pwa/` source rather than loading it from a third-party CDN at runtime.

Use MP4-only/tree-shaken imports where practical so unrelated demuxers/features are not part of the credential-bearing runtime.

### Fonts

The current launcher loads JetBrains Mono from Google Fonts. This is not JavaScript, but the credential-bearing PWA should minimize third-party runtime dependencies generally.

Preferred options are:

- use the existing system/fallback monospace stack; or
- self-host the required web-font assets if typography is important.

Do not make external font availability a functional dependency.

### Content Security Policy

Use a restrictive Content Security Policy as defense in depth.

Because GitHub Pages is static, a CSP delivered through a `<meta http-equiv="Content-Security-Policy">` element is a practical baseline when response-header control is unavailable, while recognizing that some CSP directives only work as HTTP headers.

The initial policy should be allowlist-based and tightened around the actual PWA architecture. Likely needs include:

- scripts from `'self'` only;
- styles from `'self'` only if CSS is separated;
- worker and manifest from `'self'`;
- image support for local resources plus `blob:`/`data:` where genuinely required;
- explicit `connect-src` for the ArtWorks API and verified result-media origins;
- explicit `media-src` for remote/result media if needed;
- no arbitrary remote script hosts.

Do not finalize `connect-src`/`media-src` until real ArtWorks result origins and CORS behavior are known.

### Safe DOM construction

Continue the current application's good pattern of assigning user/provider strings through `textContent` and DOM properties rather than constructing executable HTML.

Avoid `innerHTML` for prompt text, task errors, provider messages, filenames, imported settings, or history records.

## Task/recovery data is not secret credential data

Use IndexedDB for structured non-secret application state such as:

- runs and prompt sets;
- remote task IDs;
- local submission UUIDs/fingerprints;
- parameters and last known status;
- phase timestamps and retry counters;
- output/staging/export state;
- reusable history.

Keep credential handling logically separate so task/history code does not accidentally serialize the user's secret into logs, exports, or debugging views.

The application may request durable browser storage through `navigator.storage.persist()` after checking `persisted()`. Persistent storage improves eviction resistance; it does not make data cryptographically secret.

OPFS may be used for private media staging. Like IndexedDB, it is origin-owned application state rather than a user-visible or cryptographically isolated file vault.

## Result-media browser boundary

ArtWorks result media must be tested separately from the API host.

A cross-origin MP4 can be playable by `<video>` while remaining unreadable to JavaScript/canvas/media libraries.

Chain requires JavaScript-readable media bytes, so validate:

- CORS from the real production origin;
- partial/random access used by Mediabunny;
- any response header exposure relied upon by staging validation;
- actual track decodability on target iPhone.

Do not treat successful playback as proof of Chain access.

## Submission safety and custom headers

Persist local submission intent before every potentially billable creation POST.

The current authenticated ArtWorks contract does **not document** creation idempotency.

Do not send an undocumented `Idempotency-Key` by default:

- no provider semantics are established;
- an extra custom header changes CORS preflight requirements;
- unknown headers may be rejected or ignored.

A client submission UUID still belongs in the durable ledger. A deterministic documented ArtWorks tag may be used as non-secret correlation evidence, but the current contract exposes no task-list/filter endpoint that turns it into an orphan-recovery mechanism.

## Service Worker security boundary

A Service Worker does not change the selected credential model.

Do not:

- hard-code the ArtWorks credential into `service-worker.js`;
- copy it into Cache Storage;
- include it in push subscription metadata;
- log the `Authorization` header;
- persist a decrypted credential in Service Worker globals and assume those globals are durable/private.

The background-execution research recommends foreground/reconciler-driven ArtWorks monitoring rather than credential-bearing background polling.

Relative Service Worker paths/scopes are still required so preview workers cannot control production pages, but worker scope does not replace the same-origin preview trust rule.

## Web Push and the credential boundary

Web Push requires an external sender. Under the selected architecture, that sender must not be given the user's reusable ArtWorks username/password merely so it can poll tasks.

The clean notification path would require an ArtWorks webhook/callback or similarly trusted provider-side completion event that lets a minimal relay map an opaque task/correlation value to a push subscription.

Current authenticated ArtWorks contract status: **webhook/callback registration is not documented.**

Therefore the credential-free relay has been removed from the active implementation stages. Revisit it only if a newer/provider-specific contract establishes a trusted completion event. Do not move the reusable password to a relay merely to regain polling.

See [`background-execution-and-notifications.md`](background-execution-and-notifications.md) and [`runtime-architecture.md`](runtime-architecture.md).

## Alternative architectures retained as fallbacks

### Authenticated server-side proxy

A conventional proxy would avoid browser CORS and could protect a provider credential server-side, but it conflicts with the selected user-owned credential direction unless users explicitly delegate credentials to it.

Retain this only as a fallback if direct browser calls are impossible and the product owner deliberately changes the credential boundary.

A public unauthenticated proxy remains unacceptable because strangers could create billable tasks.

### Provider-issued browser-safe or short-lived credential

If ArtWorks officially offers a scoped, revocable, browser/delegated token, prefer that over repeatedly exposing a reusable password to application JavaScript.

Current project evidence is based on Basic authentication; this alternative remains **Unknown** until provider documentation establishes it.

### Keep generation in local Python

The existing Shortcut/a-Shell/Python path remains the working fallback/reference implementation. It is not the selected PWA end state.

## Architectures rejected

The following are not security solutions:

- GitHub Actions secret injected into the PWA;
- a secret in `manifest.webmanifest`;
- a secret hard-coded in Service Worker code;
- a credential hidden in Cache Storage;
- a raw ArtWorks password stored in `localStorage`;
- a secret committed to the public repository with Base64/minification/obfuscation;
- ciphertext with its reusable decryption key stored alongside it under the same origin and described as secure;
- a public proxy with no caller authentication;
- untrusted PR/fork JavaScript sharing the credential-bearing production origin.

## Orion extension comparison

The supplied Orion extensions demonstrate browser-extension capability differences but do not weaken the PWA security requirements.

### RedGifs Downloader for Orion

The inspected extension declares RedGifs host permissions plus the `downloads` permission, resolves a direct MP4 URL, and delegates the transfer to the extension downloads API.

That privileged extension model is not evidence that an ordinary PWA can bypass cross-origin browser policy.

### Orion Lite

The inspected extension controls the page's existing `HTMLVideoElement` with ordinary playback/seek/rate/inline-media operations and stores only non-secret settings.

It provides no alternative precedent for reusable ArtWorks credential persistence.

## Logging and diagnostics

The project-wide API safety rules continue to apply in the browser:

- never log username/password;
- never log `Authorization` headers;
- never log full Base64/data-URL image payloads;
- do not include secrets in task-history exports;
- sanitize provider/API error presentation so diagnostic data is useful without leaking credentials;
- preserve task IDs because they are essential for recovery and duplicate-billing avoidance.

## Recommended implementation order

1. Resolve the production-vs-preview origin trust model before real credentials are used.
2. Run a non-billable ArtWorks CORS/preflight check from the intended production origin.
3. Test result-media JavaScript CORS/partial reads with an already-paid result where possible.
4. Build the isolated PWA shell without a live billable workflow.
5. Implement IndexedDB Run/Step/Task schema separately from credential handling.
6. Implement and physical-device-test a semantic ArtWorks credential form using Safari Password AutoFill.
7. Keep the credential in memory after fill/unlock rather than persisting plaintext in application storage.
8. Add restrictive CSP and keep runtime assets/dependencies local.
9. If Password AutoFill cannot provide acceptable restart UX, prototype encrypted IndexedDB + Web Crypto as the explicit fallback.
10. Only after CORS and origin trust succeed, implement authenticated provider operations.
11. Submit a real generation only with explicit awareness that acceptance may be billable.
12. Re-evaluate provider callback/token capabilities only when concrete new evidence appears.

## Current recommendation

Proceed with user-owned credentials, but make **Safari/system Password AutoFill the preferred persistence mechanism** so the PWA does not own a reusable plaintext password database.

Use IndexedDB for structured run/task/history state. Keep the active credential in memory after the user enters or AutoFills it. If AutoFill proves insufficient on the installed Home Screen PWA, evaluate encrypted IndexedDB + Web Crypto with an explicit unlock secret as a fallback — not raw `localStorage` and not a fake zero-friction encryption scheme.

Direct ArtWorks requests remain contingent on verified CORS support and a trusted production origin. If CORS fails, or untrusted preview code shares the credential-bearing origin, the architecture must be revisited rather than weakened.

## Research references

Primary security/platform references reviewed:

- Apple Developer, "Improving AutoFill experiences for your forms".
- MDN HTML `autocomplete` reference and password-form best practices.
- OWASP HTML5 Security Cheat Sheet — browser storage guidance for sensitive data.
- OWASP Content Security Policy Cheat Sheet — strict CSP as XSS defense in depth.
- MDN Web Crypto API — PBKDF2 key derivation and AES-GCM authenticated encryption for the optional fallback.
- MDN IndexedDB API — structured asynchronous browser storage.
- WebKit/MDN Origin Private File System documentation.
- MDN StorageManager `persist()` — durable-storage request semantics.
- web.dev persistent storage guidance — request persistence when durable user state becomes meaningful.
- inspected Orion extension packages supplied during discovery.
