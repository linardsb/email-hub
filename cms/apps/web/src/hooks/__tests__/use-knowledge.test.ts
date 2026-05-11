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

beforeEach(() => {
  vi.clearAllMocks();
  seedSWRDefaults();
});

describe("use-knowledge", () => {
  describe("useKnowledgeDocuments", () => {
    it("passes correct key with defaults", async () => {
      const { useKnowledgeDocuments } = await import("../use-knowledge");
      renderHook(() => useKnowledgeDocuments());
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("/api/v1/knowledge/documents?");
      expect(key).toContain("page=1");
      expect(key).toContain("page_size=12");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("includes domain filter when provided", async () => {
      const { useKnowledgeDocuments } = await import("../use-knowledge");
      renderHook(() => useKnowledgeDocuments({ domain: "brand" }));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("domain=brand");
    });

    it("includes tag filter when provided", async () => {
      const { useKnowledgeDocuments } = await import("../use-knowledge");
      renderHook(() => useKnowledgeDocuments({ tag: "footer" }));
      const key = mockSWR().mock.calls[0]![0] as string;
      expect(key).toContain("tag=footer");
    });
  });

  describe("useKnowledgeDocument", () => {
    it("passes correct key with valid documentId", async () => {
      const { useKnowledgeDocument } = await import("../use-knowledge");
      renderHook(() => useKnowledgeDocument(42));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/knowledge/documents/42");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when documentId is null", async () => {
      const { useKnowledgeDocument } = await import("../use-knowledge");
      renderHook(() => useKnowledgeDocument(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useKnowledgeDocumentContent", () => {
    it("passes correct key with valid documentId", async () => {
      const { useKnowledgeDocumentContent } = await import("../use-knowledge");
      renderHook(() => useKnowledgeDocumentContent(7));
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/knowledge/documents/7/content");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });

    it("passes null key when documentId is null", async () => {
      const { useKnowledgeDocumentContent } = await import("../use-knowledge");
      renderHook(() => useKnowledgeDocumentContent(null));
      expect(mockSWR().mock.calls[0]![0]).toBeNull();
    });
  });

  describe("useKnowledgeDomains", () => {
    it("passes correct key", async () => {
      const { useKnowledgeDomains } = await import("../use-knowledge");
      renderHook(() => useKnowledgeDomains());
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/knowledge/domains");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });
  });

  describe("useKnowledgeTags", () => {
    it("passes correct key", async () => {
      const { useKnowledgeTags } = await import("../use-knowledge");
      renderHook(() => useKnowledgeTags());
      expect(mockSWR().mock.calls[0]![0]).toBe("/api/v1/knowledge/tags");
      expect(mockSWR().mock.calls[0]![1]).toBe(fetcher);
    });
  });

  describe("useKnowledgeSearch", () => {
    it("uses mutation fetcher with correct key", async () => {
      const { useKnowledgeSearch } = await import("../use-knowledge");
      renderHook(() => useKnowledgeSearch());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/knowledge/search");
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });
  });

  describe("useGraphSearch", () => {
    it("uses mutation fetcher with correct key", async () => {
      const { useGraphSearch } = await import("../use-knowledge");
      renderHook(() => useGraphSearch());
      expect(mockSWRMutation().mock.calls[0]![0]).toBe("/api/v1/knowledge/graph/search");
      expect(mockSWRMutation().mock.calls[0]![1]).toBe(mutationFetcher);
    });
  });
});
