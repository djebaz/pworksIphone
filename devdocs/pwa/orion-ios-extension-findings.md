<!-- VERSION$00001$ | Edited: 07/08 | TIME: 20:05 -->
# Orion iOS Extension Media Findings

## Purpose

Record what two supplied Orion extension packages actually do with video on iOS and what can or cannot be transferred to the Img2Video PWA architecture.

Packages inspected directly:

- `RedGifsDownloaderOrion-1.1.7.zip`
- `OrionLite-0.2.19 10.zip`

This is implementation inspection, not a claim about undocumented Orion internals outside the uploaded packages.

## Executive conclusion

Neither inspected extension performs heavyweight video processing.

They illustrate two different browser-extension patterns:

1. a privileged extension discovers a direct media URL and delegates the transfer to the browser downloads API;
2. a lightweight content script controls the page's existing `HTMLVideoElement` and lets the browser own network, demuxing, decoding, rendering, and audio.

This supports a minimal-browser-first PWA strategy, but extension privileges must not be confused with ordinary PWA capabilities.

## RedGifs Downloader for Orion 1.1.7

### Manifest findings

Confirmed from the uploaded `manifest.json`:

```json
{
  "manifest_version": 3,
  "host_permissions": [
    "https://api.redgifs.com/*",
    "https://media.redgifs.com/*"
  ],
  "permissions": [
    "downloads",
    "storage"
  ],
  "background": {
    "service_worker": "background.js"
  }
}
```

The extension therefore has explicit capabilities unavailable to a normal GitHub Pages PWA:

- host permissions for RedGifs API/media domains;
- extension background execution semantics;
- the browser extension downloads API.

### Media path

The content script defines the RedGifs API base and resolves a GIF/video record through the API.

Its resolution logic selects a direct MP4 URL using approximately:

```text
urls.hd || urls.sd
```

When the user asks to download, the content script sends a runtime message containing:

```text
type = rg-orion-download-api
url
filename
```

The background worker then calls the extension downloads API with the remote URL.

Conceptually:

```text
RedGifs page
    -> content script discovers video identity
    -> RedGifs API returns media URLs
    -> content script selects direct MP4 URL
    -> message to background service worker
    -> downloads.download({ url, filename })
    -> browser owns the transfer
```

### What it does not do

Inspection found no Chain-like media pipeline:

- no MP4 parser;
- no WebCodecs `VideoDecoder`;
- no WebCodecs `VideoEncoder`;
- no ffmpeg.wasm;
- no ArrayBuffer-based video transform;
- no canvas-based frame extraction;
- no transcoding/remuxing.

Playback-control code uses ordinary media-element properties such as `currentTime` and `playbackRate`, but the download path itself delegates the remote URL to the privileged browser API.

### PWA implication

This extension is evidence that Orion's extension environment can make privileged host requests/downloads when permissions are granted.

It is **not** evidence that:

- an ordinary PWA can bypass CORS;
- a Home Screen PWA has `browser.downloads`/`chrome.downloads`;
- ArtWorks result URLs will be JavaScript-readable from GitHub Pages.

Therefore the ArtWorks API/media CORS gates remain unchanged.

## Orion Lite AutoNext 0.2.19

### Manifest findings

Confirmed from the uploaded `manifest.json`:

```json
{
  "manifest_version": 3,
  "permissions": ["storage"],
  "content_scripts": [
    {
      "matches": [
        "*://motherless.com/*",
        "*://*.motherless.com/*",
        "*://motherless.xxx/*",
        "*://*.motherless.xxx/*"
      ],
      "run_at": "document_start"
    }
  ]
}
```

There is no background service worker, no downloads permission, and no explicit media-host API permission in this package.

### Media path

The content scripts find/control the site's existing `<video>` element.

Confirmed operations include:

```text
video.currentTime
video.playbackRate
video.play()
video.pause()
video.muted
video.duration
video.videoWidth / video.videoHeight
```

The script also sets inline-playback hints:

```text
playsinline
webkit-playsinline
video.playsInline = true
```

The source comments explicitly avoid adding autoplay/preload attributes in that path because of observed iOS/Orion loading/UI effects. Automatic playback is attempted programmatically with bounded/fallback behavior instead of being treated as guaranteed.

