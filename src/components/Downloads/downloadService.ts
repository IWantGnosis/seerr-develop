export type DownloadStatus =
  | 'QUEUED'
  | 'SEARCHING'
  | 'FOUND'
  | 'DOWNLOADING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface DownloadJob {
  id: string;
  title: string;
  year: number;
  posterPath: string;
  quality: string;
  status: DownloadStatus;
  progress: number;
  speed?: string;
  source?: string;
  destination?: string;
  error?: string;
  startedAt?: string;
  completedAt?: string;
}

const requestScraperApi = async (
  endpoint: string,
  options?: RequestInit
): Promise<Response | null> => {
  const host =
    typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';

  // 1. Try same-origin /scraper-api proxy first (avoids CORS & external port blocks)
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2500);
    const res = await fetch(`/scraper-api${endpoint}`, {
      ...options,
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (res.ok) return res;
  } catch {
    // Proxy unavailable or timed out
  }

  // 2. Direct port 5000 fallback
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2500);
    const res = await fetch(`http://${host}:5000/api${endpoint}`, {
      ...options,
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (res.ok) return res;
  } catch {
    // Port 5000 offline
  }

  return null;
};

export const getDownloadJobs = async (): Promise<DownloadJob[]> => {
  try {
    const res = await requestScraperApi('/downloads');
    if (res && res.ok) {
      const data = await res.json();
      if (Array.isArray(data)) {
        return data;
      }
    }
  } catch {
    // Return empty array when scraper service is not running
  }
  return [];
};

export const cancelDownloadJob = async (jobId: string): Promise<boolean> => {
  try {
    const res = await requestScraperApi(`/downloads/${jobId}/cancel`, {
      method: 'POST',
    });
    return !!res?.ok;
  } catch {
    return false;
  }
};

export const deleteDownloadJob = async (jobId: string): Promise<boolean> => {
  try {
    const res = await requestScraperApi(`/downloads/${jobId}/delete`, {
      method: 'POST',
    });
    if (res?.ok) return true;
    const res2 = await requestScraperApi(`/downloads/${jobId}`, {
      method: 'DELETE',
    });
    return !!res2?.ok;
  } catch {
    return false;
  }
};

export const clearCompletedDownloads = async (): Promise<boolean> => {
  try {
    const res = await requestScraperApi('/downloads/clear-completed', {
      method: 'POST',
    });
    return !!res?.ok;
  } catch {
    return false;
  }
};

export const getScraperLogs = async (): Promise<string[]> => {
  try {
    const res = await requestScraperApi('/logs');
    if (res && res.ok) {
      const data = await res.json();
      if (Array.isArray(data)) {
        return data;
      }
    }
  } catch {
    // Fallback when scraper is offline
  }
  return [];
};

export interface DownloadSettings {
  max_concurrent: number;
  active_count: number;
  queued_count: number;
}

export const getDownloadSettings = async (): Promise<DownloadSettings | null> => {
  try {
    const res = await requestScraperApi('/downloads/settings');
    if (res && res.ok) {
      return await res.json();
    }
  } catch {
    // Scraper offline
  }
  return null;
};

export const updateDownloadSettings = async (
  maxConcurrent: number
): Promise<DownloadSettings | null> => {
  try {
    const res = await requestScraperApi('/downloads/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_concurrent: maxConcurrent }),
    });
    if (res && res.ok) {
      return await res.json();
    }
  } catch {
    // Scraper offline
  }
  return null;
};


