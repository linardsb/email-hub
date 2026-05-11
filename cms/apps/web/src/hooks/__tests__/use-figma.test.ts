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
import { mutationFetcher } from "@/lib/mutation-fetcher";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-figma", () => {
  describe("useFigmaDesignTokens", () => {
    it("delegates to design-sync with correct key", async () => {
      const { useFigmaDesignTokens } = await import("../use-figma");
      renderHook(() => useFigmaDesignTokens(8));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/design-sync/connections/8/tokens");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when connectionId is null", async () => {
      const { useFigmaDesignTokens } = await import("../use-figma");
      renderHook(() => useFigmaDesignTokens(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useCreateFigmaConnection", () => {
    it("delegates to design-sync create with correct key", async () => {
      const { useCreateFigmaConnection } = await import("../use-figma");
      renderHook(() => useCreateFigmaConnection());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/design-sync/connections");
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });
  });
});
