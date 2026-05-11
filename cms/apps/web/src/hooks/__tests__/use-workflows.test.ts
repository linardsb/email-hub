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

describe("use-workflows", () => {
  describe("useWorkflows", () => {
    it("passes correct key with refresh interval", async () => {
      const { useWorkflows } = await import("@/hooks/use-workflows");
      renderHook(() => useWorkflows());
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/workflows",
        fetcher,
        expect.objectContaining({ refreshInterval: 60_000 }),
      );
    });
  });

  describe("useWorkflowStatus", () => {
    it("passes correct key with executionId", async () => {
      const { useWorkflowStatus } = await import("@/hooks/use-workflows");
      renderHook(() => useWorkflowStatus("exec-abc"));
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/workflows/exec-abc",
        fetcher,
        expect.objectContaining({ refreshInterval: 30_000 }),
      );
    });

    it("uses faster refresh when isActive", async () => {
      const { useWorkflowStatus } = await import("@/hooks/use-workflows");
      renderHook(() => useWorkflowStatus("exec-abc", true));
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/workflows/exec-abc",
        fetcher,
        expect.objectContaining({ refreshInterval: 5_000 }),
      );
    });

    it("passes null key when executionId is null", async () => {
      const { useWorkflowStatus } = await import("@/hooks/use-workflows");
      renderHook(() => useWorkflowStatus(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher, expect.any(Object));
    });
  });

  describe("useWorkflowLogs", () => {
    it("passes correct key with executionId", async () => {
      const { useWorkflowLogs } = await import("@/hooks/use-workflows");
      renderHook(() => useWorkflowLogs("exec-xyz"));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/workflows/exec-xyz/logs", fetcher);
    });

    it("passes null key when executionId is null", async () => {
      const { useWorkflowLogs } = await import("@/hooks/use-workflows");
      renderHook(() => useWorkflowLogs(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useTriggerWorkflow", () => {
    it("passes correct mutation key", async () => {
      const { useTriggerWorkflow } = await import("@/hooks/use-workflows");
      renderHook(() => useTriggerWorkflow());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/workflows/trigger", mutationFetcher);
    });
  });
});
