import { NextResponse } from "next/server";

export function middleware(req) {
  const url = req.nextUrl.clone();

  // 1. Forzar minúsculas en la ruta
  const lowerPath = url.pathname.toLowerCase();
  if (url.pathname !== lowerPath) {
    url.pathname = lowerPath;
    return NextResponse.redirect(url, 301);
  }

  // 2. Redirigir carpetas a feed.xml
  if (!lowerPath.includes('.') && lowerPath !== '/') {
    url.pathname = `${lowerPath.replace(/\/$/, '')}/feed.xml`;
    return NextResponse.redirect(url, 301);
  }

  return NextResponse.next();
}

export const config = {
  matcher: '/:path*',
};