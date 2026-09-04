import { describe, expect, it } from "vitest";

import {
  createStartButton,
  EmbedError,
  startPrevisit,
  type LaunchResponse,
  type StartButtonConfig,
} from "./index.js";

const GOOD: LaunchResponse = {
  ticket: "hdr.payload.sig",
  launch_url: "https://intake.app/embed/launch#ticket=hdr.payload.sig",
  expires_at: 1_800_000_120,
};

function okFetch(body: unknown, ok = true, status = 200): typeof fetch {
  return (async () =>
    ({
      ok,
      status,
      json: async () => body,
    }) as unknown as Response) as unknown as typeof fetch;
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("startPrevisit", () => {
  it("fetches a ticket and opens the branded https launch url", async () => {
    let opened: string | undefined;
    const result = await startPrevisit({
      ticketEndpoint: "https://partner.example/vizite/ticket",
      fetchImpl: okFetch(GOOD),
      open: (url) => {
        opened = url;
      },
    });
    expect(result).toEqual(GOOD);
    expect(opened).toBe(GOOD.launch_url);
  });

  it("posts to the partner endpoint", async () => {
    let calledUrl: string | undefined;
    let method: string | undefined;
    const spyFetch = (async (url: string, init?: RequestInit) => {
      calledUrl = url;
      method = init?.method;
      return { ok: true, status: 200, json: async () => GOOD } as unknown as Response;
    }) as unknown as typeof fetch;
    await startPrevisit({
      ticketEndpoint: "/vizite/ticket",
      fetchImpl: spyFetch,
      open: () => undefined,
    });
    expect(calledUrl).toBe("/vizite/ticket");
    expect(method).toBe("POST");
  });

  it.each(["http://partner.example/t", "javascript:alert(1)", "not a url"])(
    "refuses a non-https partner endpoint (%s)",
    async (endpoint) => {
      await expect(
        startPrevisit({
          ticketEndpoint: endpoint,
          fetchImpl: okFetch(GOOD),
          open: () => undefined,
        }),
      ).rejects.toBeInstanceOf(EmbedError);
    },
  );

  it("refuses to open a non-https launch url", async () => {
    await expect(
      startPrevisit({
        ticketEndpoint: "https://partner.example/t",
        fetchImpl: okFetch({ ...GOOD, launch_url: "javascript:alert(1)" }),
        open: () => undefined,
      }),
    ).rejects.toThrow(/https/);
  });

  it("throws when the partner backend refuses", async () => {
    await expect(
      startPrevisit({
        ticketEndpoint: "https://partner.example/t",
        fetchImpl: okFetch(GOOD, false, 403),
        open: () => undefined,
      }),
    ).rejects.toThrow(/status 403/);
  });

  it.each([
    { launch_url: GOOD.launch_url, expires_at: 1 }, // missing ticket
    { ticket: "t", expires_at: 1 }, // missing launch_url
    { ticket: "t", launch_url: GOOD.launch_url }, // missing expires_at
    "not-an-object",
  ])("refuses a malformed launch response", async (body) => {
    await expect(
      startPrevisit({
        ticketEndpoint: "https://partner.example/t",
        fetchImpl: okFetch(body),
        open: () => undefined,
      }),
    ).rejects.toBeInstanceOf(EmbedError);
  });

  it("errors when no fetch implementation exists", async () => {
    const saved = globalThis.fetch;
    delete (globalThis as { fetch?: unknown }).fetch;
    try {
      await expect(
        startPrevisit({ ticketEndpoint: "https://partner.example/t", open: () => undefined }),
      ).rejects.toBeInstanceOf(EmbedError);
    } finally {
      globalThis.fetch = saved;
    }
  });
});

interface FakeButton {
  type: string;
  textContent: string;
  dataset: Record<string, string>;
  addEventListener: (event: string, handler: () => void) => void;
  click: () => void;
}

function fakeDocument(): { document: Document; button: FakeButton } {
  const handlers: Record<string, () => void> = {};
  const button: FakeButton = {
    type: "",
    textContent: "",
    dataset: {},
    addEventListener: (event, handler) => {
      handlers[event] = handler;
    },
    click: () => handlers["click"]?.(),
  };
  const document = { createElement: () => button } as unknown as Document;
  return { document, button };
}

describe("createStartButton", () => {
  it("renders a Turkish-labelled button and starts a handshake on click", async () => {
    const { document, button } = fakeDocument();
    let opened: string | undefined;
    const config: StartButtonConfig = {
      ticketEndpoint: "https://partner.example/t",
      fetchImpl: okFetch(GOOD),
      open: (url) => {
        opened = url;
      },
      document,
    };
    const el = createStartButton(config) as unknown as FakeButton;
    expect(el.type).toBe("button");
    expect(el.textContent).toBe("Ön muayeneyi başlat");
    expect(el.dataset["viziteEmbed"]).toBe("start-previsit");
    button.click();
    await flush();
    expect(opened).toBe(GOOD.launch_url);
  });

  it("honours a custom label and reports errors via onError", async () => {
    const { document, button } = fakeDocument();
    let caught: unknown;
    createStartButton({
      ticketEndpoint: "https://partner.example/t",
      fetchImpl: okFetch(GOOD, false, 500),
      open: () => undefined,
      label: "Start",
      document,
      onError: (error) => {
        caught = error;
      },
    });
    expect(button.textContent).toBe("Start");
    button.click();
    await flush();
    expect(caught).toBeInstanceOf(EmbedError);
  });
});
