<!-- VERSION$00003$ | Edited: 07/08 | TIME: 19:53 -->
# PWA Chain Media Strategy

## Purpose

Define the lightest reliable browser-side media path for Img2Video Chain mode.

Chain mode needs one operation from the previous ArtWorks result: obtain the final displayed video frame and convert it into an image suitable for the next `image-to-video` request.

The PWA does **not** need to transcode the video, re-encode a segment, process audio, or mux a new media container merely to advance a chain.

No ArtWorks generation request was made while preparing this document.

## Decision

**Do not ship FFmpeg or ffmpeg.wasm for Chain mode.**

The preferred implementation candidate is **Mediabunny**, with MP4Box.js + direct WebCodecs retained as a lower-level fallback/debug path.

Preferred architecture:

```text
ArtWorks MP4 result URL
    |
    v
Mediabunny UrlSource
    |-- lazy remote reads / prefetch
    |-- bounded cache
    |-- bounded application retry policy
    |
    v
Mediabunny Input({ formats: [MP4] })
    |-- MP4 parser only
    |-- track / codec / dimensions / duration
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
VideoSample.draw(canvas)
    |
    v
JPEG/PNG Blob
    |
    v
next ArtWorks task
```

No `VideoEncoder`, audio decoder/encoder, output muxer, ffmpeg.wasm, or complete-video transcode is required.

## Why Mediabunny fits this exact problem

The reviewed Mediabunny guide describes a pure-TypeScript, zero-dependency, tree-shakable media toolkit that combines demuxing with higher-level WebCodecs integration.

For Chain it removes application-owned responsibilities that MP4Box.js + raw WebCodecs would otherwise require.

Relevant documented capabilities include:

- MP4/ISOBMFF input support;
- lazy, partial file reads rather than mandatory full-file buffering;
- `UrlSource` for remote media with network-oriented prefetching;
- configurable source cache size;
- custom `RequestInit`, retry behavior and `fetchFn`;
- `InputVideoTrack.canDecode()` for the actual browser/device and codec configuration;
- codec and full codec-parameter strings;
- decoder configuration extraction;
- coded/display dimensions and rotation;
- duration, first timestamp and time-resolution information;
- packet statistics including packet count, average packet rate/FPS and average bitrate;
- `VideoSampleSink` for decoded frames;
- presentation-order sample semantics;
- explicit final-frame retrieval via `VideoSampleSink.getSample(Infinity)`;
- `VideoSample.draw()` with rotation-aware canvas drawing;
- explicit `VideoSample.close()` and `Input.dispose()` resource cleanup.

The `getSample(Infinity)` contract is especially valuable. The guide states that `VideoSampleSink` operates in presentation order and documents `getSample(Infinity)` as the way to extract the last sample. This avoids application-owned B-frame/decode-order bookkeeping.

## Minimal target algorithm

Architecture-level pseudocode:

```js
const source = new UrlSource(videoUrl, {
  maxCacheSize: 8 * 1024 * 1024,
  getRetryDelay: previousAttempts => {
    if (previousAttempts >= 3) return null;
    return Math.min(2 ** previousAttempts, 8);
  },
});

const input = new Input({
  source,
  formats: [MP4],
});

let sample;
try {
  const track = await input.getPrimaryVideoTrack();
  if (!track || !(await track.canDecode())) {
    throw new Error('Result video is not decodable on this device.');
  }

  const sink = new VideoSampleSink(track);
  sample = await sink.getSample(Infinity);
  if (!sample) {
    throw new Error('No final video frame was found.');
  }

  const canvas = document.createElement('canvas');
  canvas.width = sample.displayWidth;
  canvas.height = sample.displayHeight;

  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas 2D context is unavailable.');

  sample.draw(ctx, 0, 0);

  const transitionBlob = await new Promise((resolve, reject) => {
    canvas.toBlob(
      blob => blob ? resolve(blob) : reject(new Error('Frame export failed.')),
      'image/jpeg',
      0.95,
    );
  });

  // Persist transition-image state before the next billable POST.
} finally {
  sample?.close();
  input.dispose();
}
```

This is not yet project runtime code. Exact imports and APIs must be verified against the pinned Mediabunny version chosen during implementation.

## Important implementation rules from the full guide

### Import only MP4 support

Use:

```js
formats: [MP4]
```

Do **not** use `ALL_FORMATS` for the production Chain path.

The guide explicitly states that `ALL_FORMATS` pulls in all demuxers and can significantly increase bundle size. ArtWorks results are expected to be MP4, so unrelated input formats should be tree-shaken out.

