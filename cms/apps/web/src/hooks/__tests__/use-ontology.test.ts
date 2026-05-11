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

describe("use-ontology", () => {
  describe("useOntologySyncStatus", () => {
    it("passes correct key with refresh interval", async () => {
      const { useOntologySyncStatus } = await import("@/hooks/use-ontology");
      renderHook(() => useOntologySyncStatus());
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/ontology/sync-status",
        fetcher,
        expect.objectContaining({ refreshInterval: 60_000 }),
      );
    });
  });

  describe("useOntologySync", () => {
    it("passes correct mutation key and longMutationFetcher", async () => {
      const { useOntologySync } = await import("@/hooks/use-ontology");
      renderHook(() => useOntologySync());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/ontology/sync", longMutationFetcher);
    });
  });

  describe("useCompetitiveReport", () => {
    it("passes base key without clientIds", async () => {
      const { useCompetitiveReport } = await import("@/hooks/use-ontology");
      renderHook(() => useCompetitiveReport());
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/ontology/competitive-report", fetcher);
    });

    it("includes client_ids params when provided", async () => {
      const { useCompetitiveReport } = await import("@/hooks/use-ontology");
      renderHook(() => useCompetitiveReport(["gmail", "outlook"]));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("client_ids=gmail");
      expect(key).toContain("client_ids=outlook");
    });
  });

  describe("useEmailClients", () => {
    it("passes correct key", async () => {
      const { useEmailClients } = await import("@/hooks/use-ontology");
      renderHook(() => useEmailClients());
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/ontology/clients", fetcher);
    });
  });
});
