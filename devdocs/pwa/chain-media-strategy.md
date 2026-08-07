<!-- VERSION$00002$ | Edited: 07/08 | TIME: 19:50 -->
# PWA Chain Media Strategy

## Purpose

Define the lightest reliable browser-side media path for Img2Video Chain mode.

Chain mode needs one operation from the previous ArtWorks result: obtain the final displayed video frame and convert it into an image suitable for the next `image-to-video` request.

The PWA does **not** need to transcode the video, re-encode a segment, process audio, or mux a new media container merely to advance a chain.

No ArtWorks generation request was made while preparing this document.

## Updated recommendation

**Do not ship FFmpeg or ffmpeg.wasm for Chain mode.**

The preferred implementation candidate is now **Mediabunny**, with MP4Box.js + direct WebCodecs kept as a lower-level fallback/debug path.

Preferred architecture:

```text
ArtWorks MP4 result URL
    |
    v
Mediabunny UrlSource
    |-- optimized remote byte reads / prefetch
    |-- custom fetch RequestInit when needed
    |
    v
Mediabunny Input + MP4 parser
    |-- track / codec / dimensions / duration
    |-- packet timing and statistics
    |
    v
InputVideoTrack.canDecode()
    |
    v
VideoSampleSink.getSample(Infinity)
    |-- WebCodecs-backed decode
    |-- presentation-order final frame
    |
    v
VideoSample / Canvas
    |
    v
JPEG/PNG Blob
    |
    v
next ArtWorks task
```

No `VideoEncoder`, audio decoder/encoder, output muxer, ffmpeg.wasm, or complete-video transcode is required.

## Why Mediabunny is a strong fit

Mediabunny is a pure-TypeScript browser media toolkit with zero dependencies. It combines container demuxing with abstractions over browser WebCodecs decoders and is designed for lazy/streamed media access.

For this project it removes several pieces of application-owned media plumbing that the MP4Box.js + raw WebCodecs design would otherwise require.

Relevant documented capabilities include:

- MP4/ISOBMFF input support;
- `UrlSource` for remote media with optimized reading and prefetch behavior;
- `UrlSourceOptions.requestInit` for normal Fetch API options/custom headers;
- `InputVideoTrack.canDecode()` to test whether the browser can decode the actual track;
- codec and full codec-parameter strings;
- coded/display dimensions and rotation;
- duration and timing information;
- packet statistics including packet count, average packet rate/FPS, and average bitrate;
- `VideoSampleSink` for decoded video frames;
- presentation-order frame retrieval;
- direct last-frame retrieval through `VideoSampleSink.getSample(Infinity)`;
- `VideoSample` conversion/drawing to canvas-compatible image sources.

The `getSample(Infinity)` behavior is especially valuable: the library defines `getSample(timestamp)` as returning the last sample in **presentation order** at or before the requested timestamp. Passing `Infinity` is explicitly documented as the way to retrieve the last sample.

That means the application does not need to manually:

- find the final presentation sample;
- find the preceding H.264 sync sample;
- construct `EncodedVideoChunk` objects;
- manage decode order versus presentation order;
- feed and flush `VideoDecoder` itself.

Those responsibilities are still present internally, but they move into a media library whose API is designed around exactly this operation.

## Minimal target algorithm

The intended Chain transition can be approximately:

```js
const input = new Input({
  source: new UrlSource(videoUrl),
  formats: [MP4],
});

const track = await input.getPrimaryVideoTrack();
if (!track || !(await track.canDecode())) {
  throw new Error('Result video is not decodable on this device.');
}

const sink = new VideoSampleSink(track);
const sample = await sink.getSample(Infinity);
if (!sample) {
  throw new Error('No final video frame was found.');
}

const canvas = document.createElement('canvas');
canvas.width = sample.displayWidth;
canvas.height = sample.displayHeight;
const ctx = canvas.getContext('2d');
sample.draw(ctx, 0, 0);

const transitionBlob = await new Promise((resolve, reject) => {
  canvas.toBlob(
    blob => blob ? resolve(blob) : reject(new Error('Frame export failed.')),
    'image/jpeg',
    0.95,
  );
});

sample.close();
input.dispose();
```

This is architecture-level pseudocode, not yet validated project runtime code. Exact imports/API details must follow the pinned Mediabunny version chosen during implementation.

## Network efficiency

Mediabunny's `UrlSource` is specifically intended for remote media and uses optimized reading/prefetch patterns rather than requiring the application to fetch the full MP4 into an `ArrayBuffer` first.

That aligns well with the mobile constraint: Chain only needs enough of the file to parse the MP4 and decode the final frame dependency region.

The exact byte traffic depends on:

- MP4 layout (`moov` placement);
- final GOP length;
- server Range behavior;
- Mediabunny's selected prefetch/cache configuration.

Measure actual network reads on a representative ArtWorks result before claiming a particular byte saving.

## CORS remains the controlling provider constraint

Mediabunny does not bypass browser security policy.

Its documentation explicitly warns that cross-origin `UrlSource` usage requires CORS to be configured correctly.

Validate against a real ArtWorks result URL:

- cross-origin browser fetch access;
- partial/range access used by the media reader;
- media bytes readable by JavaScript;
- actual H.264 track decodable through the target Safari/WebCodecs implementation;
- final frame can be exported into a Blob suitable for the next request.

If result-media CORS fails, replacing MP4Box.js with Mediabunny does not solve that provider boundary.

## Safari/iOS implications

Mediabunny relies on WebCodecs for browser-native codec decoding. Codec availability therefore remains dependent on the browser.

