// INT-497 — the playback half of the turn, measured on AVFoundation.
//
// `make runtime-sim` charges playback on a virtual clock, and the dev dialogue's
// player (expo-audio) is AVPlayer on iOS. Neither tells us how long AVPlayer
// itself takes to START a local clip, or how much dead air it leaves between
// two clips. This tool answers exactly those two questions on the machine it
// runs on, with the same framework the phone uses:
//
//   cold      create an AVPlayer for a file and play it        → first-frame latency
//   preloaded the same, with the item already readyToPlay       → first-frame latency
//   chain     clip A ends, a NEW AVPlayer plays clip B          → dead air between them
//   queue     one AVQueuePlayer holds [A, B]                    → dead air between them
//
// "chain" is what useDialogueSession did before INT-497 (one createAudioPlayer
// per clip, the next one created when the previous one finished); "queue" is
// what expo-audio's AudioPlaylist is on iOS (AVQueuePlayer).
//
// The start of a clip is estimated as (host time) − (player currentTime) at the
// first observation where currentTime has advanced, so the poll interval does
// not leak into the figure. Output latency of the audio device is the same for
// every mode, so the DIFFERENCES between modes are what this measures; the
// absolute figures are this machine on this day (CLAUDE.md invariant 20) and
// never a property of the product. Playback runs at volume 0.
//
// Input files are agent-voice clips (synthetic, scripted text) — never patient
// audio (invariant 3). Nothing is written.
//
// Usage: swift scripts/voice/playback_gap.swift <runs> <clip> <clip> [<clip> …]
// Prints one JSON object.

import AVFoundation
import Foundation

func now() -> Double { ProcessInfo.processInfo.systemUptime * 1000.0 }

/// Spin the main run loop until `done` returns true or `timeoutMs` passes.
func spin(timeoutMs: Double, _ done: () -> Bool) -> Bool {
  let deadline = now() + timeoutMs
  while now() < deadline {
    if done() { return true }
    RunLoop.main.run(mode: .default, before: Date(timeIntervalSinceNow: 0.0005))
  }
  return done()
}

/// Host-time estimate of when `player` started rendering `item`, or nil.
func startEstimate(_ player: AVPlayer, of item: AVPlayerItem, timeoutMs: Double = 3000) -> Double? {
  var estimate: Double?
  _ = spin(timeoutMs: timeoutMs) {
    guard player.currentItem === item else { return false }
    let t = player.currentTime().seconds
    if t.isFinite && t > 0 {
      estimate = now() - t * 1000.0
      return true
    }
    return false
  }
  return estimate
}

func waitReady(_ item: AVPlayerItem) -> Bool {
  spin(timeoutMs: 3000) { item.status == .readyToPlay }
}

/// The clip's length from its own header: frames / rate. Synchronous, and the
/// same quantity the player's currentTime runs against.
func durationMs(_ url: URL) -> Double {
  guard let file = try? AVAudioFile(forReading: url) else { return .nan }
  return Double(file.length) / file.processingFormat.sampleRate * 1000.0
}

func cold(_ url: URL) -> Double? {
  let t0 = now()
  let item = AVPlayerItem(url: url)
  let player = AVPlayer(playerItem: item)
  player.volume = 0
  player.play()
  defer { player.pause() }
  guard let start = startEstimate(player, of: item) else { return nil }
  return start - t0
}

func preloaded(_ url: URL) -> Double? {
  let item = AVPlayerItem(url: url)
  let player = AVPlayer(playerItem: item)
  player.volume = 0
  guard waitReady(item) else { return nil }
  _ = spin(timeoutMs: 150) { false }
  let t0 = now()
  player.play()
  defer { player.pause() }
  guard let start = startEstimate(player, of: item) else { return nil }
  return start - t0
}

func chain(_ a: URL, _ b: URL) -> Double? {
  let itemA = AVPlayerItem(url: a)
  let playerA = AVPlayer(playerItem: itemA)
  playerA.volume = 0
  var endedAt: Double?
  let token = NotificationCenter.default.addObserver(
    forName: .AVPlayerItemDidPlayToEndTime, object: itemA, queue: .main
  ) { _ in endedAt = now() }
  defer { NotificationCenter.default.removeObserver(token) }
  playerA.play()
  guard let startA = startEstimate(playerA, of: itemA) else { return nil }
  let lengthA = durationMs(a)
  guard spin(timeoutMs: lengthA + 3000, { endedAt != nil }) else { return nil }
  // What the dialogue did: on "finished", tear down and create the next player.
  playerA.pause()
  let itemB = AVPlayerItem(url: b)
  let playerB = AVPlayer(playerItem: itemB)
  playerB.volume = 0
  playerB.play()
  defer { playerB.pause() }
  guard let startB = startEstimate(playerB, of: itemB) else { return nil }
  return startB - (startA + lengthA)
}

func queue(_ a: URL, _ b: URL) -> Double? {
  let itemA = AVPlayerItem(url: a)
  let itemB = AVPlayerItem(url: b)
  let player = AVQueuePlayer(items: [itemA, itemB])
  player.volume = 0
  player.play()
  defer { player.pause() }
  guard let startA = startEstimate(player, of: itemA) else { return nil }
  let lengthA = durationMs(a)
  guard let startB = startEstimate(player, of: itemB, timeoutMs: lengthA + 3000) else {
    return nil
  }
  return startB - (startA + lengthA)
}

func summary(_ values: [Double]) -> [String: Double] {
  guard !values.isEmpty else { return [:] }
  let sorted = values.sorted()
  func pct(_ p: Double) -> Double {
    let rank = max(0, Int((p / 100.0 * Double(sorted.count)).rounded(.up)) - 1)
    return sorted[min(rank, sorted.count - 1)]
  }
  let round1 = { (v: Double) in (v * 10).rounded() / 10 }
  return [
    "n": Double(sorted.count), "p50": round1(pct(50)), "p95": round1(pct(95)),
    "min": round1(sorted.first!), "max": round1(sorted.last!),
  ]
}

let args = CommandLine.arguments
guard args.count >= 4, let runs = Int(args[1]) else {
  FileHandle.standardError.write("usage: playback_gap.swift <runs> <clip> <clip> [...]\n".data(using: .utf8)!)
  exit(2)
}
let clips = args[2...].map { URL(fileURLWithPath: $0) }
var results: [String: [Double]] = ["cold": [], "preloaded": [], "chain": [], "queue": []]
for run in 0..<runs {
  let a = clips[run % clips.count]
  let b = clips[(run + 1) % clips.count]
  if let v = cold(a) { results["cold"]!.append(v) }
  if let v = preloaded(b) { results["preloaded"]!.append(v) }
  if let v = chain(a, b) { results["chain"]!.append(v) }
  if let v = queue(a, b) { results["queue"]!.append(v) }
}
var out: [String: Any] = [
  "tool": "scripts/voice/playback_gap.swift",
  "runs": runs,
  "clips": clips.count,
  "os": ProcessInfo.processInfo.operatingSystemVersionString,
]
for (mode, values) in results { out[mode + "_ms"] = summary(values) }
let data = try JSONSerialization.data(withJSONObject: out, options: [.sortedKeys, .prettyPrinted])
print(String(data: data, encoding: .utf8)!)
