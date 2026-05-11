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

describe("use-briefs", () => {
  describe("useBriefConnections", () => {
    it("passes correct key", async () => {
      const { useBriefConnections } = await import("@/hooks/use-briefs");
      renderHook(() => useBriefConnections());
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/briefs/connections", fetcher);
    });
  });

  describe("useBriefItems", () => {
    it("passes correct key with connectionId", async () => {
      const { useBriefItems } = await import("@/hooks/use-briefs");
      renderHook(() => useBriefItems(3));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/briefs/connections/3/items", fetcher);
    });

    it("passes null key when connectionId is null", async () => {
      const { useBriefItems } = await import("@/hooks/use-briefs");
      renderHook(() => useBriefItems(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useBriefDetail", () => {
    it("passes correct key with itemId", async () => {
      const { useBriefDetail } = await import("@/hooks/use-briefs");
      renderHook(() => useBriefDetail(55));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/briefs/items/55", fetcher);
    });

    it("passes null key when itemId is null", async () => {
      const { useBriefDetail } = await import("@/hooks/use-briefs");
      renderHook(() => useBriefDetail(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useCreateBriefConnection", () => {
    it("passes correct mutation key and fetcher", async () => {
      const { useCreateBriefConnection } = await import("@/hooks/use-briefs");
      renderHook(() => useCreateBriefConnection());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/briefs/connections", mutationFetcher);
    });
  });

  describe("useDeleteBriefConnection", () => {
    it("passes correct mutation key", async () => {
      const { useDeleteBriefConnection } = await import("@/hooks/use-briefs");
      renderHook(() => useDeleteBriefConnection());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/briefs/connections/delete",
        mutationFetcher,
      );
    });
  });

  describe("useSyncBriefConnection", () => {
    it("passes correct mutation key", async () => {
      const { useSyncBriefConnection } = await import("@/hooks/use-briefs");
      renderHook(() => useSyncBriefConnection());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/briefs/connections/sync",
        mutationFetcher,
      );
    });
  });

  describe("useImportBrief", () => {
    it("passes correct mutation key", async () => {
      const { useImportBrief } = await import("@/hooks/use-briefs");
      renderHook(() => useImportBrief());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/briefs/import", mutationFetcher);
    });
  });

  describe("useAllBriefItems", () => {
    it("passes base key without options", async () => {
      const { useAllBriefItems } = await import("@/hooks/use-briefs");
      renderHook(() => useAllBriefItems());
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/briefs/items", fetcher);
    });

    it("includes query params when options provided", async () => {
      const { useAllBriefItems } = await import("@/hooks/use-briefs");
      renderHook(() => useAllBriefItems({ platform: "jira" as never, status: "new" as never }));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("platform=jira");
      expect(key).toContain("status=new");
    });
  });
});
