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

describe("use-agent-skills", () => {
  describe("useAgentSkills", () => {
    it("passes correct SWR key", async () => {
      const { useAgentSkills } = await import("@/hooks/use-agent-skills");
      renderHook(() => useAgentSkills());
      expect(mockSWR()).toHaveBeenCalledWith(
        "/api/v1/agents/skills",
        fetcher,
        expect.objectContaining({ revalidateOnFocus: false, dedupingInterval: 600_000 }),
      );
    });
  });
});