If later provider evidence shows another container format, add that format explicitly rather than switching to `ALL_FORMATS` by default.

### Override the default UrlSource retry policy

Mediabunny's documented `UrlSource` default uses infinite exponential backoff capped at 16 seconds, except when it suspects a cross-origin CORS failure.

That default conflicts with this project's bounded-retry discipline.

Therefore the PWA must provide its own `getRetryDelay` with a finite retry budget. Retry state relevant to recovery should still be represented in the durable task ledger rather than hidden indefinitely inside a media library.

### Keep network memory bounded

`UrlSource` documents an 8 MiB default cache. This is compatible with the mobile-first design, but the value should be explicit or otherwise treated as a measured implementation parameter.

The Chain path should not first download the full result into an `ArrayBuffer` merely to obtain one frame.

Actual bytes read depend on:

- MP4 metadata placement;
- final decode dependency region/GOP;
- provider HTTP behavior;
- Mediabunny prefetch behavior;
- cache size.

Measure `source.onread` ranges in development against representative ArtWorks media. Do not log signed result URLs or other sensitive URL material.

### Dispose resources deterministically

The guide explicitly documents:

- `VideoSample.close()` to release underlying frame/VRAM resources;
- `Input.dispose()` to cancel outstanding reads, close decoders and dispose connected sink activity.

Do not rely only on garbage collection on iPhone. Close the final sample promptly after drawing it and dispose the `Input` in a `finally` path.

### Do not compute expensive media statistics in the Chain hot path

`computePacketStats()` can provide packet count, average packet rate/FPS and bitrate, but the guide warns that it may require many reads and can take several hundred milliseconds depending on the file.

Use it for diagnostics/evidence when needed, not as a prerequisite for extracting the final frame.

A bounded sample count such as `computePacketStats(100)` is suitable for quick estimates but must be labeled as an estimate where applicable.

## Presentation order and B-frames

The final image must represent the final **displayed** frame, not simply the final encoded packet in file order.

Mediabunny distinguishes presentation order from decode order. `VideoSampleSink` operations are documented as using presentation order, and `getSample(Infinity)` returns the last presented sample.

This is a material advantage over implementing the decoder pipeline ourselves because the application does not need to manually:

- find the final presentation sample;
- locate the preceding H.264 key packet;
- construct `EncodedVideoChunk` objects;
- feed packets in decode order;
- reorder decoded B-frames into presentation order;
- manage decoder flush/reset semantics.

MP4Box.js + direct WebCodecs remains useful if this abstraction ever needs to be debugged or verified at packet level.

## CanvasSink alternative

Mediabunny also exposes `CanvasSink`, whose retrieval methods are documented as analogous to `VideoSampleSink` and which handles scaling, rotation and cropping while producing canvas objects.

For one final frame, either approach is reasonable:

- `VideoSampleSink` + one application-owned canvas gives the clearest frame lifetime and explicit `sample.close()` control;
- `CanvasSink` can further reduce glue code if its exact final-frame behavior in the pinned version is validated.

Current preference remains `VideoSampleSink.getSample(Infinity)` because the guide explicitly shows that exact last-frame call.

## Network and CORS boundary

Mediabunny does not bypass browser security policy.

The guide explicitly warns that browser use of a cross-origin `UrlSource` requires proper CORS configuration.

Validate against a real ArtWorks result URL:

- JavaScript can read the cross-origin response;
- the provider supports the random/partial reads required by the remote source path;
- any relevant response metadata is accessible;
- the actual track is decodable on the target iPhone;
- final-frame extraction completes without a full-file memory spike;
- the exported image Blob is accepted by the next ArtWorks request.

Do not assume HTTP Range support merely from the existence of `UrlSource`; measure the actual provider requests and responses.

If result-media CORS fails, replacing MP4Box.js with Mediabunny does not solve that provider boundary.

## Safari/iOS capability boundary

Mediabunny relies on native WebCodecs for browser-supported codec decoding unless a custom decoder is registered.

Do not hard-code a Safari version assumption as the Chain gate.

Use:

```text
track.canDecode()
```

against the actual result track on the actual device.

No custom codec decoder is planned for H.264. If native decoding unexpectedly fails on the supported iPhone target, Chain should stop before submitting the next billable task and expose a clear incompatibility state.

## Media measurement boundary

Mediabunny materially improves what the PWA can inspect compared with a plain `<video>` element.

Useful browser-visible data can include:

