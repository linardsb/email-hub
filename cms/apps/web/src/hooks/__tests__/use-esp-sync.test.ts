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

describe("use-esp-sync", () => {
  describe("useESPConnections", () => {
    it("passes correct key", async () => {
      const { useESPConnections } = await import("../use-esp-sync");
      renderHook(() => useESPConnections());
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/connectors/sync/connections");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });
  });

  describe("useESPConnection", () => {
    it("passes correct key with valid id", async () => {
      const { useESPConnection } = await import("../use-esp-sync");
      renderHook(() => useESPConnection(4));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/connectors/sync/connections/4");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when id is null", async () => {
      const { useESPConnection } = await import("../use-esp-sync");
      renderHook(() => useESPConnection(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useCreateESPConnection", () => {
    it("uses mutation fetcher with correct key", async () => {
      const { useCreateESPConnection } = await import("../use-esp-sync");
      renderHook(() => useCreateESPConnection());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/connectors/sync/connections");
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });
  });

  describe("useDeleteESPConnection", () => {
    it("passes correct key with valid id", async () => {
      const { useDeleteESPConnection } = await import("../use-esp-sync");
      renderHook(() => useDeleteESPConnection(6));
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/connectors/sync/connections/6");
      expect(typeof mockSWRMutation().mock.calls[0]![1]).toBe("function");
    });

    it("passes empty string key when id is null", async () => {
      const { useDeleteESPConnection } = await import("../use-esp-sync");
      renderHook(() => useDeleteESPConnection(null));
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("");
    });
  });

  describe("useESPTemplates", () => {
    it("passes correct key with valid connectionId", async () => {
      const { useESPTemplates } = await import("../use-esp-sync");
      renderHook(() => useESPTemplates(2));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/connectors/sync/connections/2/templates");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when connectionId is null", async () => {
      const { useESPTemplates } = await import("../use-esp-sync");
      renderHook(() => useESPTemplates(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useESPTemplate", () => {
    it("passes correct key with both ids", async () => {
      const { useESPTemplate } = await import("../use-esp-sync");
      renderHook(() => useESPTemplate(2, "tpl-abc"));
      expect(mockSWR().mock.calls[0]![0]).toBe(
        "/api/v1/connectors/sync/connections/2/templates/tpl-abc",
      );
    });

    it("passes null key when connectionId is null", async () => {
      const { useESPTemplate } = await import("../use-esp-sync");
      renderHook(() => useESPTemplate(null, "tpl-abc"));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });

    it("passes null key when templateId is null", async () => {
      const { useESPTemplate } = await import("../use-esp-sync");
      renderHook(() => useESPTemplate(2, null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useImportESPTemplate", () => {
    it("uses mutation fetcher with correct key when connectionId set", async () => {
      const { useImportESPTemplate } = await import("../use-esp-sync");
      renderHook(() => useImportESPTemplate(3));
      expect(mockSWRMutation().mock.calls[0]![0]).toBe(
        "/api/v1/connectors/sync/connections/3/import",
      );
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });

    it("passes empty string key when connectionId is null", async () => {
      const { useImportESPTemplate } = await import("../use-esp-sync");
      renderHook(() => useImportESPTemplate(null));
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("");
    });
  });

  describe("usePushToESP", () => {
    it("uses mutation fetcher with correct key when connectionId set", async () => {
      const { usePushToESP } = await import("../use-esp-sync");
      renderHook(() => usePushToESP(5));
      expect(mockSWRMutation().mock.calls[0]![0]).toBe(
        "/api/v1/connectors/sync/connections/5/push",
      );
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });

    it("passes empty string key when connectionId is null", async () => {
      const { usePushToESP } = await import("../use-esp-sync");
      renderHook(() => usePushToESP(null));
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("");
    });
  });
});
