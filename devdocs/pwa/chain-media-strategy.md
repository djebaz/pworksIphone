<!-- VERSION$00001$ | Edited: 07/08 | TIME: 19:46 -->
# PWA Chain Media Strategy

## Purpose

Define the lightest reliable browser-side media path for Img2Video Chain mode.

Chain mode needs one operation from the previous ArtWorks result: obtain the final displayed video frame and convert it into an image suitable for the next `image-to-video` request.

The PWA does **not** need to transcode the video, re-encode a segment, process audio, or mux a new media container merely to advance a chain.

No ArtWorks generation request was made while preparing this document.

## Decision

**Do not ship FFmpeg or ffmpeg.wasm for Chain mode.**

Preferred architecture:

```text
ArtWorks MP4 result
    |
    v
fetch / HTTP Range access
    |
    v
MP4Box.js
    |-- MP4 structure / track metadata
    |-- AVC decoder configuration
    |-- sample table / sync-sample information
    |-- encoded video samples
    |
    v
WebCodecs VideoDecoder
    |
    v
final VideoFrame
    |
    v
Canvas / OffscreenCanvas
    |
    v
JPEG/PNG Blob
    |
    v
next ArtWorks task
```

No `VideoEncoder`, `AudioDecoder`, `AudioEncoder`, or output muxer is required for this path.

## Why MP4Box.js

MP4Box.js is a browser/Node MP4 parser and sample extractor. Its current documentation exposes enough information for the Chain use case, including:

- video track codec;
- dimensions;
- duration and timescale;
- number of samples;
- bitrate;
- sync-sample information;
- encoded sample data and timestamps.

This is substantially lighter than embedding FFmpeg/WASM when the application only needs MP4 demuxing and one decoded frame.

MP4Box.js does **not** decode H.264 itself. It provides the encoded access units and decoder configuration that can be supplied to WebCodecs.

## Why WebCodecs

WebCodecs provides low-level browser-native video decoding through `VideoDecoder` and returns `VideoFrame` objects that can be drawn into a canvas.

WebKit shipped H.264 `VideoDecoder` support before the Safari 26 cycle; Safari 26 expanded WebCodecs further by adding the audio encoder/decoder side. Audio support is irrelevant to Chain because only the final video frame is required.

Use feature detection and `VideoDecoder.isConfigSupported()` on the actual ArtWorks codec configuration before a Chain run is allowed to create billable work.

## Minimal decode algorithm

The robust target is the **final displayed frame**, not merely the last encoded sample in file order.

1. Parse enough of the MP4 to obtain the video track, codec configuration, sample timing, sync samples, and byte locations.
2. Identify the sample with the latest presentation time (`CTS` / presentation timestamp), accounting for sample duration.
3. Locate the nearest preceding random-access/sync sample required to decode that target.
4. Fetch only the MP4 byte ranges needed for the decoder configuration and that final GOP where practical.
5. Configure `VideoDecoder` with the MP4 AVC/H.264 configuration record supplied by the container.
6. Feed complete encoded video samples to `VideoDecoder` in decode order from the selected sync sample through the target sample.
7. Select the decoded `VideoFrame` matching the target presentation timestamp.
8. Draw that one frame to a canvas or `OffscreenCanvas`.
9. Export the canvas to a JPEG/PNG `Blob`.
10. Persist the transition-image state before submitting the next ArtWorks task.

This handles streams containing predictive frames more reliably than seeking approximately to `video.duration` and assuming the displayed frame is the true final frame.

## Important correction to the uploaded WebCodecs note

The user-supplied WebCodecs research describes a larger pipeline for decoding and **re-encoding** a segment. That pipeline is valid as a separate media-processing problem, but Img2Video Chain does not require the re-encode half.

For Chain, remove:

```text
VideoEncoder
AudioDecoder
AudioEncoder
muxer
segment output
```

The uploaded note also shows a `segment.webm` target while configuring H.264/AAC encoders. Container/codec compatibility would need deliberate muxing choices for a real re-encoding feature. That issue disappears entirely when Chain only exports a still image from the decoded final frame.

## Encoded sample handling

With an MP4 `avc1` track, WebCodecs should receive the AVC decoder configuration and encoded access units in the format expected by that configuration.

Do not split H.264 NAL units merely because MP4Box exposes their internal framing. Prefer passing complete encoded MP4 video samples/access units to `EncodedVideoChunk` unless a verified codec-format conversion is required.

This keeps sample timing, access-unit boundaries, and decoder dependencies intact.

## Network and CORS requirements

This architecture is lightweight computationally but still depends on the ArtWorks result-media host allowing browser access.

Validate on the real result URL:

- cross-origin `fetch()` succeeds from the PWA origin;
- HTTP Range access works if the optimized partial-fetch path is used;
- required response metadata can be inspected where needed;
- fetched bytes can be passed to MP4Box.js;
- a fallback `<video crossorigin="anonymous">` path can be drawn to canvas without tainting it, if that fallback is retained.

If the result-media origin does not grant the required CORS access, neither MP4Box.js range parsing nor readable cross-origin canvas extraction can be assumed to work directly from that URL.

## Fallback path

Keep the simpler browser-native path as a fallback/prototype:

```text
result URL / Blob
    -> HTMLVideoElement
    -> seek near end
    -> requestVideoFrameCallback()
    -> canvas
    -> Blob
```

This is easier to implement but gives less exact control over the final sample and keyframe/decode dependencies.

Recommended order:

1. prototype `<video>` + canvas for device compatibility;
2. use MP4Box.js + WebCodecs as the precise Chain implementation if the prototype cannot guarantee the true final frame;
3. do not introduce FFmpeg/WASM unless both browser-native paths fail on actual ArtWorks media.

## Preflight self-test before billable Chain work

Before the first Chain task is submitted, validate the media path using non-billable/local fixture media that matches the known ArtWorks output codec profile as closely as practical.

Check:

- `VideoDecoder` exists;
- actual codec configuration is supported with `VideoDecoder.isConfigSupported()`;
- MP4Box.js parses the fixture;
- a final frame can be decoded and exported to a non-empty image Blob;
- memory remains bounded on the target iPhone.

A result-media CORS test still requires a real provider-hosted result URL and should be performed against an already-paid completed task when possible.

## Media measurement boundary

MP4Box.js improves browser observability beyond a plain `<video>` element. It can provide container/track evidence such as codec string, dimensions, duration/timescale, sample count, bitrate, and sample timestamps.

However, it does not make the PWA a replacement for the repository's Python/`ffprobe` measurement and discovery tooling.

Keep the deliberate dual-runtime boundary:

- **PWA:** production orchestration, recovery, user workflow, lightweight MP4 inspection needed for Chain;
- **Python + probes:** authoritative deep media measurement, provider discovery, codec/container diagnostics, and reproducible evidence generation.

## Current status

**Architecture selected, implementation not yet validated on ArtWorks media.**

Remaining Chain-specific validation:

- ArtWorks result-media CORS and Range behavior;
- actual codec string/configuration returned by current Wan/LTX outputs;
- MP4Box.js parsing against those outputs;
- WebCodecs H.264 decode on the target iPhone/iOS version;
- correct final-presentation-frame selection on real outputs;
- canvas image export suitable for the next ArtWorks request.

## Sources

- User-supplied `webcodecs.md`, reviewed 2026-08-07.
- GPAC MP4Box.js documentation: MP4 parsing, track information, and sample extraction.
- WebKit Safari/WebCodecs release notes and H.264 VideoDecoder implementation history.
- MDN WebCodecs `VideoDecoder` / `VideoFrame` documentation.
