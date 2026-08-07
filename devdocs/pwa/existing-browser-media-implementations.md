<!-- VERSION$00001$ | Edited: 07/08 | TIME: 20:40 -->
# Existing Browser Media Implementations

## Purpose

Record directly inspected browser-extension implementations owned by the project owner that already solve harder media problems than the Img2Video PWA requires.

These repositories are useful as implementation references, but they do **not** change the browser security boundary of a normal PWA. Extension-only privileges such as host permissions, background/offscreen extension pages, `chrome.runtime`, and browser download APIs must not be treated as available to GitHub Pages.

This report distinguishes:

- **Confirmed by repository inspection**: behavior present in the inspected source tree at the referenced commit;
- **Inferred for Img2Video**: a design lesson derived from that implementation;
- **Not established**: behavior that still requires target-iPhone or ArtWorks validation.

No ArtWorks generation request was made while preparing this report.

## Reference repositories

### `djebaz/mothanext`

Inspected private repository snapshot:

```text
6d415869092ecb7e41d0b66d8d79574df86b957e
```

Relevant paths include:

- `src/offscreen/offscreen.js`
- `src/lib/webcodecs/convertstartend.js`
- `src/lib/webcodecs/mediabunny-loader.js`
- `devdocs/mediabunny-transition.md`
- `devdocs/action_sequences_report_v1.9.md`
- `README.md`

### `djebaz/StreamsDL`

Inspected private repository snapshot:

```text
91205d0d4511ad49ae04563daf8b27480d2004c5
```

Relevant paths include:

- `src/pages/parse.js`
- `src/pages/app/mp4-probe.js`
- `src/pages/pipeline/clip-mp4.js`
- `src/pages/pipeline/download-chunks.js`
- `src/pages/pipeline/mp4.js`
- `src/vendor/parsers/m3u8-parser.js`
- `src/vendor/parsers/mpd-parser.js`
- `src/vendor/ffmpeg/`
- `devdocs/features/ffmpeg-0.11-core-finalization.md`
- `README.md`

## `mothanext`: browser-native media engine reference

### Confirmed by repository inspection

`mothanext` contains real media-byte processing, not only playback control or URL delegation.

Its media path includes:

- MP4 metadata/sample-table processing;
- byte-range-oriented media acquisition;
- explicit DTS/PTS handling;
- keyframe/sync-sample alignment;
- WebCodecs `VideoDecoder` and `VideoEncoder` use;
- WebCodecs audio decode/encode in the full segment-processing path;
- decoded-frame lifetime management with explicit `frame.close()`;
- output muxing/remuxing;
- a later Mediabunny integration/migration path;
- an offscreen processing document separated from the normal page/content execution path.

The low-level implementation explicitly distinguishes H.264 decode order from presentation order. Current code comments state that B-frame video must reach `VideoDecoder` in decode/DTS order while presentation timestamps remain distinct.

The repository also vendors/loads Mediabunny locally rather than depending on a runtime third-party CDN.

### What `mothanext` proves for our design

It demonstrates that browser-side media work using ordinary web media primitives is practical for substantially harder operations than Chain final-frame extraction.

The difficult path already implemented there is conceptually:

```text
remote MP4
  -> byte ranges / MP4 sample metadata
  -> encoded video/audio samples
  -> WebCodecs decode
  -> decoded frames/audio
  -> WebCodecs encode
  -> mux/remux
  -> downloadable media Blob
```

Img2Video Chain requires only a strict subset:

```text
remote MP4
  -> decode final presentation sample
  -> canvas
  -> JPEG/PNG Blob
```

Therefore Img2Video should not copy the full `mothanext` transcoding pipeline. The value is the proven browser-media engineering knowledge and the fallback/debug techniques.

### Reusable patterns for Img2Video

Reuse conceptually:

- DTS versus PTS awareness;
- keyframe/dependency awareness;
- bounded Range acquisition;
- runtime codec capability checks;
- explicit cleanup of decoded media objects;
- stage/progress/error reporting;
- cancellation and bounded resource use;
- locally pinned media dependencies.

Do not reuse by default:

