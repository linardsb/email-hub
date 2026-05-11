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

describe("use-failure-patterns", () => {
  describe("useFailurePatterns", () => {
    it("passes correct SWR key with defaults", async () => {
      const { useFailurePatterns } = await import("@/hooks/use-failure-patterns");
      renderHook(() => useFailurePatterns({}));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("/api/v1/blueprints/failure-patterns?");
      expect(key).toContain("page=1");
      expect(key).toContain("page_size=20");
    });

    it("includes optional filters in key", async () => {
      const { useFailurePatterns } = await import("@/hooks/use-failure-patterns");
      renderHook(() => useFailurePatterns({ agentName: "scaffolder", projectId: 5 }));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("agent_name=scaffolder");
      expect(key).toContain("project_id=5");
    });

    it("passes fetcher", async () => {
      const { useFailurePatterns } = await import("@/hooks/use-failure-patterns");
      renderHook(() => useFailurePatterns({}));
      expect(mockSWR()).toHaveBeenCalledWith(expect.any(String), fetcher);
    });
  });

  describe("useFailurePatternStats", () => {
    it("passes correct key", async () => {
      const { useFailurePatternStats } = await import("@/hooks/use-failure-patterns");
      renderHook(() => useFailurePatternStats());
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("/api/v1/blueprints/failure-patterns/stats");
    });

    it("includes projectId when provided", async () => {
      const { useFailurePatternStats } = await import("@/hooks/use-failure-patterns");
      renderHook(() => useFailurePatternStats(7));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("project_id=7");
    });

    it("passes fetcher", async () => {
      const { useFailurePatternStats } = await import("@/hooks/use-failure-patterns");
      renderHook(() => useFailurePatternStats());
      expect(mockSWR()).toHaveBeenCalledWith(expect.any(String), fetcher);
    });
  });
});
