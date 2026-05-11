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

describe("use-tolgee", () => {
  describe("useTolgeeConnection", () => {
    it("passes correct key with connectionId", async () => {
      const { useTolgeeConnection } = await import("@/hooks/use-tolgee");
      renderHook(() => useTolgeeConnection(9));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/connectors/tolgee/connections/9", fetcher);
    });

    it("passes null key when connectionId is null", async () => {
      const { useTolgeeConnection } = await import("@/hooks/use-tolgee");
      renderHook(() => useTolgeeConnection(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useCreateTolgeeConnection", () => {
    it("passes correct mutation key", async () => {
      const { useCreateTolgeeConnection } = await import("@/hooks/use-tolgee");
      renderHook(() => useCreateTolgeeConnection());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/connectors/tolgee/connect",
        mutationFetcher,
      );
    });
  });

  describe("useTolgeeLanguages", () => {
    it("passes correct key with connectionId", async () => {
      const { useTolgeeLanguages } = await import("@/hooks/use-tolgee");
      renderHook(() => useTolgeeLanguages(11));
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/connectors/tolgee/connections/11/languages",
        fetcher,
      );
    });

    it("passes null key when connectionId is null", async () => {
      const { useTolgeeLanguages } = await import("@/hooks/use-tolgee");
      renderHook(() => useTolgeeLanguages(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useSyncKeys", () => {
    it("passes correct mutation key", async () => {
      const { useSyncKeys } = await import("@/hooks/use-tolgee");
      renderHook(() => useSyncKeys());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/connectors/tolgee/sync-keys",
        mutationFetcher,
      );
    });
  });

  describe("usePullTranslations", () => {
    it("passes correct mutation key", async () => {
      const { usePullTranslations } = await import("@/hooks/use-tolgee");
      renderHook(() => usePullTranslations());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/connectors/tolgee/pull",
        mutationFetcher,
      );
    });
  });

  describe("useLocaleBuild", () => {
    it("passes correct mutation key and longMutationFetcher", async () => {
      const { useLocaleBuild } = await import("@/hooks/use-tolgee");
      renderHook(() => useLocaleBuild());
      expect(mockSWRMutation()).toHaveBeenCalledWith(
        "/api/v1/connectors/tolgee/build-locales",
        longMutationFetcher,
      );
    });
  });
});
