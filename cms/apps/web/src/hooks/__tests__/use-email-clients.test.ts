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

describe("use-email-clients", () => {
  describe("useEmailClients", () => {
    it("passes correct key", async () => {
      const { useEmailClients } = await import("../use-email-clients");
      renderHook(() => useEmailClients());
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/ontology/clients");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("disables revalidateOnFocus", async () => {
      const { useEmailClients } = await import("../use-email-clients");
      renderHook(() => useEmailClients());
      const options = mockSWR().mock.calls[0]![2];
      expect(options!.revalidateOnFocus).toBe(false);
    });
  });
});
