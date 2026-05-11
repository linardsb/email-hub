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

describe("use-brand", () => {
  describe("useBrandConfig", () => {
    it("passes correct key with valid orgId", async () => {
      const { useBrandConfig } = await import("../use-brand");
      renderHook(() => useBrandConfig(5));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/orgs/5/brand");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when orgId is null", async () => {
      const { useBrandConfig } = await import("../use-brand");
      renderHook(() => useBrandConfig(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useUpdateBrandConfig", () => {
    it("uses mutation fetcher with correct key", async () => {
      const { useUpdateBrandConfig } = await import("../use-brand");
      renderHook(() => useUpdateBrandConfig());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/orgs/brand");
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });
  });
});
