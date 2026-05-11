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

describe("use-image-gen", () => {
  describe("useProjectImages", () => {
    it("passes correct key with projectId", async () => {
      const { useProjectImages } = await import("@/hooks/use-image-gen");
      renderHook(() => useProjectImages(10));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/projects/10/images", fetcher);
    });

    it("passes null key when projectId is null", async () => {
      const { useProjectImages } = await import("@/hooks/use-image-gen");
      renderHook(() => useProjectImages(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useGenerateImage", () => {
    it("passes correct mutation key and fetcher", async () => {
      const { useGenerateImage } = await import("@/hooks/use-image-gen");
      renderHook(() => useGenerateImage());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/images/generate", mutationFetcher);
    });
  });
});
