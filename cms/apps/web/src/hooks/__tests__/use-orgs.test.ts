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

describe("use-orgs", () => {
  describe("useOrgs", () => {
    it("passes correct key with defaults", async () => {
      const { useOrgs } = await import("../use-orgs");
      renderHook(() => useOrgs());
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("/api/v1/orgs?");
      expect(key).toContain("page=1");
      expect(key).toContain("page_size=50");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes custom page params", async () => {
      const { useOrgs } = await import("../use-orgs");
      renderHook(() => useOrgs({ page: 3, pageSize: 25 }));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("page=3");
      expect(key).toContain("page_size=25");
    });
  });
});
