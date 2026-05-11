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
import {
  useComponents,
  useComponent,
  useComponentVersions,
  useComponentCompatibility,
} from "@/hooks/use-components";

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-components", () => {
  describe("useComponents", () => {
    it("passes default params key", () => {
      renderHook(() => useComponents());
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/components/?page=1&page_size=20", fetcher);
    });

    it("includes category and search in key", () => {
      renderHook(() => useComponents({ page: 2, pageSize: 10, category: "header", search: "nav" }));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("page=2");
      expect(key).toContain("page_size=10");
      expect(key).toContain("category=header");
      expect(key).toContain("search=nav");
    });
  });

  describe("useComponent", () => {
    it("passes correct key for valid id", () => {
      renderHook(() => useComponent(6));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/components/6", fetcher);
    });

    it("passes null key when id is null", () => {
      renderHook(() => useComponent(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useComponentVersions", () => {
    it("passes correct key for valid id", () => {
      renderHook(() => useComponentVersions(6));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/components/6/versions", fetcher);
    });

    it("passes null key when id is null", () => {
      renderHook(() => useComponentVersions(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });

  describe("useComponentCompatibility", () => {
    it("passes correct key for valid id", () => {
      renderHook(() => useComponentCompatibility(6));
      expect(mockSWR()).toHaveBeenCalledWith("/api/v1/components/6/compatibility", fetcher);
    });

    it("passes null key when id is null", () => {
      renderHook(() => useComponentCompatibility(null));
      expect(mockSWR()).toHaveBeenCalledWith(null, fetcher);
    });
  });
});