- `VideoEncoder`;
- audio decoding/encoding;
- A/V interleaving;
- output video muxing;
- extension offscreen-document orchestration.

Mediabunny remains preferable for the normal Chain path because `VideoSampleSink.getSample(Infinity)` moves final-presentation-frame selection, dependency walking, decoder configuration, and B-frame ordering below the application layer.

## `StreamsDL`: acquisition, Range, staging, and FFmpeg reference

### Confirmed by repository inspection

`StreamsDL` is a browser-extension downloader with explicit HLS/DASH parsing and FFmpeg-WASM post-processing.

The current repository:

- vendors `m3u8-parser` and `mpd-parser`;
- resolves master playlists and quality variants;
- converts manifests into concrete segment lists;
- handles direct media URLs separately from HLS/DASH manifests;
- probes direct MP4 metadata;
- performs bounded direct-MP4 byte-range clipping;
- uses segmented/chunked acquisition and Blob-backed intermediate data;
- uses OPFS/internal handles for staging in some flows;
- distinguishes staging/internal persistence from final user-visible save;
- uses FFmpeg-WASM for MP4 copy-remux/repair, A/V merge, clipping, and timeline concatenation;
- uses `-c copy` for the normal MP4 remux path rather than re-encoding when codecs permit;
- enforces an approximately 800 MiB in-browser FFmpeg input ceiling;
- has explicit runtime/fallback handling for WebAssembly memory-allocation failure.

The active vendored FFmpeg cores are large assets: the inspected `0.10` and `0.11-core` WASM files are each roughly 24 MiB before runtime memory expansion.

The repository's own accepted runtime notes record `WebAssembly.Memory(): could not allocate memory` as a real constrained-browser/host failure mode and retain a fallback runtime for that case.

### Strong Range-validation lesson

`StreamsDL` contains a particularly useful rule for direct MP4 acquisition:

> absence of `Accept-Ranges` is not enough to reject Range support, and a normal `200` full response is not enough to prove it.

Its documented guardrail is to probe a one-byte request and treat **actual `206 Partial Content`** as the positive capability signal.

This should be reused in Img2Video Stage 0 result-media validation.

For the PWA, the relevant test is not merely:

```text
HEAD says Accept-Ranges: bytes
```

It is:

```text
GET Range: bytes=0-0
  -> 206 Partial Content
  -> valid Content-Range
  -> JavaScript can read the response under CORS
```

A `200` response to that Range request means the host may be ignoring Range and returning the full file. That can still permit playback/download, but it must not be classified as proven random-access support for the optimized Chain path.

### Staging/export lesson

`StreamsDL` independently enforces a distinction that matches our current PWA design:

```text
internal/staged media != final user-visible export
```

Its implementation may use OPFS or internal handles for intermediate persistence, but it does not automatically count such a write as a completed user-visible download. Final delivery is tracked separately.

This supports the Img2Video state model:

```text
remote-completed -> staged -> exported
```

The exact Files/Photos/share implementation remains an iPhone Safari/PWA validation item.

### Why StreamsDL does not justify FFmpeg-WASM for Chain

StreamsDL has genuinely FFmpeg-shaped requirements:

- repairing malformed or inconvenient containers;
- converting/remuxing TS/WebM/MKV/MOV-like inputs to MP4;
- merging separate video and audio tracks;
- clipping media;
- concatenating timeline cuts;
- regenerating timestamps and fast-start MP4 structure.

Img2Video Chain has none of those requirements in the selected product design.

For one final frame, shipping a roughly 24 MiB-class FFmpeg WASM core plus its runtime memory cost would add a much larger failure and resource surface than using the browser-native decoder through Mediabunny/WebCodecs.

Therefore StreamsDL strengthens, rather than weakens, the current decision:

> **Do not ship ffmpeg.wasm for normal Chain advancement.**

Treat FFmpeg-WASM as an optional future escape hatch only if a later product requirement genuinely needs container repair, format conversion, A/V muxing, concatenation, or another FFmpeg-native operation.

## Combined architecture lessons

The inspected projects now provide a useful capability ladder.

