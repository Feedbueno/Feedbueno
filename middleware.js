import { NextResponse } from 'next/server';

export function middleware(req) {
  const url = req.nextUrl.clone();
  const originalPath = url.pathname;
  const lowerPath = originalPath.toLowerCase();

  // Si la ruta tiene mayúsculas, redirige a minúsculas
  if (originalPath !== lowerPath) {
    url.pathname = lowerPath;
    return NextResponse.redirect(url, 308); // 308 = redirect permanente
  }

  // Si la ruta es de primer nivel (ej: /imetal) y no termina en feed.xml, redirige
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