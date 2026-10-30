/**
 * The one expo-audio binding of the capture library (INT-559).
 *
 * expo-audio 57's `AudioStream` is real-time PCM from the microphone —
 * AVAudioEngine's input tap on iOS, AudioRecord on Android — delivered as
 * 100 ms ArrayBuffers and nothing else: no file, no URI, no recorder. The
 * import is dynamic for the same reason lib/livekit/nativeRoom.ts's is: the
 * module is native, and the capture library's tests run in node with a fake
 * port in its place.
 *
 * The port is single-use: `stop` releases the native object, so a new turn
 * creates a new stream.
 */
import type { PcmFormat, PcmStreamPort } from "./types";

export async function createExpoPcmStream(format: PcmFormat): Promise<PcmStreamPort> {
  const { AudioModule } = await import("expo-audio");
  const stream = new AudioModule.AudioStream({
    sampleRate: format.sampleRate,
    channels: format.channels,
    encoding: "int16",
  });
  let released = false;
  return {
    start: () => stream.start(),
    stop: () => {
      if (released) {
        return;
      }
      released = true;
      try {
        stream.stop();
      } finally {
        stream.release();
      }
    },
    onBuffer: (listener) => {
      const subscription = stream.addListener("audioStreamBuffer", listener);
      return () => subscription.remove();
    },
  };
}
