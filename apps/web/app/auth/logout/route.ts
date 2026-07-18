import { NextRequest, NextResponse } from "next/server";

import { AUTH_COOKIE, safeReturnTo } from "../../../src/auth";

export function GET(request: NextRequest) {
  const response = NextResponse.redirect(
    new URL(safeReturnTo(request.nextUrl.searchParams.get("returnTo")), request.url),
  );
  response.cookies.delete(AUTH_COOKIE);
  return response;
}
