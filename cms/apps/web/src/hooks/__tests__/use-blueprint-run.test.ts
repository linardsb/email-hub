import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { seedSWRDefaults } from "./setup";

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

describe("use-blueprint-run", () => {
  it("returns run, resume, reset, isRunning, result, and error", async () => {
    const { useBlueprintRun } = await import("@/hooks/use-blueprint-run");
    const { result } = renderHook(() => useBlueprintRun({ projectId: 1 }));
    expect(result.current).toHaveProperty("run");
    expect(result.current).toHaveProperty("resume");
    expect(result.current).toHaveProperty("reset");
    expect(result.current.isRunning).toBe(false);
    expect(result.current.result).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
