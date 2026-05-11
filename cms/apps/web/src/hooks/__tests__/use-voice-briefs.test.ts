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
import { longMutationFetcher } from "@/lib/mutation-fetcher";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-voice-briefs", () => {
  describe("useVoiceBriefs", () => {
    it("passes correct key with projectId", async () => {
      const { useVoiceBriefs } = await import("@/hooks/use-voice-briefs");
      renderHook(() => useVoiceBriefs(8));
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/projects/8/voice-briefs?page=1&page_size=20",
        fetcher,
        expect.objectContaining({ revalidateOnFocus: false, refreshInterval: 30_000 }),
      );
    });

    it("passes null key when projectId is null", async () => {
      const { useVoiceBriefs } = await import("@/hooks/use-voice-briefs");
      renderHook(() => useVoiceBriefs(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher, expect.any(Object));
    });

    it("includes custom page number", async () => {
      const { useVoiceBriefs } = await import("@/hooks/use-voice-briefs");
      renderHook(() => useVoiceBriefs(8, 3));
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/projects/8/voice-briefs?page=3&page_size=20",
        fetcher,
        expect.any(Object),
      );
    });
  });

  describe("useVoiceBrief", () => {
    it("passes correct key with both params", async () => {
      const { useVoiceBrief } = await import("@/hooks/use-voice-briefs");
      renderHook(() => useVoiceBrief(5, 12));
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/projects/5/voice-briefs/12",
        fetcher,
        expect.objectContaining({ revalidateOnFocus: false }),
      );
    });

    it("passes null key when projectId is null", async () => {
      const { useVoiceBrief } = await import("@/hooks/use-voice-briefs");
      renderHook(() => useVoiceBrief(null, 12));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher, expect.any(Object));
    });

    it("passes null key when briefId is null", async () => {
      const { useVoiceBrief } = await import("@/hooks/use-voice-briefs");
      renderHook(() => useVoiceBrief(5, null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher, expect.any(Object));
    });
  });

  describe("useGenerateFromBrief", () => {
    it("passes correct mutation key with projectId", async () => {
      const { useGenerateFromBrief } = await import("@/hooks/use-voice-briefs");
      renderHook(() => useGenerateFromBrief(4));
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/projects/4/voice-briefs/generate",
        longMutationFetcher,
      );
    });

    it("passes null key when projectId is null", async () => {
      const { useGenerateFromBrief } = await import("@/hooks/use-voice-briefs");
      renderHook(() => useGenerateFromBrief(null));
      expect(mockSWRMutation()).toHaveBeenCalledWith(null, longMutationFetcher);
    });
  });

  describe("useDeleteVoiceBrief", () => {
    it("passes correct mutation key with projectId", async () => {
      const { useDeleteVoiceBrief } = await import("@/hooks/use-voice-briefs");
      renderHook(() => useDeleteVoiceBrief(6));
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/projects/6/voice-briefs/delete",
        expect.any(Function),
      );
    });

    it("passes null key when projectId is null", async () => {
      const { useDeleteVoiceBrief } = await import("@/hooks/use-voice-briefs");
      renderHook(() => useDeleteVoiceBrief(null));
      expect(mockSWRMutation()).toHaveBeenCalledWith(null, expect.any(Function));
    });
  });
});
