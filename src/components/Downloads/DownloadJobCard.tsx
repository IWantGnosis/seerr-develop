import Badge from '@app/components/Common/Badge';
import CachedImage from '@app/components/Common/CachedImage';
import type {
  DownloadJob,
  DownloadStatus,
} from '@app/components/Downloads/downloadService';
import {
  CheckCircleIcon,
  ExclamationCircleIcon,
  NoSymbolIcon,
  XCircleIcon,
  XMarkIcon,
} from '@heroicons/react/24/solid';
import { useState } from 'react';

interface DownloadJobCardProps {
  job: DownloadJob;
  onCancel?: (jobId: string) => Promise<void> | void;
  onDelete?: (jobId: string) => Promise<void> | void;
}

const cleanErrorMessage = (err: string) => {
  if (!err) return '';
  let clean = err;
  if (clean.includes('Stacktrace:')) {
    clean = clean.split('Stacktrace:')[0].trim();
  }
  if (clean.startsWith('Message:')) {
    clean = clean.replace('Message:', '').trim();
  }
  if (clean.includes('DevToolsActivePort')) {
    return 'Chromium failed to launch (DevToolsActivePort). The latest update fixes this with 2GB shared memory.';
  }
  return clean.slice(0, 180);
};

const statusBadgeType: Record<
  DownloadStatus,
  'default' | 'danger' | 'success' | 'warning'
> = {
  QUEUED: 'warning',
  SEARCHING: 'default',
  FOUND: 'default',
  DOWNLOADING: 'default',
  COMPLETED: 'success',
  FAILED: 'danger',
  CANCELLED: 'danger',
};

const DownloadJobCard = ({ job, onCancel, onDelete }: DownloadJobCardProps) => {
  const [isActing, setIsActing] = useState(false);
  const isActive = ['QUEUED', 'SEARCHING', 'FOUND', 'DOWNLOADING'].includes(
    job.status
  );

  const handleCancel = async () => {
    if (!onCancel || isActing) return;
    setIsActing(true);
    try {
      await onCancel(job.id);
    } finally {
      setIsActing(false);
    }
  };

  const handleDelete = async () => {
    if (!onDelete || isActing) return;
    setIsActing(true);
    try {
      await onDelete(job.id);
    } finally {
      setIsActing(false);
    }
  };

  return (
    <article className="hover:bg-gray-750 overflow-hidden rounded-lg bg-gray-800 shadow transition">
      <div className="flex p-4 sm:p-5">
        <div className="relative h-28 w-20 flex-shrink-0 overflow-hidden rounded-md bg-gray-700 sm:h-36 sm:w-24">
          <CachedImage
            src={job.posterPath}
            type="tmdb"
            alt={`${job.title} poster`}
            fill
            sizes="(max-width: 640px) 80px, 96px"
            className="object-cover"
          />
        </div>
        <div className="min-w-0 flex-1 pl-4 sm:pl-5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h3 className="truncate text-lg font-semibold text-gray-100">
                {job.title}
              </h3>
              <p className="text-sm text-gray-400">{job.year}</p>
            </div>
            <div className="flex items-center gap-2">
              <Badge badgeType={statusBadgeType[job.status]}>{job.status}</Badge>

              {isActive && onCancel && (
                <button
                  type="button"
                  onClick={handleCancel}
                  disabled={isActing}
                  title="Cancel Scraper & Stop Process"
                  className="inline-flex items-center gap-1 rounded bg-red-600/20 px-2 py-1 text-xs font-semibold text-red-400 border border-red-500/30 hover:bg-red-600/30 hover:text-red-300 transition focus:outline-none disabled:opacity-50"
                >
                  <XCircleIcon className="h-4 w-4" />
                  <span>{isActing ? 'Stopping...' : 'Cancel'}</span>
                </button>
              )}

              {!isActive && onDelete && (
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={isActing}
                  title="Dismiss / Clear this card"
                  aria-label="Dismiss this download card"
                  className="inline-flex items-center justify-center rounded-md p-1.5 text-gray-400 hover:bg-gray-700 hover:text-white transition focus:outline-none disabled:opacity-50"
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>
              )}
            </div>
          </div>
          <div className="mt-4">
            <div className="mb-1 flex items-center justify-between text-sm text-gray-300">
              <span>Progress</span>
              <span className="font-semibold text-gray-100">{job.progress}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-gray-700">
              <div
                className={`h-full rounded-full transition-all ${
                  job.status === 'FAILED' || job.status === 'CANCELLED'
                    ? 'bg-red-500'
                    : job.status === 'COMPLETED'
                    ? 'bg-green-500'
                    : 'bg-indigo-500'
                }`}
                style={{ width: `${job.progress}%` }}
              />
            </div>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-gray-400">Quality</dt>
              <dd className="text-gray-100">{job.quality}</dd>
            </div>
            {job.speed && (
              <div>
                <dt className="text-gray-400">Speed</dt>
                <dd className="text-gray-100">{job.speed}</dd>
              </div>
            )}
            {job.source && (
              <div>
                <dt className="text-gray-400">Source</dt>
                <dd className="truncate text-gray-100">{job.source}</dd>
              </div>
            )}
            {job.destination && (
              <div className="col-span-2 sm:col-span-3 mt-1 border-t border-gray-700/60 pt-2">
                <dt className="text-gray-400">Save Destination</dt>
                <dd
                  className="truncate font-mono text-xs text-indigo-300"
                  title={job.destination}
                >
                  📁 {job.destination}
                </dd>
              </div>
            )}
          </dl>
          {job.status === 'CANCELLED' && (
            <p className="mt-3 flex items-center gap-1.5 text-sm text-yellow-400">
              <NoSymbolIcon className="h-5 w-5 flex-shrink-0" />
              Process stopped by user.
            </p>
          )}
          {job.error && (
            <div className="mt-3 flex items-start gap-2 rounded-md bg-red-950/40 p-2.5 text-xs text-red-300 border border-red-800/40">
              <ExclamationCircleIcon className="h-4 w-4 flex-shrink-0 text-red-400 mt-0.5" />
              <span className="line-clamp-2 leading-relaxed" title={job.error}>
                {cleanErrorMessage(job.error)}
              </span>
            </div>
          )}
          {job.completedAt && (
            <p className="mt-3 flex items-center gap-1.5 text-sm text-green-300">
              <CheckCircleIcon className="h-5 w-5 flex-shrink-0" />
              {job.completedAt.startsWith('Completed')
                ? job.completedAt
                : `Completed ${job.completedAt}`}
            </p>
          )}
          {job.startedAt && !job.completedAt && job.status !== 'CANCELLED' && (
            <p className="mt-2 text-xs text-gray-400">
              {job.startedAt.startsWith('Started')
                ? job.startedAt
                : `Started ${job.startedAt}`}
            </p>
          )}
        </div>
      </div>
    </article>
  );
};

export default DownloadJobCard;
