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

describe("use-mcp", () => {
  describe("useMCPStatus", () => {
    it("passes correct key with refresh interval", async () => {
      const { useMCPStatus } = await import("@/hooks/use-mcp");
      renderHook(() => useMCPStatus());
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/mcp/status",
        fetcher,
        expect.objectContaining({ refreshInterval: 30_000, revalidateOnFocus: false }),
      );
    });
  });

  describe("useMCPTools", () => {
    it("passes correct key", async () => {
      const { useMCPTools } = await import("@/hooks/use-mcp");
      renderHook(() => useMCPTools());
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/mcp/tools",
        fetcher,
        expect.objectContaining({ revalidateOnFocus: false }),
      );
    });
  });

  describe("useMCPConnections", () => {
    it("passes correct key with refresh interval", async () => {
      const { useMCPConnections } = await import("@/hooks/use-mcp");
      renderHook(() => useMCPConnections());
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/mcp/connections",
        fetcher,
        expect.objectContaining({ refreshInterval: 15_000 }),
      );
    });
  });

  describe("useToggleMCPTool", () => {
    it("passes correct mutation key", async () => {
      const { useToggleMCPTool } = await import("@/hooks/use-mcp");
      renderHook(() => useToggleMCPTool());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/mcp/tools/toggle", mutationFetcher);
    });
  });

  describe("useMCPApiKeys", () => {
    it("passes correct key", async () => {
      const { useMCPApiKeys } = await import("@/hooks/use-mcp");
      renderHook(() => useMCPApiKeys());
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/mcp/api-keys",
        fetcher,
        expect.objectContaining({ revalidateOnFocus: false }),
      );
    });
  });

  describe("useGenerateMCPApiKey", () => {
    it("passes correct mutation key", async () => {
      const { useGenerateMCPApiKey } = await import("@/hooks/use-mcp");
      renderHook(() => useGenerateMCPApiKey());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/mcp/api-keys", mutationFetcher);
    });
  });
});