```text
Orion Lite
  -> controls existing HTMLVideoElement
  -> browser owns media bytes and decoding

RedGifs Downloader for Orion
  -> resolves direct MP4 URL
  -> extension downloads API owns transfer
  -> no JavaScript video processing

mothanext
  -> Range/sample-level MP4 processing
  -> WebCodecs decode/encode
  -> Mediabunny/mux pipeline
  -> proven browser-native media-engine reference

StreamsDL
  -> HLS/DASH parsing and segment acquisition
  -> MP4 Range probing/clipping
  -> OPFS/internal staging
  -> FFmpeg-WASM remux/repair/merge/concat
  -> proven heavyweight fallback and storage/download reference
```

For Img2Video, the preferred production subset remains:

```text
ArtWorks MP4 URL
  -> CORS-readable random access
  -> Mediabunny UrlSource
  -> Input({ formats: [MP4] })
  -> track.canDecode()
  -> VideoSampleSink.getSample(Infinity)
  -> canvas
  -> JPEG/PNG Blob
  -> persist transition state
  -> next ArtWorks task
```

## PWA versus extension capability boundary

Neither private repository proves that ArtWorks media will be accessible to an ordinary PWA.

Extension implementations may rely on privileges unavailable to GitHub Pages, including:

- host permissions;
- extension background/service-worker messaging;
- offscreen extension documents;
- `chrome.downloads`;
- `chrome.scripting`;
- extension CSP and packaged WASM exposure;
- extension-specific file/download behavior.

The portable media primitives are the parts relevant to the PWA:

- `fetch()`;
- HTTP Range when the server and CORS policy allow it;
- `Blob`/streams;
- canvas;
- WebCodecs;
- Mediabunny;
- IndexedDB/OPFS where supported.

Therefore Stage 0 still has to prove the provider/origin boundary independently.

## Stage 0 implications

The existing Stage 0 media gate should use these reference implementations to sharpen the test protocol.

For an already-paid ArtWorks result URL:

1. verify ordinary JavaScript CORS access;
2. issue `Range: bytes=0-0`;
3. record whether the server returns a real `206 Partial Content` and valid `Content-Range`;
4. do not classify a `200` full response as proven Range support;
5. test the pinned Mediabunny reader against the same host;
6. record bytes/ranges fetched without logging signed URL secrets;
7. verify `track.canDecode()` on the physical target iPhone;
8. retrieve the final presentation sample;
9. export a non-empty JPEG/PNG Blob;
10. record peak memory and whether full-file fallback occurred.

A separate local fixture still validates the decoder/library path without making any ArtWorks request.

## What remains not established

The reference repositories do **not** answer these project-specific questions:

- whether ArtWorks API CORS permits the intended production origin;
- whether ArtWorks result-media CORS permits JavaScript reads;
- whether the ArtWorks media host honors byte-range requests with `206`;
- whether representative Wan/LTX outputs decode correctly through the pinned Mediabunny build on the target iPhone;
- whether `getSample(Infinity)` yields the intended last displayed frame for those actual outputs;
- whether the resulting JPEG/PNG is accepted by the next ArtWorks image-to-video request;
- whether OPFS/user export behavior is acceptable in the installed iPhone PWA;
- exact production bundle and peak-memory measurements.

## Decision impact

No production architecture reversal is required.

The private repositories reduce implementation uncertainty and provide proven patterns for diagnostics, Range validation, staging, memory controls, and fallback design.

Current ordering remains:

1. **Mediabunny** — preferred Chain implementation;
2. **`<video>` + canvas** — minimal compatibility experiment;
3. **low-level MP4/WebCodecs techniques from `mothanext`** — diagnostic/fallback reference;
4. **FFmpeg-WASM techniques from `StreamsDL`** — future heavyweight escape hatch only when a genuinely FFmpeg-shaped requirement appears.

## Sources

Repository inspection performed 2026-08-07 against:

- `djebaz/mothanext` commit `6d415869092ecb7e41d0b66d8d79574df86b957e`;
- `djebaz/StreamsDL` commit `91205d0d4511ad49ae04563daf8b27480d2004c5`.

Source claims above are limited to the inspected repository content. No claim is made that either extension architecture or FFmpeg runtime has been validated on the target Img2Video iPhone/PWA environment.
