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

export const getDownloadJobs = async (): Promise<DownloadJob[]> => {
  try {
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
    const res = await fetch(`http://${host}:5000/api/downloads`);
    if (res.ok) {
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
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
    const res = await fetch(`http://${host}:5000/api/downloads/${jobId}/cancel`, {
      method: 'POST',
    });
    return res.ok;
  } catch {
    return false;
  }
};

export const deleteDownloadJob = async (jobId: string): Promise<boolean> => {
  try {
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
    const res = await fetch(`http://${host}:5000/api/downloads/${jobId}/delete`, {
      method: 'POST',
    });
    if (res.ok) return true;
    const res2 = await fetch(`http://${host}:5000/api/downloads/${jobId}`, {
      method: 'DELETE',
    });
    return res2.ok;
  } catch {
    return false;
  }
};


export const clearCompletedDownloads = async (): Promise<boolean> => {
  try {
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
    const res = await fetch(`http://${host}:5000/api/downloads/clear-completed`, {
      method: 'POST',
    });
    return res.ok;
  } catch {
    return false;
  }
};


export const getScraperLogs = async (): Promise<string[]> => {
  try {
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
    const res = await fetch(`http://${host}:5000/api/logs`);
    if (res.ok) {
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
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
    const res = await fetch(`http://${host}:5000/api/downloads/settings`);
    if (res.ok) {
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
    const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
    const res = await fetch(`http://${host}:5000/api/downloads/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_concurrent: maxConcurrent }),
    });
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // Scraper offline
  }
  return null;
};


