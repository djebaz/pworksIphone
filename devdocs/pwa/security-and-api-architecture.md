<!-- VERSION$00003$ | Edited: 07/08 | TIME: 18:57 -->
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
- Cache Storage, IndexedDB, and `localStorage` are client-side storage, not server-side environment variables;
- obfuscation, Base64, minification, or splitting a credential across files does not make it secret.

A static PWA cannot contain a reusable private ArtWorks password and keep that password hidden from its own browser runtime.

## Selected architecture — user-supplied credentials, direct browser-to-ArtWorks

### Model

The PWA asks the user for their ArtWorks username/password locally and calls ArtWorks directly with `fetch()`.

### Advantages

- GitHub Pages remains sufficient for application hosting.
- No general ArtWorks proxy needs to be operated.
- Credentials are not committed to the repository or embedded in public deployment artifacts.
- Each user consumes their own ArtWorks account rather than a shared project credential.
- The API request path remains simple if ArtWorks CORS permits it.

### Critical prerequisite: CORS

ArtWorks must allow the deployed PWA origin to make authenticated cross-origin requests, including the `Authorization` header and required methods/endpoints.

The fact that the Python client works is not evidence of browser CORS support.

Current status: **Unverified.**

A non-billable browser/preflight probe should be performed before generation implementation. Do not create a live generation merely to discover a CORS header.

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

The primary browser threat is cross-site scripting: malicious JavaScript executing with the PWA's origin privileges can potentially read application storage and can access a credential while the application has unlocked it for use.

Therefore:

- no browser storage mechanism makes an unlocked reusable credential immune to same-origin script compromise;
- encryption at rest primarily reduces exposure from raw storage inspection or accidental leakage;
- the strongest client-only control is to minimize the amount of code allowed to execute at the PWA origin;
- task/history persistence and credential persistence must be separated.

## Frontend security requirements

Because the future PWA will handle credentials directly, copying the legacy single-file HTML structure byte-for-byte is not the correct security goal. Preserve UI and behavior, but the new `pwa/` may legitimately separate local CSS and JavaScript files to support a stricter policy.

### No third-party runtime JavaScript

Do not load analytics, tag managers, UI frameworks, CDN libraries, or other third-party runtime scripts without a concrete need and security review.

The dependency-free/plain-JavaScript project direction is an advantage here.

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
- explicit `connect-src` for the ArtWorks API and any verified media origin;
- explicit `media-src` for downloaded/processed result media if needed;
- no arbitrary remote script hosts.

Do not finalize `connect-src`/`media-src` until real ArtWorks result origins and CORS behavior are known.

### Safe DOM construction

Continue the current application's good pattern of assigning user/provider strings through `textContent` and DOM properties rather than constructing executable HTML.

Avoid `innerHTML` for prompt text, task errors, provider messages, filenames, imported settings, or history records.

## Task/recovery data is not secret credential data

Use IndexedDB for structured non-secret application state such as:

- runs and prompt sets;
- remote task IDs;
- parameters and last known status;
- phase timestamps and retry counters;
- output/download state;
- reusable history.

Keep credential handling logically separate so task/history code does not accidentally serialize the user's secret into logs, exports, or debugging views.

The application may request durable browser storage through `navigator.storage.persist()` after meaningful user state exists. Persistent storage improves eviction resistance; it does not make data cryptographically secret.

## Service Worker security boundary

A Service Worker does not change the selected credential model.

Do not:

- hard-code the ArtWorks credential into `service-worker.js`;
- copy it into Cache Storage;
- include it in push subscription metadata;
- log the `Authorization` header;
- persist a decrypted credential in Service Worker globals and assume those globals are durable/private.

The background-execution research recommends foreground/recovery-driven ArtWorks polling rather than credential-bearing background polling.

## Web Push and the credential boundary

Web Push requires an external sender. Under the selected architecture, that sender must not be given the user's reusable ArtWorks username/password merely so it can poll tasks.

The clean future notification path would use an ArtWorks webhook/callback or a scoped/delegated provider credential that lets a minimal relay learn task completion without taking possession of the reusable account password.

Current status of ArtWorks webhook/callback support: **Unknown.** No authoritative mechanism was identified in current project sources or the web research performed for this discovery. This absence must not be promoted to a claim that the provider does not support one.

See [`background-execution-and-notifications.md`](background-execution-and-notifications.md) for the platform analysis.

## Alternative architectures retained as fallbacks

### Authenticated server-side proxy

A conventional proxy would avoid browser CORS and could protect the ArtWorks credential server-side, but it conflicts with the selected user-owned credential direction unless users explicitly delegate credentials to it.

Retain this only as a fallback if direct browser calls are impossible and no provider-scoped credential exists.

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
- a public proxy with no caller authentication.

## Logging and diagnostics

The project-wide API safety rules continue to apply in the browser:

- never log username/password;
- never log `Authorization` headers;
- never log full Base64/data-URL image payloads;
- do not include secrets in task-history exports;
- sanitize provider/API error presentation so diagnostic data is useful without leaking credentials;
- preserve task IDs because they are essential for recovery and duplicate-billing avoidance.

## Recommended implementation order

1. Build the PWA shell without live credentials or submission.
2. Implement IndexedDB task/run/history schema separately from credential handling.
3. Implement and physical-device-test a semantic ArtWorks credential form using Safari Password AutoFill (`autocomplete="username"` and `autocomplete="current-password"`).
4. Keep the credential in memory after fill/unlock rather than persisting plaintext in application storage.
5. Add restrictive CSP and keep runtime assets local.
6. Run a non-billable ArtWorks CORS/preflight check from the real GitHub Pages PWA origin.
7. If Password AutoFill cannot provide acceptable restart UX, prototype encrypted IndexedDB + Web Crypto as the explicit fallback.
8. Only if CORS succeeds, implement authenticated read/validation behavior.
9. Submit a real generation only with explicit awareness that acceptance may be billable.
10. Re-evaluate provider token/webhook capabilities before adding push infrastructure.

## Current recommendation

Proceed with user-owned credentials, but make **Safari/system Password AutoFill the preferred persistence mechanism** so the PWA does not own a reusable plaintext password database.

Use IndexedDB for structured run/task/history state. Keep the active credential in memory after the user enters or AutoFills it. If AutoFill proves insufficient on the installed Home Screen PWA, evaluate encrypted IndexedDB + Web Crypto with an explicit unlock secret as a fallback — not raw `localStorage` and not a fake zero-friction encryption scheme.

Direct ArtWorks requests remain contingent on verified CORS support. If CORS fails, the architecture must be revisited rather than weakened by publishing credentials or creating an unauthenticated proxy.

## Research references

Primary security/platform references reviewed:

- Apple Developer, "Improving AutoFill experiences for your forms".
- MDN HTML `autocomplete` reference and password-form best practices.
- OWASP HTML5 Security Cheat Sheet — browser storage guidance for sensitive data.
- OWASP Content Security Policy Cheat Sheet — strict CSP as XSS defense in depth.
- MDN Web Crypto API — PBKDF2 key derivation and AES-GCM authenticated encryption for the optional fallback.
- MDN IndexedDB API — structured asynchronous browser storage.
- MDN StorageManager `persist()` — durable-storage request semantics.
- web.dev persistent storage guidance — request persistence when durable user state becomes meaningful.
