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
import { useQARun, useQAResult, useQALatest, useQAResults, useQAOverride } from "@/hooks/use-qa";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-qa", () => {
  describe("useQARun", () => {
    it("uses longMutationFetcher for QA run", () => {
      renderHook(() => useQARun());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/qa/run", longMutationFetcher);
    });
  });

  describe("useQAResult", () => {
    it("passes correct key for valid id", () => {
      renderHook(() => useQAResult(10));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/qa/results/10", fetcher);
    });

    it("passes null key when id is null", () => {
      renderHook(() => useQAResult(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useQALatest", () => {
    it("passes correct key for valid templateVersionId", () => {
      renderHook(() => useQALatest(77));
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/qa/results/latest?template_version_id=77",
        fetcher,
      );
    });

    it("passes null key when templateVersionId is null", () => {
      renderHook(() => useQALatest(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useQAResults", () => {
    it("passes default params key", () => {
      renderHook(() => useQAResults());
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/qa/results?page=1&page_size=20", fetcher);
    });

    it("includes optional filters in key", () => {
      renderHook(() => useQAResults({ page: 3, pageSize: 5, templateVersionId: 12, passed: true }));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("page=3");
      expect(key).toContain("page_size=5");
      expect(key).toContain("template_version_id=12");
      expect(key).toContain("passed=true");
    });
  });

  describe("useQAOverride", () => {
    it("passes correct mutation key for valid resultId", () => {
      renderHook(() => useQAOverride(8));
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/qa/results/8/override",
        mutationFetcher,
      );
    });

    it("passes null key when resultId is null", () => {
      renderHook(() => useQAOverride(null));
      expect(mockSWRMutation()).toHaveBeenCalledWith(null, mutationFetcher);
    });
  });
});
