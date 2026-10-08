import { Address6 } from 'ip-address';

export function getHostAndPort(): string {
  let host = process.env.HOST || '127.0.0.1';
  if (Address6.isValid(host)) {
    // If host is an IPv6 literal it needs to be placed in square brackets
    host = `[${host}]`;
  }

  const port = Number(process.env.PORT) || 5055;
  return `${host}:${port}`;
}
