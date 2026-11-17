/**
 * INT-559 — the in-memory container the ASR request carries.
 *
 * The dev ASR daemon decodes whatever container the body is (the file path
 * sent an AAC container before this change), so the samples travel inside a
 * 44-byte linear-PCM header. The header is bytes in a buffer and nothing
 * else: no name, no path, no extension. Every field is pinned so the daemon
 * can never be handed a shape it would decode as something else.
 */
import { describe, expect, it } from "vitest";

import { PCM_ENVELOPE_HEADER_BYTES, linearPcmEnvelope, pcmContentDescription } from "./envelope";
import type { PcmSegment } from "./types";

function ascii(bytes: Uint8Array, offset: number, length: number): string {
  return String.fromCharCode(...bytes.subarray(offset, offset + length));
}

function u32(bytes: Uint8Array, offset: number): number {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(offset, true);
}

function u16(bytes: Uint8Array, offset: number): number {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint16(offset, true);
}

const segment: PcmSegment = {
  samples: new Int16Array([0, 1, -2, 32_767, -32_768]),
  sampleRate: 16_000,
  channels: 1,
};

describe("linearPcmEnvelope", () => {
  it("is the header plus two bytes per sample", () => {
    expect(PCM_ENVELOPE_HEADER_BYTES).toBe(44);
    expect(linearPcmEnvelope(segment).byteLength).toBe(44 + 2 * 5);
  });

  it("carries the four tags where a decoder looks for them", () => {
    const bytes = linearPcmEnvelope(segment);
    expect(ascii(bytes, 0, 4)).toBe("RIFF");
    expect(ascii(bytes, 8, 4)).toBe("WAVE");
    expect(ascii(bytes, 12, 4)).toBe("fmt ");
    expect(ascii(bytes, 36, 4)).toBe("data");
  });

  it("describes the samples exactly: linear PCM, 16 bit, little-endian", () => {
    const bytes = linearPcmEnvelope(segment);
    expect(u32(bytes, 4)).toBe(36 + 10); // RIFF chunk size
    expect(u32(bytes, 16)).toBe(16); // fmt chunk size
    expect(u16(bytes, 20)).toBe(1); // linear PCM
    expect(u16(bytes, 22)).toBe(1); // channels
    expect(u32(bytes, 24)).toBe(16_000); // sample rate
    expect(u32(bytes, 28)).toBe(32_000); // byte rate
    expect(u16(bytes, 32)).toBe(2); // block align
    expect(u16(bytes, 34)).toBe(16); // bits per sample
    expect(u32(bytes, 40)).toBe(10); // data size
  });

  it("writes every sample little-endian after the header", () => {
    const bytes = linearPcmEnvelope(segment);
    expect(Array.from(bytes.subarray(44))).toEqual([
      0x00, 0x00, 0x01, 0x00, 0xfe, 0xff, 0xff, 0x7f, 0x00, 0x80,
    ]);
  });

  it("follows the segment's own rate and channel count", () => {
    const stereo = linearPcmEnvelope({
      samples: new Int16Array([1, 2, 3, 4]),
      sampleRate: 48_000,
      channels: 2,
    });
    expect(u16(stereo, 22)).toBe(2);
    expect(u32(stereo, 24)).toBe(48_000);
    expect(u32(stereo, 28)).toBe(192_000);
    expect(u16(stereo, 32)).toBe(4);
  });

  it("is a copy: zeroing the segment afterwards does not reach the envelope, and vice versa", () => {
    const own: PcmSegment = { samples: new Int16Array([5, 6]), sampleRate: 16_000, channels: 1 };
    const bytes = linearPcmEnvelope(own);
    own.samples.fill(0);
    expect(Array.from(bytes.subarray(44))).toEqual([5, 0, 6, 0]);
    bytes.fill(0);
    expect(Array.from(own.samples)).toEqual([0, 0]);
  });
});

describe("pcmContentDescription", () => {
  it("states the sample format so a daemon can skip the container", () => {
    expect(pcmContentDescription(segment)).toBe("pcm_s16le;rate=16000;channels=1");
    expect(
      pcmContentDescription({ samples: new Int16Array(0), sampleRate: 48_000, channels: 2 }),
    ).toBe("pcm_s16le;rate=48000;channels=2");
  });
});
