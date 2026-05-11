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

describe("use-reports", () => {
  describe("useGenerateQAReport", () => {
    it("passes correct mutation key and longMutationFetcher", async () => {
      const { useGenerateQAReport } = await import("@/hooks/use-reports");
      renderHook(() => useGenerateQAReport());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/reports/qa", longMutationFetcher);
    });
  });

  describe("useGenerateApprovalReport", () => {
    it("passes correct mutation key", async () => {
      const { useGenerateApprovalReport } = await import("@/hooks/use-reports");
      renderHook(() => useGenerateApprovalReport());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/reports/approval",
        longMutationFetcher,
      );
    });
  });

  describe("useGenerateRegressionReport", () => {
    it("passes correct mutation key", async () => {
      const { useGenerateRegressionReport } = await import("@/hooks/use-reports");
      renderHook(() => useGenerateRegressionReport());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/reports/regression",
        longMutationFetcher,
      );
    });
  });

  describe("useReportDownload", () => {
    it("passes correct mutation key with reportId", async () => {
      const { useReportDownload } = await import("@/hooks/use-reports");
      renderHook(() => useReportDownload("rpt-123"));
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/reports/rpt-123",
        expect.any(Function),
      );
    });

    it("passes empty string key when reportId is null", async () => {
      const { useReportDownload } = await import("@/hooks/use-reports");
      renderHook(() => useReportDownload(null));
      expect(mockSWRMutation()).toHaveBeenCalledWith("", expect.any(Function));
    });
  });
});
