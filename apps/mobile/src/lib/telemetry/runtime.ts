/**
 * The process-scoped telemetry runtime (INT-145) — where "wired" actually
 * happens.
 *
 * One session begins when the app process starts, and it is crash-free unless
 * something says otherwise. That is the only honest way a client can compute
 * `client.crash_free_sessions`: the process that crashes cannot report its own
 * crash, so a crash is recorded by the NEXT launch finding the previous
 * session unclosed, or by a global error handler that ran before the process
 * died. Both paths land here.
 *
 * State is in memory and dies with the process, deliberately (files/10 §3 and
 * invariant 3's posture): the alternative is a counter file on a patient's
 * phone. The consequence is stated rather than hidden — a launch cannot see
 * whether the previous one crashed, so `recordPreviousLaunchCrashed()` exists
 * for a platform hook to call when one is available and nothing fabricates the
 * answer in the meantime.
 */
import { createCrashClient, type CrashClient, type CrashClientOptions } from "./client";
import {
  emitPerf,
  emptyPerfState,
  noopClientMetricSink,
  recordColdStart,
  recordCrash,
  recordSession,
  recordStall,
  type ClientMetricSink,
  type PerfState,
} from "./metrics";

export interface TelemetryRuntime {
  readonly crash: CrashClient;
  /** The current counters. Read-only; mutate through the functions below. */
  state(): PerfState;
  /** Fold in the launch duration and emit the current readings. */
  noteColdStart(ms: number): void;
  /** One main-thread stall past the watchdog threshold. */
  noteStall(): void;
  /** Report a crash, both as a counter and as a scrubbed crash report. */
  noteCrash(raw: unknown): Promise<void>;
  /** A platform hook found the previous launch had not closed its session. */
  recordPreviousLaunchCrashed(): void;
  /** Push the current readings to the sink. */
  flush(): void;
}

export interface TelemetryRuntimeOptions extends CrashClientOptions {
  /** Defaults to the discarding sink, so metrics are opt-in like crashes. */
  readonly metricSink?: ClientMetricSink;
}

export function createTelemetryRuntime(options: TelemetryRuntimeOptions): TelemetryRuntime {
  const sink = options.metricSink ?? noopClientMetricSink;
  const crash = createCrashClient(options);
  // The launch itself is the session.
  let state = recordSession(emptyPerfState());

  const flush = (): void => emitPerf(sink, state);

  return {
    crash,
    state: () => state,
    noteColdStart: (ms) => {
      state = recordColdStart(state, ms);
      flush();
    },
    noteStall: () => {
      state = recordStall(state);
    },
    noteCrash: async (raw) => {
      state = recordCrash(state);
      flush();
      await crash.captureCrash(raw);
    },
    recordPreviousLaunchCrashed: () => {
      state = recordCrash(recordSession(state));
    },
    flush,
  };
}
