import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NextRequest } from "next/server";

const mockAuth = vi.fn();

vi.mock("@/auth", () => ({
  auth: () => mockAuth(),
}));

async function callMiddleware(pathname: string) {
  const { default: middleware } = await import("../middleware");
  const request = new NextRequest(new URL(`https://app.test${pathname}`));
  return middleware(request);
}

describe("middleware", () => {
  beforeEach(() => {
    mockAuth.mockReset();
  });

  describe("public routes", () => {
    it("allows /login without auth", async () => {
      const res = await callMiddleware("/login");
      expect(res.headers.get("location")).toBeNull();
      expect(res.headers.get("x-middleware-next")).toBe("1");
      expect(mockAuth).not.toHaveBeenCalled();
    });
  });

  describe("known route + allowed role", () => {
    it("calls next() for admin on /users", async () => {
      mockAuth.mockResolvedValue({ user: { role: "admin" } });
      const res = await callMiddleware("/users");
      expect(res.headers.get("location")).toBeNull();
      expect(res.headers.get("x-middleware-next")).toBe("1");
    });

    it("calls next() for viewer on /projects/123", async () => {
      mockAuth.mockResolvedValue({ user: { role: "viewer" } });
      const res = await callMiddleware("/projects/123");
      expect(res.headers.get("location")).toBeNull();
      expect(res.headers.get("x-middleware-next")).toBe("1");
    });
  });

  describe("known route + denied role", () => {
    it("redirects viewer away from /users (admin-only)", async () => {
      mockAuth.mockResolvedValue({ user: { role: "viewer" } });
      const res = await callMiddleware("/users");
      expect(res.headers.get("location")).toBe("https://app.test/unauthorized");
    });
  });

  describe("unknown route (default-deny)", () => {
    it("redirects authenticated user to /unauthorized for unmapped route", async () => {
      mockAuth.mockResolvedValue({ user: { role: "admin" } });
      const res = await callMiddleware("/secret-area");
      expect(res.headers.get("location")).toBe("https://app.test/unauthorized");
    });
  });

  describe("auth() throws", () => {
    let warnSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    });

    afterEach(() => {
      warnSpy.mockRestore();
    });

    it("logs structured warn and falls through to next()", async () => {
      mockAuth.mockRejectedValue(new Error("session-decode-failed"));
      const res = await callMiddleware("/projects");
      expect(res.headers.get("x-middleware-next")).toBe("1");
      expect(warnSpy).toHaveBeenCalledWith(
        "middleware.auth_failed",
        expect.objectContaining({
          pathname: "/projects",
          err: "session-decode-failed",
        }),
      );
    });
  });
});
