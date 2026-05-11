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
import {
  useApprovals,
  useApproval,
  useCreateApproval,
  useApprovalDecide,
  useApprovalFeedback,
  useAddFeedback,
  useApprovalAudit,
  useBuild,
} from "@/hooks/use-approvals";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-approvals", () => {
  describe("useApprovals", () => {
    it("passes correct key for valid projectId", () => {
      renderHook(() => useApprovals(5));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/approvals/?project_id=5", fetcher);
    });

    it("passes null key when projectId is null", () => {
      renderHook(() => useApprovals(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useApproval", () => {
    it("passes correct key for valid id", () => {
      renderHook(() => useApproval(11));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/approvals/11", fetcher);
    });

    it("passes null key when id is null", () => {
      renderHook(() => useApproval(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useCreateApproval", () => {
    it("passes correct mutation key and fetcher", () => {
      renderHook(() => useCreateApproval());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/approvals/", mutationFetcher);
    });
  });

  describe("useApprovalDecide", () => {
    it("passes correct mutation key", () => {
      renderHook(() => useApprovalDecide(15));
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/approvals/15/decide",
        mutationFetcher,
      );
    });
  });

  describe("useApprovalFeedback", () => {
    it("passes correct key for valid id", () => {
      renderHook(() => useApprovalFeedback(20));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/approvals/20/feedback", fetcher);
    });

    it("passes null key when id is null", () => {
      renderHook(() => useApprovalFeedback(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useAddFeedback", () => {
    it("passes correct mutation key", () => {
      renderHook(() => useAddFeedback(22));
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/approvals/22/feedback",
        mutationFetcher,
      );
    });
  });

  describe("useApprovalAudit", () => {
    it("passes correct key for valid id", () => {
      renderHook(() => useApprovalAudit(30));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/approvals/30/audit", fetcher);
    });

    it("passes null key when id is null", () => {
      renderHook(() => useApprovalAudit(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useBuild", () => {
    it("passes correct key for valid id", () => {
      renderHook(() => useBuild(99));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/email/builds/99", fetcher);
    });

    it("passes null key when id is null", () => {
      renderHook(() => useBuild(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });
});