### What the browser owns

The extension does not fetch or decode the video itself.

Conceptually:

```text
page's existing media URL
    -> browser/WebKit networking
    -> browser demuxer
    -> browser decoder
    -> browser renderer/audio
    -> HTMLVideoElement controlled by extension script
```

The extension script only changes the element's state and presentation.

### PWA implication

This is relevant to Img2Video because it demonstrates how much normal video behavior should remain browser-owned on iOS.

Use `HTMLVideoElement` for ordinary operations where sample-level certainty is not required:

- playback/preview;
- play/pause;
- seeking UI;
- playback rate;
- dimensions;
- lifecycle events;
- inline presentation.

Do not introduce a media library merely to reproduce those operations.

## Three capability layers

The inspected implementations clarify three distinct layers:

### Layer A — page/browser media element

Example: Orion Lite.

```text
HTMLVideoElement
```

Browser owns media bytes and decode. Script controls playback/presentation.

### Layer B — privileged extension transfer

Example: RedGifs Downloader.

```text
direct media URL
    -> extension host/download permission
    -> browser download subsystem
```

The extension still avoids decoding/transcoding the file.

### Layer C — PWA sample-level media inspection

Img2Video Chain uniquely needs one exact decoded frame.

```text
ArtWorks MP4 URL
    -> JavaScript-readable bytes under CORS
    -> Mediabunny/WebCodecs
    -> exact final presentation sample
    -> canvas/JPEG transition image
```

This is the only normal production path where the PWA needs sample-level access to video bytes.

## Design consequences for Img2Video

### Keep playback browser-native

Do not route normal previews through Mediabunny. A native `<video>` element remains the simplest and most iOS-native playback surface.

### Keep Chain sample-accurate

For dependent Chain advancement, approximate `video.currentTime = duration` seeking is not the selected correctness mechanism.

Mediabunny remains preferred because its `VideoSampleSink` uses presentation-order semantics and explicitly supports retrieving the last sample with `getSample(Infinity)`.

### Keep downloads separate from Chain

A completed output does not need to pass through the Chain decoder merely to be exported.

Use the lightest browser-supported staging/export path for finished media. Only the transition image path needs exact frame decode.

### Do not infer PWA permissions from extensions

The RedGifs extension's successful direct download is based on declared extension permissions. It does not reduce the importance of ArtWorks CORS testing from the exact Pages origin.

### Treat autoplay as attended UX

Orion Lite's bounded autoplay/fallback handling is a useful implementation pattern for preview UX, but Img2Video correctness must never depend on automatic playback succeeding.

## Relation to Mediabunny

The supplied Mediabunny guide reinforces the division of labor:

- browser `<video>` for ordinary playback;
- Mediabunny only for lazy/sample-accurate reads;
- `VideoSampleSink.getSample(Infinity)` for the exact final frame;
- explicit cleanup for bounded VRAM/resource use.

This avoids reproducing functionality that WebKit already performs efficiently while retaining deterministic Chain behavior where needed.

## Security implication

Neither extension package provides a model for storing reusable ArtWorks credentials.

Orion Lite's storage use is for ordinary extension settings, not provider passwords. The Img2Video PWA credential design therefore remains unchanged:

- Password AutoFill/system password manager for persistence;
- credentials in memory while unlocked;
- IndexedDB/OPFS only for non-secret run/task/media state.

## Validation status

Confirmed by direct inspection of the supplied ZIPs:

- manifests and declared permissions;
- RedGifs background `downloads.download` path;
- RedGifs content-to-background download message;
- RedGifs API/media URL discovery pattern;
- Orion Lite media-element control path;
- Orion Lite inline-playback handling;
- absence of WebCodecs/FFmpeg/container-processing logic in the inspected packages.

Not established by these packages:

- ArtWorks CORS behavior;
- Safari Home Screen PWA download/export behavior;
- Orion browser implementation details outside the supplied extensions;
- whether an Orion extension companion should ever become a supported Img2Video product surface.

No ArtWorks generation request was made and no potentially billable task was submitted.
