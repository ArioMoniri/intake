/**
 * The in-memory container the ASR request carries (INT-559).
 *
 * The dev ASR daemon on the team box decodes the request body as a container
 * (the file path sent an AAC container before this change), so the samples
 * travel inside a 44-byte linear-PCM header. The header is bytes in a buffer
 * and nothing else — no name, no path, no extension — and the request also
 * states the sample format in a header line (`pcmContentDescription`) so a
 * daemon can skip the container altogether.
 */
import type { PcmSegment } from "./types";

export const PCM_ENVELOPE_HEADER_BYTES = 44;

const BYTES_PER_SAMPLE = 2;

function writeAscii(view: DataView, offset: number, tag: string): void {
  for (let index = 0; index < tag.length; index += 1) {
    view.setUint8(offset + index, tag.charCodeAt(index));
  }
}

/** A fresh byte array: the header, then every sample little-endian. */
export function linearPcmEnvelope(segment: PcmSegment): Uint8Array<ArrayBuffer> {
  const dataBytes = segment.samples.length * BYTES_PER_SAMPLE;
  const bytes = new Uint8Array(PCM_ENVELOPE_HEADER_BYTES + dataBytes);
  const view = new DataView(bytes.buffer);
  const blockAlign = segment.channels * BYTES_PER_SAMPLE;

  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // linear PCM
  view.setUint16(22, segment.channels, true);
  view.setUint32(24, segment.sampleRate, true);
  view.setUint32(28, segment.sampleRate * blockAlign, true); // byte rate
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 8 * BYTES_PER_SAMPLE, true); // bits per sample
  writeAscii(view, 36, "data");
  view.setUint32(40, dataBytes, true);

  for (let index = 0; index < segment.samples.length; index += 1) {
    view.setInt16(
      PCM_ENVELOPE_HEADER_BYTES + index * BYTES_PER_SAMPLE,
      segment.samples[index],
      true,
    );
  }
  return bytes;
}

/** The sample format, for the request header that lets a daemon skip the container. */
export function pcmContentDescription(segment: PcmSegment): string {
  return `pcm_s16le;rate=${segment.sampleRate};channels=${segment.channels}`;
}
