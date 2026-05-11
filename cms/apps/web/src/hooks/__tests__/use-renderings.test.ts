import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { mockSWR, mockSWRMutation, seedSWRDefaults } from "./setup";

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
import { longMutationFetcher } from "@/lib/mutation-fetcher";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-renderings", () => {
  describe("useRenderingTests", () => {
    it("passes correct key with page params", async () => {
      const { useRenderingTests } = await import("../use-renderings");
      renderHook(() => useRenderingTests({ page: 2, pageSize: 10 }));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("/api/v1/rendering/tests");
      expect(key).toContain("page=2");
      expect(key).toContain("page_size=10");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("includes status filter when provided", async () => {
      const { useRenderingTests } = await import("../use-renderings");
      renderHook(() => useRenderingTests({ status: "completed" }));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("status=completed");
    });

    it("omits empty params", async () => {
      const { useRenderingTests } = await import("../use-renderings");
      renderHook(() => useRenderingTests({}));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toBe("/api/v1/rendering/tests");
    });
  });

  describe("useRenderingTest", () => {
    it("passes correct key with valid testId", async () => {
      const { useRenderingTest } = await import("../use-renderings");
      renderHook(() => useRenderingTest(5));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/rendering/tests/5");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when testId is null", async () => {
      const { useRenderingTest } = await import("../use-renderings");
      renderHook(() => useRenderingTest(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useRenderingTestPolling", () => {
    it("passes correct key with valid testId", async () => {
      const { useRenderingTestPolling } = await import("../use-renderings");
      renderHook(() => useRenderingTestPolling(3));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/rendering/tests/3");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when testId is null", async () => {
      const { useRenderingTestPolling } = await import("../use-renderings");
      renderHook(() => useRenderingTestPolling(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });

    it("includes refreshInterval option", async () => {
      const { useRenderingTestPolling } = await import("../use-renderings");
      renderHook(() => useRenderingTestPolling(3));
      const options = mockSWR().mock.calls[0]![2];
      expect(options).toBeDefined();
      expect(options!.refreshInterval).toBeDefined();
    });
  });

  describe("useRequestRendering", () => {
    it("uses longMutationFetcher with correct key", async () => {
      const { useRequestRendering } = await import("../use-renderings");
      renderHook(() => useRequestRendering());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/rendering/tests");
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(longMutationFetcher);
    });
  });

  describe("useRenderingComparison", () => {
    it("uses longMutationFetcher with correct key", async () => {
      const { useRenderingComparison } = await import("../use-renderings");
      renderHook(() => useRenderingComparison());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/rendering/compare");
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(longMutationFetcher);
    });
  });
});
