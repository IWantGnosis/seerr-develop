import logger from '@server/logger';
import { DnsCacheManager } from 'dns-caching';
import dns from 'node:dns';

export let dnsCache: DnsCacheManager | undefined;

export function initializeDnsCache({
  forceMinTtl,
  forceMaxTtl,
}: {
  forceMinTtl?: number;
  forceMaxTtl?: number;
} = {}) {
  if (dnsCache) {
    logger.warn('DNS Cache is already initialized', { label: 'DNS Cache' });
    return;
  }

  logger.info('Initializing DNS Cache with public upstream DNS (Cloudflare & Google)', {
    label: 'DNS Cache',
  });

  // Set trusted public DNS servers to bypass ISP DNS hijacking (e.g. Jio 49.44.79.236)
  try {
    dns.setServers(['1.1.1.1', '1.0.0.1', '8.8.8.8', '8.8.4.4']);
  } catch (e) {
    logger.warn('Failed to set global DNS servers', {
      label: 'DNS Cache',
      message: e.message,
    });
  }

  dnsCache = new DnsCacheManager({
    logger,
    forceMinTtl: typeof forceMinTtl === 'number' ? forceMinTtl * 1000 : 0,
    forceMaxTtl: typeof forceMaxTtl === 'number' ? forceMaxTtl * 1000 : -1,
  });

  try {
    (dnsCache as any).resolver?.setServers([
      '1.1.1.1',
      '1.0.0.1',
      '8.8.8.8',
      '8.8.4.4',
    ]);
  } catch {}

  dnsCache.initialize();
}
