import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { mockSWRMutation, seedSWRDefaults } from "./setup";

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

import { longMutationFetcher } from "@/lib/mutation-fetcher";
import { useExport } from "@/hooks/use-connectors";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-connectors", () => {
  describe("useExport", () => {
    it("uses longMutationFetcher for export", () => {
      renderHook(() => useExport());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/connectors/export",
        longMutationFetcher,
      );
    });
  });
});
