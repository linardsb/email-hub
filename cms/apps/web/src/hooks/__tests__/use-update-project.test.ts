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

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-update-project", () => {
  describe("useUpdateProject", () => {
    it("passes correct key with projectId", async () => {
      const { useUpdateProject } = await import("../use-update-project");
      renderHook(() => useUpdateProject(17));
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/projects/17");
      expect(typeof mockSWRMutation().mock.calls[0]![1]).toBe("function");
    });
  });
});
