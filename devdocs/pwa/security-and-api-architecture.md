<!-- VERSION$00001$ | Edited: 07/08 | TIME: 18:20 -->
# PWA Security and API Architecture

## Purpose

Define the security boundary for moving ArtWorks task handling from the current iPhone Python client into a GitHub Pages-hosted PWA.

This document is exploratory. No credential architecture has been selected yet.

## Current authentication behavior

The current Python client constructs an HTTP Basic Authorization header from the locally stored ArtWorks username and password and sends requests directly to `https://api.artworks.ai`.

That is viable in the current architecture because the credentials live in a local file next to the Python runtime on the user's device and are not published with the repository or static site.

## Fundamental GitHub Pages constraint

GitHub Pages serves static public assets. There is no private server-side runtime attached to a Pages request.

Therefore:

- repository secrets must never be written into HTML, JavaScript, a manifest, JSON, or another Pages artifact;
- GitHub Actions secrets are secret while a workflow runs, but a value injected into a deployed browser asset becomes public to anyone who can fetch that asset;
- JavaScript environment variables produced at build time are not secret once bundled or emitted into the site;
- a Service Worker is client-side code and is not a secret store;
- obfuscation, Base64, minification, or splitting a credential across files does not make it secret.

A static PWA cannot contain a reusable private ArtWorks password and keep that password hidden from the browser/user.

## Architecture A — user-supplied credentials, direct browser-to-ArtWorks

### Model

The PWA asks the user for ArtWorks credentials locally and calls ArtWorks directly with `fetch()`.

### Advantages

- GitHub Pages can remain the only hosting platform for the application itself.
- No separate backend needs to be operated.
- Credentials are not committed to the repository or embedded in public deployment artifacts.
- The API request path is simple if ArtWorks CORS permits it.

### Security properties

The credentials are necessarily available to JavaScript while requests are being made.

Storage choices have different tradeoffs:

- **memory only**: safest simple option against persistence, but credentials must be entered again after application restart;
- **sessionStorage**: persists for the browser session but is still readable by same-origin JavaScript;
- **localStorage**: convenient but persistent and readable by any JavaScript executing on the origin; not appropriate to describe as secure secret storage;
- **IndexedDB**: better structured storage but not intrinsically a secure credential vault;
- **password-manager/autofill flow**: potentially useful for UX, but browser/platform support must be studied and it does not change the fact that credentials enter page JavaScript when used.

A strong Content Security Policy, no untrusted scripts, no HTML injection, careful dependency control, and avoiding unnecessary third-party JavaScript become especially important if credentials ever enter the PWA.

### Critical prerequisite

ArtWorks must support cross-origin browser requests from the PWA origin, including preflight for the `Authorization` header and the required HTTP methods.

This is currently unverified.

### Best fit

Potentially attractive for a personal/single-user application if direct browser CORS works and the user accepts entering credentials on the device.

## Architecture B — thin authenticated API proxy

### Model

The GitHub Pages PWA calls a small server-side endpoint. That backend stores the ArtWorks credential in its own secret manager/environment and makes authenticated ArtWorks requests on behalf of the PWA.

Possible hosting categories include edge/serverless functions or a small conventional backend. The provider should be selected later based on operational simplicity, cost, authentication options, request/body limits, and timeout behavior.

### Advantages

- ArtWorks credentials never need to be shipped to browser JavaScript.
- CORS toward ArtWorks becomes a server-to-server concern rather than a browser restriction.
- The proxy can validate allowed operations and payload sizes.
- Rate limiting and abuse controls can be added.
- Credentials can be rotated without redeploying the PWA.

### Risks and requirements

A public unauthenticated proxy would effectively publish access to the ArtWorks account and could create billable tasks for strangers. Therefore a proxy requires its own access-control strategy.

Potential approaches include:

- user authentication in front of the proxy;
- an access platform that authenticates the intended user;
- short-lived signed session tokens issued after authentication;
- another provider-supported identity mechanism.

A static secret embedded in the PWA and used to authenticate to the proxy is not a solution; it would itself be public.

### Best fit

Strongest general architecture when the ArtWorks account credential must remain server-side and the PWA is reachable publicly.

## Architecture C — provider-issued browser-safe or short-lived credential

### Model

Use an ArtWorks-supported token/API-key/session mechanism designed for browser or delegated use, ideally scoped and revocable and possibly short-lived.

### Status

Unknown. The current project evidence is based on username/password Basic authentication. Provider capabilities must be verified before relying on this option.

### Best fit

Potentially the cleanest architecture if ArtWorks officially supports a browser-oriented, scoped credential flow.

## Architecture D — keep generation in the local Python client

### Model

The PWA remains a UI/orchestrator and hands work to the existing Shortcut/a-Shell/Python client.

### Advantages

- Existing secret handling remains local.
- Existing recovery, FFmpeg, download, chain, and assembly logic is preserved.
- Lowest migration risk.

### Disadvantage

This does not satisfy the desired end state in which the PWA itself handles ArtWorks calls.

### Use in planning

Retain as a fallback/reference architecture, not the target.

## Architectures that must be rejected

### GitHub Actions secret injected into the PWA

Rejected. Once rendered into browser-accessible code/configuration, the value is no longer secret.

### Secret in `manifest.webmanifest`

Rejected. The manifest is public.

### Secret in Service Worker code or Cache Storage

Rejected. Service Worker scripts and browser caches are client-side and inspectable.

### Secret in a public repository with encoding/obfuscation

Rejected. Encoding is not encryption and browser code must ultimately recover the value.

### Public proxy with no caller authentication

Rejected for production. It would expose billable ArtWorks capability to arbitrary callers.

## Additional browser security considerations

### Cross-site scripting

If the page holds or uses credentials, XSS becomes credential compromise. Avoid unnecessary third-party JavaScript and unsafe DOM injection.

The current UI already uses an external Google Fonts stylesheet but no external JavaScript library. Preserving a dependency-light runtime is beneficial.

### Content Security Policy

A future implementation should investigate a restrictive CSP compatible with the existing inline CSS/JavaScript architecture. A strong CSP may motivate moving inline JavaScript and CSS to local files or using hashes/nonces, but this should be a deliberate security change rather than an aesthetic refactor.

### Result URLs

The ArtWorks result-media origin and its CORS/content-disposition behavior must be checked. Browser display, direct download, canvas extraction, and media processing can have different cross-origin requirements.

### Local persistence

Task IDs and non-secret recovery state are good candidates for IndexedDB or localStorage. Secret credentials and non-secret task state should not be conflated merely because both require persistence.

## Recommended discovery order

1. Inspect the authenticated ArtWorks OpenAPI/auth documentation for alternative authentication mechanisms.
2. Verify CORS/preflight behavior without creating a billable generation where possible.
3. Decide whether direct user-supplied credentials are acceptable for this personal PWA.
4. If credentials must remain server-side, select a backend/proxy hosting and user-auth model.
5. Only after the security boundary is selected, implement browser task submission.

## Current recommendation

Do not attempt to create a fake "secure environment variable" inside GitHub Pages. The real decision is between:

- credentials supplied on the user's device and sent directly to ArtWorks, if CORS permits; or
- credentials stored in a separate authenticated backend/edge function that proxies ArtWorks.

Provider-supported short-lived/scoped credentials should be preferred over both if ArtWorks offers them, but that capability is not yet verified.
