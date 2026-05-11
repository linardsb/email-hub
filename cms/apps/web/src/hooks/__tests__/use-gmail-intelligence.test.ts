import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { mockSWRMutation, seedSWRDefaults } from "./setup";

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

import { longMutationFetcher } from "@/lib/mutation-fetcher";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-gmail-intelligence", () => {
  describe("useGmailPredict", () => {
    it("passes correct mutation key", async () => {
      const { useGmailPredict } = await import("@/hooks/use-gmail-intelligence");
      renderHook(() => useGmailPredict());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/qa/gmail-predict",
        longMutationFetcher,
      );
    });
  });

  describe("useGmailOptimize", () => {
    it("passes correct mutation key", async () => {
      const { useGmailOptimize } = await import("@/hooks/use-gmail-intelligence");
      renderHook(() => useGmailOptimize());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/qa/gmail-optimize",
        longMutationFetcher,
      );
    });
  });

  describe("useDeliverabilityScore", () => {
    it("passes correct mutation key", async () => {
      const { useDeliverabilityScore } = await import("@/hooks/use-gmail-intelligence");
      renderHook(() => useDeliverabilityScore());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/qa/deliverability-score",
        longMutationFetcher,
      );
    });
  });

  describe("useBIMICheck", () => {
    it("passes correct mutation key", async () => {
      const { useBIMICheck } = await import("@/hooks/use-gmail-intelligence");
      renderHook(() => useBIMICheck());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/qa/bimi-check", longMutationFetcher);
    });
  });
});
