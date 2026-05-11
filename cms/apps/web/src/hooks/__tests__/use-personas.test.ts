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
import { usePersonas, usePersona, useCreatePersona } from "@/hooks/use-personas";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-personas", () => {
  describe("usePersonas", () => {
    it("passes correct key", () => {
      renderHook(() => usePersonas());
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/personas", fetcher);
    });
  });

  describe("usePersona", () => {
    it("passes correct key for valid id", () => {
      renderHook(() => usePersona(3));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/personas/3", fetcher);
    });

    it("passes null key when id is null", () => {
      renderHook(() => usePersona(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useCreatePersona", () => {
    it("passes correct mutation key and fetcher", () => {
      renderHook(() => useCreatePersona());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/personas", mutationFetcher);
    });
  });
});
