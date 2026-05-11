import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { mockSWR, seedSWRDefaults } from "./setup";

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

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-penpot", () => {
  describe("usePenpotConnections", () => {
    it("passes correct key with refresh interval", async () => {
      const { usePenpotConnections } = await import("@/hooks/use-penpot");
      renderHook(() => usePenpotConnections());
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/design-sync/connections",
        fetcher,
        expect.objectContaining({ refreshInterval: 60_000 }),
      );
    });

    it("filters data to penpot provider only", async () => {
      const { usePenpotConnections } = await import("@/hooks/use-penpot");
      mockSWR().mockReturnValue({
        data: [
          { id: 1, provider: "penpot", name: "P1" },
          { id: 2, provider: "figma", name: "F1" },
          { id: 3, provider: "penpot", name: "P2" },
        ],
        error: undefined,
        isLoading: false,
        isValidating: false,
        mutate: vi.fn(),
      });
      const { result } = renderHook(() => usePenpotConnections());
      expect(result.current.data).toHaveLength(2);
      expect(result.current.data?.every((c: { provider: string }) => c.provider === "penpot")).toBe(
        true,
      );
    });
  });
});
