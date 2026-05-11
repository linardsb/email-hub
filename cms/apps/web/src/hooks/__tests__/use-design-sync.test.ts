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

describe("use-design-sync", () => {
  describe("useDesignConnections", () => {
    it("passes correct key", async () => {
      const { useDesignConnections } = await import("../use-design-sync");
      renderHook(() => useDesignConnections());
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/design-sync/connections");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });
  });

  describe("useDesignConnection", () => {
    it("passes correct key with valid id", async () => {
      const { useDesignConnection } = await import("../use-design-sync");
      renderHook(() => useDesignConnection(3));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/design-sync/connections/3");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when id is null", async () => {
      const { useDesignConnection } = await import("../use-design-sync");
      renderHook(() => useDesignConnection(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useDesignTokens", () => {
    it("passes correct key with valid connectionId", async () => {
      const { useDesignTokens } = await import("../use-design-sync");
      renderHook(() => useDesignTokens(9));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/design-sync/connections/9/tokens");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when connectionId is null", async () => {
      const { useDesignTokens } = await import("../use-design-sync");
      renderHook(() => useDesignTokens(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useDesignComponents", () => {
    it("passes correct key with valid connectionId", async () => {
      const { useDesignComponents } = await import("../use-design-sync");
      renderHook(() => useDesignComponents(4));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/design-sync/connections/4/components");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when connectionId is null", async () => {
      const { useDesignComponents } = await import("../use-design-sync");
      renderHook(() => useDesignComponents(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useCreateDesignConnection", () => {
    it("uses mutation fetcher with correct key", async () => {
      const { useCreateDesignConnection } = await import("../use-design-sync");
      renderHook(() => useCreateDesignConnection());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/design-sync/connections");
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });
  });

  describe("useDeleteDesignConnection", () => {
    it("uses mutation fetcher with correct key", async () => {
      const { useDeleteDesignConnection } = await import("../use-design-sync");
      renderHook(() => useDeleteDesignConnection());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/design-sync/connections/delete");
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });
  });

  describe("useSyncDesignConnection", () => {
    it("uses mutation fetcher with correct key", async () => {
      const { useSyncDesignConnection } = await import("../use-design-sync");
      renderHook(() => useSyncDesignConnection());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/design-sync/connections/sync");
      expect(mockSWRMutation().mock.calls[0]![1]).toEqual(expect.any(Function));
    });
  });

  describe("useDesignFileStructure", () => {
    it("passes correct key with valid connectionId", async () => {
      const { useDesignFileStructure } = await import("../use-design-sync");
      renderHook(() => useDesignFileStructure(6));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/design-sync/connections/6/file-structure");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("includes depth param when provided", async () => {
      const { useDesignFileStructure } = await import("../use-design-sync");
      renderHook(() => useDesignFileStructure(6, 3));
      expect(mockSWR().mock.calls[0]![0]).toBe(
        "/api/v1/design-sync/connections/6/file-structure?depth=3",
      );
    });

    it("passes null key when connectionId is null", async () => {
      const { useDesignFileStructure } = await import("../use-design-sync");
      renderHook(() => useDesignFileStructure(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useDesignImport", () => {
    it("passes correct key with valid importId", async () => {
      const { useDesignImport } = await import("../use-design-sync");
      renderHook(() => useDesignImport(11));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/design-sync/imports/11");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when importId is null", async () => {
      const { useDesignImport } = await import("../use-design-sync");
      renderHook(() => useDesignImport(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });

    it("enables polling when flag is true", async () => {
      const { useDesignImport } = await import("../use-design-sync");
      renderHook(() => useDesignImport(11, true));
      const options = mockSWR().mock.calls[0]![2];
      expect(options!.refreshInterval).toBeGreaterThan(0);
    });
  });

  describe("useDesignImportByTemplate", () => {
    it("passes correct key with valid templateId", async () => {
      const { useDesignImportByTemplate } = await import("../use-design-sync");
      renderHook(() => useDesignImportByTemplate(15, 2));
      expect(mockSWR().mock.calls[0]![0]).toBe(
        "/api/v1/design-sync/imports/by-template/15?project_id=2",
      );
    });

    it("passes null key when templateId is null", async () => {
      const { useDesignImportByTemplate } = await import("../use-design-sync");
      renderHook(() => useDesignImportByTemplate(null, 2));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useExportImages", () => {
    it("uses mutation fetcher with correct key", async () => {
      const { useExportImages } = await import("../use-design-sync");
      renderHook(() => useExportImages());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe(
        "/api/v1/design-sync/connections/export-images",
      );
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });
  });

  describe("useGenerateBrief", () => {
    it("uses mutation fetcher with correct key", async () => {
      const { useGenerateBrief } = await import("../use-design-sync");
      renderHook(() => useGenerateBrief());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe(
        "/api/v1/design-sync/connections/generate-brief",
      );
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });
  });

  describe("useCreateDesignImport", () => {
    it("uses mutation fetcher with correct key", async () => {
      const { useCreateDesignImport } = await import("../use-design-sync");
      renderHook(() => useCreateDesignImport());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/design-sync/imports");
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });
  });

  describe("useConvertImport", () => {
    it("uses longMutationFetcher with correct key when importId set", async () => {
      const { useConvertImport } = await import("../use-design-sync");
      renderHook(() => useConvertImport(7));
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/design-sync/imports/7/convert");
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(longMutationFetcher);
    });

    it("passes empty string key when importId is null", async () => {
      const { useConvertImport } = await import("../use-design-sync");
      renderHook(() => useConvertImport(null));
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("");
    });
  });

  describe("useExtractComponents", () => {
    it("uses mutation fetcher with correct key when connectionId set", async () => {
      const { useExtractComponents } = await import("../use-design-sync");
      renderHook(() => useExtractComponents(12));
      expect(mockSWRMutation().mock.calls[0]![0]).toBe(
        "/api/v1/design-sync/connections/12/extract-components",
      );
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });

    it("passes empty string key when connectionId is null", async () => {
      const { useExtractComponents } = await import("../use-design-sync");
      renderHook(() => useExtractComponents(null));
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("");
    });
  });
});
