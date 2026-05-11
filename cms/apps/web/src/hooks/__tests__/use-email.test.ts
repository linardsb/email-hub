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
import { useEmailBuild, useEmailPreview } from "@/hooks/use-email";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-email", () => {
  describe("useEmailBuild", () => {
    it("uses longMutationFetcher for email build", () => {
      renderHook(() => useEmailBuild());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/email/build", longMutationFetcher, {
        throwOnError: false,
      });
    });
  });

  describe("useEmailPreview", () => {
    it("uses longMutationFetcher for email preview", () => {
      renderHook(() => useEmailPreview());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/email/preview", longMutationFetcher, {
        throwOnError: false,
      });
    });
  });
});
