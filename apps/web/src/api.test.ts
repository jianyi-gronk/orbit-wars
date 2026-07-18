import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, apiFetchWithRetry } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("API client", () => {
  it("uses same-origin credentials and parses JSON", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ publicId: "fleet_real" }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetcher);

    await expect(apiFetch("/api/v1/me/fleet")).resolves.toEqual({ publicId: "fleet_real" });
    expect(fetcher).toHaveBeenCalledWith(
      "/orbit-api/api/v1/me/fleet",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("preserves stable backend error codes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: { code: "fleet.not_found" } }), {
          headers: { "Content-Type": "application/json" },
          status: 404,
        }),
      ),
    );
    const error = await apiFetch("/api/v1/me/fleet").catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "fleet.not_found", status: 404 });
  });

  it("retries transient public reads but not stable not-found responses", async () => {
    const transientFetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ publicId: "replay_real" }), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        }),
      );
    vi.stubGlobal("fetch", transientFetcher);

    await expect(
      apiFetchWithRetry("/api/public/v1/replays/replay_real/compact", {}, { baseDelayMs: 0 }),
    ).resolves.toEqual({ publicId: "replay_real" });
    expect(transientFetcher).toHaveBeenCalledTimes(2);

    const notFoundFetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: "replay.not_found" } }), {
        headers: { "Content-Type": "application/json" },
        status: 404,
      }),
    );
    vi.stubGlobal("fetch", notFoundFetcher);
    await expect(
      apiFetchWithRetry("/api/public/v1/replays/missing/compact", {}, { baseDelayMs: 0 }),
    ).rejects.toMatchObject({ status: 404 });
    expect(notFoundFetcher).toHaveBeenCalledTimes(1);
  });
});
