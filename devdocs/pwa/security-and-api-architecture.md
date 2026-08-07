<!-- VERSION$00002$ | Edited: 07/08 | TIME: 18:53 -->
# PWA Security and API Architecture

## Purpose

Define the security boundary for moving ArtWorks task handling from the current iPhone Python client into a GitHub Pages-hosted PWA.

## Selected direction

**Decision:** use user-supplied ArtWorks credentials and keep those reusable credentials on the user's device.

The PWA should call ArtWorks directly from the browser if the provider's CORS policy permits the required authenticated requests.

A shared application credential, GitHub Actions secret, or credential injected into the public Pages build is explicitly rejected.

This selected direction still requires two implementation decisions:

1. the exact protected device-local persistence/unlock UX for the user's credential;
2. verified ArtWorks browser CORS/preflight behavior.

## Current authentication behavior

The current Python client constructs an HTTP Basic `Authorization` header from the locally stored ArtWorks username and password and sends requests directly to `https://api.artworks.ai`.

That is viable in the current architecture because the credentials live in a local file next to the Python runtime on the user's device and are not published with the repository or static site.

The browser implementation should preserve the ownership property — the user owns the credential — without pretending browser storage is equivalent to a native secret vault.

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

## Credential persistence threat model

The user wants the credential retained on-device rather than re-entered on every launch.

The primary browser threat is cross-site scripting: any malicious JavaScript executing with the PWA's origin privileges can potentially read application storage and can access a credential while the application has unlocked it for use.

This means persistence must be described accurately:

- no web storage mechanism makes a reusable browser credential immune to same-origin script compromise;
- encryption at rest can reduce exposure from raw storage inspection, backups, or accidental leakage;
- encryption does **not** defeat XSS after the PWA has unlocked the credential, because authorized application JavaScript must eventually obtain usable secret material to build the request;
- storing an encryption key beside the ciphertext in the same origin only disguises the value and does not create a meaningful security boundary.

## Storage options

### Memory only

Strongest simple browser option because no reusable credential is persisted by the application.

Disadvantage: the user must supply/unlock it again after restart.

Retain as a fallback/private-session mode, but it does not satisfy the selected convenience goal by itself.

### `sessionStorage`

Not selected for persistent credentials. It is still readable by same-origin JavaScript and disappears with the session.

### Raw `localStorage`

**Rejected for ArtWorks credentials.**

OWASP guidance specifically advises against storing sensitive authentication data in browser local storage because XSS can read it. Its synchronous, string-only API is also a poor fit for the PWA's structured recovery database.

`localStorage` may remain acceptable for low-risk UI preferences, but not for the username/password.

### Raw IndexedDB

IndexedDB is the preferred structured storage mechanism for task/run/history state, but **raw IndexedDB is not a secret vault**. A credential stored there unencrypted is still available to same-origin JavaScript.

### Encrypted credential record in IndexedDB

This is the preferred direction to study for persistent user credentials.

A defensible browser-only design is:

1. user enters ArtWorks credentials and an application unlock secret/passphrase;
2. derive an encryption key with Web Crypto, for example PBKDF2 with a random salt and deliberately selected iteration count;
3. encrypt the credential using authenticated encryption such as AES-GCM with a fresh IV;
4. persist only ciphertext, salt, IV, version/KDF metadata, and non-secret UX metadata in IndexedDB;
5. do not persist the derived encryption key;
6. require the user to unlock the credential after a cold restart before authenticated ArtWorks calls can resume.

This provides meaningful encryption at rest while keeping the reusable ArtWorks password off the repository and public build.

It does not make an unlocked page invulnerable to XSS, so frontend code security remains essential.

### Zero-friction auto-unlock

A design that stores both ciphertext and the decryption key under the same web origin should **not** be described as secure encrypted storage. It may deter casual inspection but provides little protection against origin compromise.

If a later platform-supported credential/password-manager mechanism can provide a stronger user-presence boundary, evaluate it separately rather than inventing a custom claim of native-keychain equivalence.

## Frontend security requirements

Because the future PWA will handle credentials directly, copying the legacy single-file HTML structure byte-for-byte is not the correct security goal. Preserve the UI and behavior, but the new `pwa/` may legitimately separate local CSS and JavaScript files to support a stricter policy.

### No third-party runtime JavaScript

Do not load analytics, tag managers, UI frameworks, CDN libraries, or other third-party runtime scripts without a concrete need and security review.

The dependency-free/plain-JavaScript project direction is an advantage here.

### Fonts

The current launcher loads JetBrains Mono from Google Fonts. This is not JavaScript, but the new credential-bearing PWA should minimize third-party runtime dependencies generally.

Preferred options are:

- use the existing system/fallback monospace stack; or
- self-host the required web-font assets if the typography is important.

