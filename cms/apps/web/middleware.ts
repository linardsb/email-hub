import { auth } from "@/auth";
import { NextRequest, NextResponse } from "next/server";
import type { AppRole } from "@/auth";

// Route permission map — configure which roles can access each route
const ROLE_PERMISSIONS: Record<string, AppRole[]> = {
  "/": ["admin", "developer", "viewer"],
  "/projects": ["admin", "developer", "viewer"],
  "/example": ["admin", "developer", "viewer"],
  "/components": ["admin", "developer", "viewer"],
  "/users": ["admin"],
  "/approvals": ["admin", "developer", "viewer"],
  "/connectors": ["admin", "developer", "viewer"],
  "/intelligence": ["admin", "developer", "viewer"],
  "/knowledge": ["admin", "developer", "viewer"],
  "/figma": ["admin", "developer", "viewer"],
  "/briefs": ["admin", "developer", "viewer"],
  "/renderings": ["admin", "developer", "viewer"],
  "/ecosystem": ["admin", "developer", "viewer"],
  "/settings": ["admin", "developer"],
};

const PUBLIC_ROUTES = ["/login"];

function getRouteKey(pathname: string): string | null {
  for (const route of Object.keys(ROLE_PERMISSIONS)) {
    if (pathname === route || pathname.startsWith(route + "/")) {
      return route;
    }
  }
  return null;
}

function isPublicRoute(pathname: string): boolean {
  return PUBLIC_ROUTES.some((r) => pathname === r || pathname.startsWith(r + "/"));
}

export default async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip static assets and API routes
  if (pathname.startsWith("/_next") || pathname.startsWith("/api") || pathname.includes(".")) {
    return NextResponse.next();
  }

  // Public routes don't need auth
  if (isPublicRoute(pathname)) {
    return NextResponse.next();
  }

  // Check authentication — wrapped in try/catch because next-auth beta
  // can throw if session resolution fails, which kills the entire middleware
  try {
    const session = await auth();

    if (!session?.user) {
      const loginUrl = new URL("/login", request.url);
      loginUrl.searchParams.set("callbackUrl", pathname);
      return NextResponse.redirect(loginUrl);
    }

    // Check RBAC — default-deny on unknown routes or missing role config
    const routeKey = getRouteKey(pathname);
    const allowedRoles = routeKey === null ? undefined : ROLE_PERMISSIONS[routeKey];
    if (!allowedRoles) {
      return NextResponse.redirect(new URL("/unauthorized", request.url));
    }
    const userRole: string = session.user.role || "viewer";
    if (!allowedRoles.includes(userRole as AppRole)) {
      return NextResponse.redirect(new URL("/unauthorized", request.url));
    }
  } catch (err) {
    console.warn("middleware.auth_failed", {
      pathname,
      err: err instanceof Error ? err.message : String(err),
    });
    // Auth failed — let the page render (login page handles its own redirect)
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next|api|.*\\..*).*)"],
};