- container/track identity;
- codec and codec parameter string;
- decoder configuration;
- coded/display dimensions;
- rotation and color-space information;
- duration and timestamps;
- packet count;
- average packet rate/FPS;
- average bitrate;
- packet/sample timestamps.

This does **not** eliminate the deliberate dual-runtime boundary.

Keep:

- **PWA + Mediabunny:** production orchestration, final-frame extraction and lightweight media validation needed by the product;
- **Python + ffprobe/project probes:** authoritative provider discovery, detailed codec/container measurement, regression evidence and investigation where exact ffprobe semantics are required.

The PWA is the production surface, not a wholesale replacement for the diagnostic Python toolchain.

## Dependency and security policy

The PWA handles user credentials, so do not import Mediabunny from a third-party CDN at runtime.

If selected for production:

- pin a reviewed Mediabunny version;
- vendor the browser module/build under repository-controlled `pwa/` source;
- serve it from the same GitHub Pages origin as the application;
- import only the required MP4/read/decode symbols;
- measure the resulting production bundle;
- keep Content Security Policy restrictive;
- preserve applicable MPL-2.0 notices/license obligations.

The project documentation says Mediabunny is zero-dependency and highly tree-shakable. Do not assign a concrete bundle-size number until the exact Img2Video import set has been built and measured.

## Preflight/self-test before billable Chain work

Before the first Chain task is submitted on a device, validate the media path with a local/non-billable fixture matching ArtWorks H.264 MP4 output as closely as practical:

1. create `Input` with `formats: [MP4]`;
2. obtain the primary video track;
3. verify `track.canDecode()`;
4. call `VideoSampleSink.getSample(Infinity)`;
5. draw/export the returned frame;
6. verify the Blob is non-empty and has the expected image type/dimensions;
7. close the sample and dispose the input;
8. observe peak memory on the target iPhone.

Separately, use an already-paid ArtWorks result URL to validate remote CORS and actual partial-read behavior when one is available.

## Comparison with alternatives

### Mediabunny — preferred

Advantages:

- one high-level library for MP4 parsing and final-frame decode;
- explicit presentation-order `getSample(Infinity)` operation;
- WebCodecs integration already handled;
- lazy remote reading and bounded source cache;
- runtime decodability check;
- useful media metadata/statistics;
- zero dependencies and tree-shakable design.

Tradeoffs:

- substantial external library surface that must be pinned and device-tested;
- exact production bundle size must be measured;
- application must override its default unbounded remote retry behavior;
- library lifecycle/resource semantics must be followed explicitly.

### MP4Box.js + direct WebCodecs — fallback/debug

Advantages:

- lower-level MP4/packet control;
- useful for verifying sample tables, key packets and decoder behavior;
- separates demuxing from decoding explicitly.

Tradeoffs:

- substantially more application code;
- application owns decode-order/presentation-order edge cases;
- no user-visible benefit if Mediabunny's final-sample path works correctly.

### `<video>` + canvas — minimal compatibility prototype

Advantages:

- smallest conceptual implementation;
- useful as a quick browser/media-host compatibility check.

Tradeoffs:

- less deterministic sample-level behavior;
- weaker inspection/control over final-frame selection.

### ffmpeg.wasm — rejected for Chain

Not justified for extracting one frame when lighter native/browser media paths exist.

## Current status

**Mediabunny remains the preferred Chain implementation candidate, now supported by the full guide rather than only selected API documentation. Physical-device/provider validation is still required.**

Remaining Chain-specific validation:

- ArtWorks result-media CORS;
- actual remote partial-read/request behavior;
- real ArtWorks MP4 parsing through the pinned Mediabunny build;
- `InputVideoTrack.canDecode()` on target iPhone/iOS;
- `VideoSampleSink.getSample(Infinity)` returns the expected true final displayed frame on representative Wan/LTX outputs;
- final JPEG/PNG Blob is accepted as the next ArtWorks image input;
- peak memory, network byte count and vendored bundle size are acceptable.

## Sources

- User-supplied `webcodecs.md`, reviewed 2026-08-07.
- User-supplied full Mediabunny guide (`mediabunny-full-guide.md`), reviewed 2026-08-07: introduction, installation, reading media files, input formats, media sinks, packets/samples, supported formats/codecs, conversion and output documentation.
- Mediabunny official documentation/API concepts represented in that supplied guide.
- GPAC MP4Box.js documentation, retained as the lower-level fallback/reference.
- WebKit Safari/WebCodecs documentation retained for platform-level validation.