Do not make external font availability a functional dependency.

### Content Security Policy

Use a restrictive Content Security Policy as defense in depth.

Because GitHub Pages is static, a CSP delivered through a `<meta http-equiv="Content-Security-Policy">` element is a practical baseline when response-header control is unavailable, while recognizing that some CSP directives are only effective as HTTP headers.

The initial policy should be allowlist-based and tightened around the actual PWA architecture. Likely needs include:

- scripts from `'self'` only;
- styles from `'self'` only if CSS is separated;
- worker and manifest from `'self'`;
- image support for local resources plus `blob:`/`data:` where genuinely required;
- explicit `connect-src` for the ArtWorks API and any verified media origin;
- explicit `media-src` for downloaded/previewed result media if needed;
- no arbitrary framing, plugins, or remote script hosts.

Do not finalize the exact `connect-src`/`media-src` list until real ArtWorks result origins and CORS behavior are known.

### Safe DOM construction

Continue the current application's good pattern of assigning user/provider strings through `textContent` and DOM properties rather than constructing executable HTML.

Avoid `innerHTML` for prompt text, task errors, provider messages, filenames, or imported settings.

## Task/recovery data is not secret credential data

Use IndexedDB for structured non-secret application state such as:

- runs and prompt sets;
- remote task IDs;
- parameters and last known status;
- phase timestamps and retry counters;
- output/download state;
- reusable history.

Keep the encrypted credential record logically separate so task/history code does not accidentally serialize the user's secret into logs, exports, or debugging views.

The application may request durable browser storage through `navigator.storage.persist()` after meaningful user state exists. Persistent storage improves eviction resistance; it does not make data cryptographically secret.

## Service Worker security boundary

A Service Worker does not change the selected credential model.

Do not:

- hard-code the ArtWorks credential into `service-worker.js`;
- copy it into Cache Storage;
- include it in push subscription metadata;
- log the `Authorization` header;
- persist a decrypted credential in Service Worker globals and assume those globals are durable/private.

If a Service Worker eventually handles an authenticated operation, it must obtain only the minimum material required through the selected unlock/session design, and implementation must account for Service Worker termination.

The current background-execution research recommends that normal ArtWorks task polling remain foreground/recovery driven rather than credential-bearing background polling.

## Web Push and the credential boundary

Web Push requires an external sender. Under the selected architecture, that sender must not be given the user's reusable ArtWorks username/password merely so it can poll tasks.

The clean future notification path would use an ArtWorks webhook/callback or a scoped/delegated provider credential that lets a minimal relay learn task completion without taking possession of the reusable account password.

Current status of ArtWorks webhook/callback support: **Unknown.** No authoritative mechanism was identified in current project sources or the web research performed for this discovery. This absence must not be promoted to a claim that the provider does not support one.

See [`background-execution-and-notifications.md`](background-execution-and-notifications.md) for the platform analysis.

## Alternative architectures retained as fallbacks

### Authenticated server-side proxy

A conventional proxy would avoid browser CORS and could protect the ArtWorks credential server-side, but it conflicts with the currently selected user-owned/device-local credential direction unless users explicitly delegate credentials to it.

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

1. Build the PWA shell without credentials or live submission.
2. Implement IndexedDB task/run/history schema separately from secret storage.
3. Implement the encrypted credential/unlock proof of concept using Web Crypto.
4. Add restrictive CSP and keep runtime assets local.
5. Run a non-billable ArtWorks CORS/preflight check from the real GitHub Pages PWA origin.
6. Only if CORS succeeds, implement authenticated read/validation behavior.
7. Submit a real generation only with explicit awareness that acceptance may be billable.
8. Re-evaluate provider token/webhook capabilities before adding push infrastructure.

## Current recommendation

Proceed with user-owned, device-local credentials, but do **not** translate that decision into raw `localStorage`.

Use IndexedDB for structured application state and study encrypted IndexedDB + Web Crypto with a user unlock step for persistent credentials. Pair that with a strict local-only frontend dependency model and restrictive CSP.

Direct ArtWorks requests remain contingent on verified CORS support. If CORS fails, the architecture must be revisited rather than weakened by publishing credentials or creating an unauthenticated proxy.

## Research references

Primary security/platform references reviewed:

- OWASP HTML5 Security Cheat Sheet — browser storage guidance for sensitive data.
- OWASP Content Security Policy Cheat Sheet — strict CSP as XSS defense in depth.
- MDN Web Crypto API — PBKDF2 key derivation and AES-GCM authenticated encryption.
- MDN IndexedDB API — structured asynchronous browser storage.
- MDN StorageManager `persist()` — durable-storage request semantics.
- web.dev persistent storage guidance — request persistence when durable user state becomes meaningful.
