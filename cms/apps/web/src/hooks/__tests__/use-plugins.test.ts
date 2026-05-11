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

describe("use-plugins", () => {
  describe("usePlugins", () => {
    it("passes correct key with refresh interval", async () => {
      const { usePlugins } = await import("@/hooks/use-plugins");
      renderHook(() => usePlugins());
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/plugins",
        fetcher,
        expect.objectContaining({ refreshInterval: 60_000 }),
      );
    });
  });

  describe("usePluginHealthSummary", () => {
    it("passes correct key", async () => {
      const { usePluginHealthSummary } = await import("@/hooks/use-plugins");
      renderHook(() => usePluginHealthSummary());
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/plugins/health",
        fetcher,
        expect.objectContaining({ refreshInterval: 60_000 }),
      );
    });
  });

  describe("usePluginEnable", () => {
    it("passes correct mutation key with encoded name", async () => {
      const { usePluginEnable } = await import("@/hooks/use-plugins");
      renderHook(() => usePluginEnable("my-plugin"));
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/plugins/my-plugin/enable",
        mutationFetcher,
      );
    });
  });

  describe("usePluginDisable", () => {
    it("passes correct mutation key", async () => {
      const { usePluginDisable } = await import("@/hooks/use-plugins");
      renderHook(() => usePluginDisable("test"));
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/plugins/test/disable",
        mutationFetcher,
      );
    });
  });

  describe("usePluginRestart", () => {
    it("passes correct mutation key", async () => {
      const { usePluginRestart } = await import("@/hooks/use-plugins");
      renderHook(() => usePluginRestart("test"));
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/plugins/test/restart",
        mutationFetcher,
      );
    });
  });
});
