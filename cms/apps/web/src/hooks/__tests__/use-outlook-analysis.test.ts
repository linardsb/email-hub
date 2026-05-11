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

describe("use-outlook-analysis", () => {
  describe("useOutlookAnalysis", () => {
    it("passes correct mutation key and longMutationFetcher", async () => {
      const { useOutlookAnalysis } = await import("@/hooks/use-outlook-analysis");
      renderHook(() => useOutlookAnalysis());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/qa/outlook-analysis",
        longMutationFetcher,
      );
    });
  });

  describe("useOutlookModernize", () => {
    it("passes correct mutation key and longMutationFetcher", async () => {
      const { useOutlookModernize } = await import("@/hooks/use-outlook-analysis");
      renderHook(() => useOutlookModernize());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/qa/outlook-modernize",
        longMutationFetcher,
      );
    });
  });
});
