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
import {
  useTemplates,
  useTemplate,
  useTemplateVersions,
  useTemplateVersion,
  useCreateTemplate,
  useSaveVersion,
  useUpdateTemplate,
} from "@/hooks/use-templates";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-templates", () => {
  describe("useTemplates", () => {
    it("passes correct key with default params", () => {
      renderHook(() => useTemplates(1));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toBe("/api/v1/projects/1/templates?page=1&page_size=50");
    });

    it("passes null key when projectId is null", () => {
      renderHook(() => useTemplates(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });

    it("includes search and status in key", () => {
      renderHook(() =>
        useTemplates(3, { page: 2, pageSize: 10, search: "promo", status: "draft" }),
      );
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("page=2");
      expect(key).toContain("page_size=10");
      expect(key).toContain("search=promo");
      expect(key).toContain("status=draft");
    });
  });

  describe("useTemplate", () => {
    it("passes correct key for valid id", () => {
      renderHook(() => useTemplate(7));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/templates/7", fetcher);
    });

    it("passes null key when id is null", () => {
      renderHook(() => useTemplate(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useTemplateVersions", () => {
    it("passes correct key for valid id", () => {
      renderHook(() => useTemplateVersions(5));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/templates/5/versions", fetcher);
    });

    it("passes null key when id is null", () => {
      renderHook(() => useTemplateVersions(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useTemplateVersion", () => {
    it("passes correct key when both params present", () => {
      renderHook(() => useTemplateVersion(5, 2));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/templates/5/versions/2", fetcher);
    });

    it("passes null key when templateId is null", () => {
      renderHook(() => useTemplateVersion(null, 2));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });

    it("passes null key when versionNumber is null", () => {
      renderHook(() => useTemplateVersion(5, null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useCreateTemplate", () => {
    it("passes correct mutation key for valid projectId", () => {
      renderHook(() => useCreateTemplate(3));
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/projects/3/templates",
        mutationFetcher,
      );
    });

    it("passes null key when projectId is null", () => {
      renderHook(() => useCreateTemplate(null));
      expect(mockSWRMutation()).toHaveBeenCalledWith(null, mutationFetcher);
    });
  });

  describe("useSaveVersion", () => {
    it("passes correct mutation key for valid templateId", () => {
      renderHook(() => useSaveVersion(9));
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/templates/9/versions",
        mutationFetcher,
      );
    });

    it("passes null key when templateId is null", () => {
      renderHook(() => useSaveVersion(null));
      expect(mockSWRMutation()).toHaveBeenCalledWith(null, mutationFetcher);
    });
  });

  describe("useUpdateTemplate", () => {
    it("passes correct mutation key for valid templateId", () => {
      renderHook(() => useUpdateTemplate(4));
      const key = mockSWRMutation().mock.calls[0]![0];
      expect(key).toBe("/api/v1/templates/4");
    });

    it("passes null key when templateId is null", () => {
      renderHook(() => useUpdateTemplate(null));
      const key = mockSWRMutation().mock.calls[0]![0];
      expect(key).toBeNull();
    });

    it("uses patchFetcher (not mutationFetcher)", () => {
      renderHook(() => useUpdateTemplate(4));
      const fetcherArg = mockSWRMutation().mock.calls[0]![1];
      expect(fetcherArg).not.toBe(mutationFetcher);
      expect(fetcherArg).not.toBe(longMutationFetcher);
    });
  });
});
