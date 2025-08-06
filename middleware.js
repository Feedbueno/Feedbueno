import { NextResponse } from 'next/server';

export function middleware(req) {
  const url = req.nextUrl.clone();
  const originalPath = url.pathname;
  const lowerPath = originalPath.toLowerCase();

  // Redirigir a minúsculas si es necesario
  if (originalPath !== lowerPath) {
    url.pathname = lowerPath;
    return NextResponse.redirect(url, 308);
  }

  // Redirigir /xxx a /xxx/feed.xml
  if (
    lowerPath !== '/' &&
    !lowerPath.endsWith('/feed.xml') &&
    lowerPath.split('/').length === 2
  ) {
    url.pathname = `${lowerPath}/feed.xml`;
    return NextResponse.redirect(url, 308);
  }

  return NextResponse.next();
}