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
import { useProjects, useProject, useCreateProject } from "@/hooks/use-projects";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-projects", () => {
  describe("useProjects", () => {
    it("passes default params key", () => {
      renderHook(() => useProjects());
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/projects?page=1&page_size=10", fetcher);
    });

    it("passes custom params including clientOrgId and search", () => {
      renderHook(() => useProjects({ page: 2, pageSize: 25, clientOrgId: 5, search: "acme" }));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("page=2");
      expect(key).toContain("page_size=25");
      expect(key).toContain("client_org_id=5");
      expect(key).toContain("search=acme");
    });
  });

  describe("useProject", () => {
    it("passes correct key for valid id", () => {
      renderHook(() => useProject(42));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/projects/42", fetcher);
    });

    it("passes null key when id is null", () => {
      renderHook(() => useProject(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useCreateProject", () => {
    it("passes correct mutation key and fetcher", () => {
      renderHook(() => useCreateProject());
      expect(mockSWRMutation()).toHaveBeenCalledWith("/api/v1/projects", mutationFetcher);
    });
  });
});