This is acceptable for the current known ArtWorks H.264/MP4 output target, subject to physical-device validation.

Use the library's own capability boundary:

```text
track.canDecode()
```

before attempting Chain advancement.

This is preferable to hard-coding a browser/version assumption.

## Comparison with MP4Box.js + raw WebCodecs

### Mediabunny

Advantages for Img2Video:

- one high-level library for MP4 parsing and decoded frame retrieval;
- explicit `getSample(Infinity)` last-frame operation;
- presentation-order semantics already handled;
- WebCodecs integration already implemented;
- optimized `UrlSource` network reads;
- useful media metadata/statistics;
- zero dependencies;
- highly tree-shakable library architecture.

Tradeoffs:

- a larger abstraction surface than the minimal MP4Box parser;
- a relatively substantial external media dependency that must be pinned and device-tested;
- exact bundle size for the selected imports must be measured;
- MPL-2.0 licensing obligations must be respected if the library source itself is modified and redistributed.

### MP4Box.js + direct WebCodecs

Advantages:

- lower-level control over MP4 boxes, packets and exact decode pipeline;
- useful as a diagnostic/fallback implementation if a Mediabunny behavior needs investigation;
- separates demuxing from browser decoder behavior explicitly.

Tradeoffs for this product:

- application must implement the final-GOP selection/decode pipeline itself;
- application owns more H.264/WebCodecs edge cases;
- more code to test on iOS for no user-visible benefit if Mediabunny's final-sample API works correctly.

### Recommendation

Prototype **Mediabunny first**.

Keep MP4Box.js + direct WebCodecs as the fallback/debug route, not the default production architecture.

The simple `<video>` + canvas route remains a minimal compatibility experiment, but it provides less deterministic sample-level behavior than the media-toolkit path.

## Dependency and security policy

The PWA will handle user credentials, so do not import Mediabunny from a third-party CDN at runtime.

If selected for production:

- pin a specific reviewed Mediabunny version;
- vendor the browser module/build under the repository-controlled `pwa/` tree;
- serve it from the same GitHub Pages origin as the application;
- include only required functionality where practical;
- keep Content Security Policy restrictive and avoid unnecessary third-party runtime script origins;
- preserve required MPL-2.0 notices/license obligations.

The project advertises strong tree shaking and very small builds for small subsets, but the exact Img2Video subset (`Input`, MP4 input, `UrlSource`, video decoding and `VideoSampleSink`) must be built and measured before assigning a concrete bundle-size number.

## Relation to the uploaded WebCodecs note

The user-supplied `webcodecs.md` describes a valid broader pipeline for partial MP4 decoding and re-encoding.

For Chain, its key insight remains correct: media decoding requires MP4-aware sample/configuration handling and keyframe dependencies.

Mediabunny is potentially useful precisely because it already implements those responsibilities around WebCodecs.

The following parts of the uploaded re-encoding pipeline remain unnecessary for Chain:

```text
VideoEncoder
AudioDecoder
AudioEncoder
muxer
segment output
```

## Media measurement boundary

Mediabunny materially improves what the PWA can inspect compared with plain `<video>` metadata.

Useful browser-visible data includes:

- container/track identity;
- codec and codec parameter string;
- coded/display dimensions;
- rotation/pixel aspect information;
- duration;
- packet count;
- average packet rate, which is useful as an average frame-rate measure;
- average bitrate;
- packet/sample timestamps.

This does **not** eliminate the deliberate dual-runtime boundary.

Keep:

- **PWA + Mediabunny:** production orchestration, Chain final-frame extraction, lightweight media validation/inspection;
- **Python + ffprobe/project probes:** authoritative provider discovery, detailed codec/container measurements, regression evidence, and investigation where exact ffprobe semantics are required.

The PWA should not be presented as a wholesale replacement for the diagnostic Python toolchain.

## Preflight/self-test before billable Chain work

Before the first Chain task is submitted on a device, validate the media path with a local/non-billable fixture that matches ArtWorks H.264 MP4 output as closely as practical:

1. construct a Mediabunny `Input` from the fixture;
2. obtain its primary video track;
3. verify `track.canDecode()`;
4. call `VideoSampleSink.getSample(Infinity)`;
5. render/export the returned final frame;
6. verify the Blob is non-empty and has the expected image type/dimensions;
7. dispose/close all media resources;
8. observe peak memory on the target iPhone.

Separately, use an already-paid ArtWorks result URL to validate remote CORS/range behavior when one is available.

## Current status

**Mediabunny is now the preferred Chain implementation candidate; physical-device/provider validation is still required.**

Remaining Chain-specific validation:

- ArtWorks result-media CORS and partial-read behavior;
- real ArtWorks result parsing through Mediabunny;
- `InputVideoTrack.canDecode()` on target iPhone/iOS;
- `VideoSampleSink.getSample(Infinity)` returns the expected true final displayed frame on representative Wan/LTX outputs;
- final canvas/JPEG Blob is accepted as the next ArtWorks image input;
- actual network byte count and memory usage are acceptable;
- selected vendored bundle size is acceptable.

## Sources

- User-supplied `webcodecs.md`, reviewed 2026-08-07.
- Mediabunny official documentation and API reference, reviewed 2026-08-07: Input, MP4 support, UrlSource, InputVideoTrack, VideoSampleSink, VideoSample, PacketStats, supported formats/codecs, installation and licensing.
- Mediabunny GitHub repository, reviewed 2026-08-07.
- GPAC MP4Box.js documentation, retained as the lower-level fallback/reference.
- WebKit Safari/WebCodecs release notes.
