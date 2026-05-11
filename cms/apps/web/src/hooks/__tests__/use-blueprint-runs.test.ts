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

describe("use-blueprint-runs", () => {
  describe("useBlueprintRuns", () => {
    it("passes correct SWR key with projectId", async () => {
      const { useBlueprintRuns } = await import("@/hooks/use-blueprint-runs");
      renderHook(() => useBlueprintRuns(42));
      expect(mockSWR()).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/projects/42/blueprint-runs?"),
        fetcher,
        expect.objectContaining({ revalidateOnFocus: false }),
      );
    });

    it("passes null key when projectId is null", async () => {
      const { useBlueprintRuns } = await import("@/hooks/use-blueprint-runs");
      renderHook(() => useBlueprintRuns(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher, expect.any(Object));
    });

    it("includes status param when provided", async () => {
      const { useBlueprintRuns } = await import("@/hooks/use-blueprint-runs");
      renderHook(() => useBlueprintRuns(1, "completed"));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("status=completed");
    });
  });

  describe("useBlueprintRunDetail", () => {
    it("passes correct key with runId", async () => {
      const { useBlueprintRunDetail } = await import("@/hooks/use-blueprint-runs");
      renderHook(() => useBlueprintRunDetail(99));
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/blueprint-runs/99",
        fetcher,
        expect.any(Object),
      );
    });

    it("passes null key when runId is null", async () => {
      const { useBlueprintRunDetail } = await import("@/hooks/use-blueprint-runs");
      renderHook(() => useBlueprintRunDetail(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher, expect.any(Object));
    });
  });

  describe("useRunCheckpoints", () => {
    it("passes correct key with runId", async () => {
      const { useRunCheckpoints } = await import("@/hooks/use-blueprint-runs");
      renderHook(() => useRunCheckpoints("abc-123"));
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/blueprints/runs/abc-123/checkpoints",
        fetcher,
        expect.any(Object),
      );
    });

    it("passes null key when runId is null", async () => {
      const { useRunCheckpoints } = await import("@/hooks/use-blueprint-runs");
      renderHook(() => useRunCheckpoints(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher, expect.any(Object));
    });
  });
});
