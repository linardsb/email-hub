import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { mockSWR, seedSWRDefaults } from "./setup";

vi.mock("swr");
vi.mock("swr/mutation");
vi.mock("@/lib/swr-fetcher", () => ({ fetcher: vi.fn() }));
vi.mock("@/lib/mutation-fetcher", () => ({
  mutationFetcher: vi.fn(),
  longMutationFetcher: vi.fn(),
}));
vi.mock("@/lib/auth-fetch", () => ({
  authFetch: vi.fn(),
  LONG_TIMEOUT_MS: 120_000,
}));

import { fetcher } from "@/lib/swr-fetcher";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-compatibility-brief", () => {
  describe("useCompatibilityBrief", () => {
    it("passes correct key with valid projectId", async () => {
      const { useCompatibilityBrief } = await import("../use-compatibility-brief");
      renderHook(() => useCompatibilityBrief(20));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/projects/20/compatibility-brief");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when projectId is null", async () => {
      const { useCompatibilityBrief } = await import("../use-compatibility-brief");
      renderHook(() => useCompatibilityBrief(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });

    it("disables revalidateOnFocus", async () => {
      const { useCompatibilityBrief } = await import("../use-compatibility-brief");
      renderHook(() => useCompatibilityBrief(20));
      const options = mockSWR().mock.calls[0]![2];
      expect(options!.revalidateOnFocus).toBe(false);
    });
  });
});
