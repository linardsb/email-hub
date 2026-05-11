import { vi } from "vitest";
import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import { authFetch } from "@/lib/auth-fetch";

export const mockSWR = () => vi.mocked(useSWR);
export const mockSWRMutation = () => vi.mocked(useSWRMutation);
export const mockAuthFetch = () => vi.mocked(authFetch);

export function okResponse<T>(body: T, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function seedSWRDefaults(): void {
  mockSWR().mockReturnValue({
    data: undefined,
    error: undefined,
    isLoading: true,
    isValidating: false,
    mutate: vi.fn(),
  });
  mockSWRMutation().mockReturnValue({
    trigger: vi.fn(),
    reset: vi.fn(),
    data: undefined,
    error: undefined,
    isMutating: false,
  });
}
