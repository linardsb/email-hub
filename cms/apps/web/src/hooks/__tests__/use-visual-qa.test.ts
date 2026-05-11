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
import { mutationFetcher, longMutationFetcher } from "@/lib/mutation-fetcher";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-visual-qa", () => {
  describe("useCaptureScreenshots", () => {
    it("passes correct mutation key and longMutationFetcher", async () => {
      const { useCaptureScreenshots } = await import("@/hooks/use-visual-qa");
      renderHook(() => useCaptureScreenshots());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/rendering/screenshots",
        longMutationFetcher,
      );
    });
  });

  describe("useVisualDiff", () => {
    it("passes correct mutation key and mutationFetcher", async () => {
      const { useVisualDiff } = await import("@/hooks/use-visual-qa");
      renderHook(() => useVisualDiff());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/rendering/visual-diff",
        mutationFetcher,
      );
    });
  });

  describe("useBaselines", () => {
    it("passes correct key with entityType and entityId", async () => {
      const { useBaselines } = await import("@/hooks/use-visual-qa");
      renderHook(() => useBaselines("template" as never, 20));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/rendering/baselines/template/20", fetcher);
    });

    it("passes null key when entityType is null", async () => {
      const { useBaselines } = await import("@/hooks/use-visual-qa");
      renderHook(() => useBaselines(null, 20));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });

    it("passes null key when entityId is null", async () => {
      const { useBaselines } = await import("@/hooks/use-visual-qa");
      renderHook(() => useBaselines("template" as never, null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useUpdateBaseline", () => {
    it("passes correct mutation key", async () => {
      const { useUpdateBaseline } = await import("@/hooks/use-visual-qa");
      renderHook(() => useUpdateBaseline("template" as never, 15));
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/rendering/baselines/template/15",
        expect.any(Function),
      );
    });
  });
});
