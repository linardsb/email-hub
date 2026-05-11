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

describe("use-intelligence-stats", () => {
  describe("useComponentCoverage", () => {
    it("passes correct key", async () => {
      const { useComponentCoverage } = await import("../use-intelligence-stats");
      renderHook(() => useComponentCoverage());
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/components/?page=1&page_size=100");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });
  });

  describe("useGraphHealth", () => {
    it("passes graph-health-check as SWR key with custom fetcher", async () => {
      const { useGraphHealth } = await import("../use-intelligence-stats");
      renderHook(() => useGraphHealth());
      expect(mockSWR().mock.calls[0]![0]).toBe("graph-health-check");
      expect(typeof mockSWR().mock.calls[0]![1]).toBe("function");
      expect(mockSWR().mock.calls[0]![1]).not.toBe(fetcher);
    });
  });
});
